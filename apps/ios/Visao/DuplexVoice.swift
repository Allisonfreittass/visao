import AVFoundation
import Observation
import Speech
import VisaoKit

/// The call's audio in both directions at once, so you can interrupt him by talking (as in Grok's
/// voice mode). The microphone stays open with the iPhone's voice processing (the echo
/// cancellation FaceTime uses), and his voice plays through the same engine, so the iPhone knows
/// what to subtract from the microphone. While he speaks, the recognizer keeps listening: a word or
/// two from you and he stops, and what you are saying goes on as your turn.
///
/// The half-duplex VoiceEngine stays as the fallback (Ajustes → "Interromper falando").
@MainActor
@Observable
final class DuplexVoice {
    enum Phase: Equatable { case idle, listening, speaking }

    private(set) var phase: Phase = .idle
    /// What it is hearing right now, before the sentence ends.
    private(set) var partial = ""
    /// The microphone level, 0...1, for the orb.
    private(set) var level: Float = 0
    private(set) var usesServerVoice = false
    var onDevice: Bool { recognizer?.supportsOnDeviceRecognition ?? false }

    /// Your sentence ended (a short silence).
    var onUtterance: ((String) -> Void)?
    /// You started talking over him: he already stopped.
    var onBargeIn: (() -> Void)?
    /// Your voice reaches the microphone but no text comes out: the call should go back to the
    /// half-duplex way instead of leaving you talking to nobody.
    var onDeaf: (() -> Void)?

    /// Seconds of loud microphone with no recognized text, and whether any text ever came.
    private var loudWithoutText: Double = 0
    private var everHeard = false
    private var lastLevelLog = ContinuousClock.now

    private let endOfSentence: Duration = .milliseconds(1300)
    /// Right after he starts a sentence, the echo canceller is still settling: ignore that much.
    private let settle: Duration = .milliseconds(450)

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "pt-BR"))
    // A fresh engine for each attempt: after voice processing is switched, reusing one tends
    // to leave the microphone silent.
    private var audio = AVAudioEngine()
    private var player = AVAudioPlayerNode()
    /// The microphone goes into this mixer at volume zero: with voice processing on, iOS only
    /// pulls audio from an input that is wired into the graph (a loose tap got nothing at all).
    private var micSink = AVAudioMixerNode()
    private var configObserver: NSObjectProtocol?
    private var watchdog: Task<Void, Never>?
    private var gotFirstBuffer = false
    private let synthesizer = AVSpeechSynthesizer()
    private var playFormat: AVAudioFormat?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    /// Which recognition is the current one. Closing the previous one makes iOS report "no
    /// speech" for it; treated as current, that restarted the new one, and so on every 300 ms,
    /// so no recognition lived long enough to hear you. Old ones are now ignored.
    private var generation = 0
    private var task: SFSpeechRecognitionTask?
    private var lastChange = ContinuousClock.now
    private var speakingSince = ContinuousClock.now
    private var silenceWatch: Task<Void, Never>?
    private var speech: Task<Void, Never>?
    private var server: APIClient?
    private var running = false
    /// The request the audio tap feeds; swapped for each of your sentences.
    private let feed = RequestBox()

    // MARK: Start and stop

    /// Opens the two-way audio. Tries the voice-chat session first and the default one second,
    /// each with a brand-new engine, and only keeps one where the microphone keeps delivering
    /// sound. Throws when neither does: the call then goes on the half-duplex way.
    func start(api: APIClient) async throws {
        server = api
        if let status = try? await api.voiceStatus() { usesServerVoice = status.enabled }
        for mode in [AVAudioSession.Mode.voiceChat, .default] {
            do {
                try configure(mode: mode)
                if await microphoneFlows() {
                    VoiceLog.write("modo \(mode.rawValue): microfone entregando som (\(feed.buffers) blocos)")
                    running = true
                    observeEngine()
                    try beginSentence()
                    return
                }
                VoiceLog.write("modo \(mode.rawValue): microfone mudo (\(feed.buffers) blocos em 1,5 s, motor \(audio.isRunning ? "ligado" : "parado"))")
            } catch {
                VoiceLog.write("modo \(mode.rawValue) falhou: \(error.localizedDescription)")
            }
            teardown()
        }
        throw VoiceError.unavailable
    }

    private func configure(mode: AVAudioSession.Mode) throws {
        audio = AVAudioEngine()
        player = AVAudioPlayerNode()
        micSink = AVAudioMixerNode()
        feed.buffers = 0
        gotFirstBuffer = false

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: mode, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true)

        let input = audio.inputNode
        // The voice processing unit: echo cancellation of what this engine plays.
        try input.setVoiceProcessingEnabled(true)
        // Let the route and the voice processing settle before starting: changed right after
        // the start, they stop the engine ("motor parado" in the diary).
        Thread.sleep(forTimeInterval: 0.25)
        audio.attach(player)
        let rate = audio.outputNode.outputFormat(forBus: 0).sampleRate
        let format = AVAudioFormat(standardFormatWithSampleRate: rate > 0 ? rate : 48_000, channels: 1)!
        playFormat = format
        audio.connect(player, to: audio.mainMixerNode, format: format)

        let inFormat = input.outputFormat(forBus: 0)
        audio.attach(micSink)
        audio.connect(input, to: micSink, format: inFormat)
        audio.connect(micSink, to: audio.mainMixerNode, format: inFormat)
        micSink.outputVolume = 0
        VoiceLog.write("início (\(mode.rawValue)): rota \(session.currentRoute.inputs.map(\.portType.rawValue))→\(session.currentRoute.outputs.map(\.portType.rawValue)); entrada \(inFormat.sampleRate) Hz, \(inFormat.channelCount) canais; processamento de voz \(input.isVoiceProcessingEnabled), mudo \(input.isVoiceProcessingInputMuted)")
        Self.installTap(on: input, format: inFormat, feed: feed) { [weak self] level in
            Task { @MainActor in self?.measure(level) }
        }
        audio.prepare()
        try audio.start()
        player.play()
    }

    /// Sound keeps coming from the microphone: a few blocks within 3 s. iOS may still stop the
    /// engine while it finishes setting up the audio; then it is started again, right here.
    private func microphoneFlows() async -> Bool {
        var restarts = 0
        for _ in 0..<30 {
            try? await Task.sleep(for: .milliseconds(100))
            if feed.buffers >= 6 { return true }
            if !audio.isRunning && restarts < 4 {
                restarts += 1
                do {
                    try audio.start()
                    player.play()
                    VoiceLog.write("motor parou ao começar; religado (\(restarts))")
                } catch {
                    VoiceLog.write("motor não religou: \(error.localizedDescription)")
                }
            }
        }
        return false
    }

    private func teardown() {
        player.stop()
        audio.inputNode.removeTap(onBus: 0)
        audio.stop()
        try? audio.inputNode.setVoiceProcessingEnabled(false)
        audio.detach(player)
        audio.detach(micSink)
    }

    /// If iOS reconfigures the audio mid-call the engine stops quietly: start it again. And if
    /// the microphone goes quiet anyway, the call goes back to the half-duplex way.
    private func observeEngine() {
        configObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: audio, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self, self.running else { return }
                VoiceLog.write("o iOS reconfigurou o áudio; religando o motor")
                try? self.audio.start()
                self.player.play()
            }
        }
        watchdog = Task { [weak self] in
            var last = 0
            var quiet = 0
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self, self.running else { return }
                let now = self.feed.buffers
                if now == last {
                    quiet += 1
                    VoiceLog.write("microfone sem som há \(quiet) s (motor \(self.audio.isRunning ? "ligado" : "parado"))")
                    if quiet == 2 { try? self.audio.start(); self.player.play() }
                    if quiet >= 4 { self.onDeaf?(); return }
                } else {
                    quiet = 0
                }
                last = now
            }
        }
    }

    func stop() {
        running = false
        watchdog?.cancel()
        if let configObserver { NotificationCenter.default.removeObserver(configObserver) }
        configObserver = nil
        stopSpeaking()
        silenceWatch?.cancel()
        feed.request = nil
        request?.endAudio()
        task?.cancel()
        teardown()
        phase = .idle
        level = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: Listening, all the time

    /// A new recognition for your next sentence; the microphone itself never stops.
    private func beginSentence() throws {
        guard running, let recognizer, recognizer.isAvailable else { throw VoiceError.unavailable }
        generation += 1
        let current = generation
        task?.cancel()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        self.request = request
        feed.request = request
        partial = ""
        lastChange = .now
        task = Self.recognize(with: recognizer, request: request) { [weak self] text, final in
            Task { @MainActor in
                guard let self, current == self.generation else { return }
                self.heard(text, final: final)
            }
        } failed: { [weak self] message in
            Task { @MainActor in
                guard let self, current == self.generation else { return }
                self.recognitionFailed(message)
            }
        }
        if phase != .speaking { phase = .listening }
        silenceWatch?.cancel()
        silenceWatch = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(200))
                guard let self else { return }
                if self.phase != .speaking, !self.partial.isEmpty, ContinuousClock.now - self.lastChange > self.endOfSentence {
                    self.finishSentence()
                    return
                }
            }
        }
    }

    /// The microphone level for the orb, and the watch for "voice but no text".
    private func measure(_ value: Float) {
        level = value
        if !gotFirstBuffer {
            gotFirstBuffer = true
            VoiceLog.write("primeiro som do microfone chegou (nível \(String(format: "%.2f", value)))")
        }
        guard running, phase != .speaking else { return }
        if value > 0.35 && partial.isEmpty && !everHeard {
            loudWithoutText += 1024 / 48_000
            if loudWithoutText > 4 {
                VoiceLog.write("surdo: \(String(format: "%.1f", loudWithoutText)) s de voz no microfone e nenhum texto; voltando ao modo sem interrupção")
                loudWithoutText = 0
                onDeaf?()
            }
        }
        if ContinuousClock.now - lastLevelLog > .seconds(3) {
            lastLevelLog = .now
            VoiceLog.write("nível \(String(format: "%.2f", value)), fase \(phase), parcial \(partial.isEmpty ? "vazio" : "“\(partial)”")")
        }
    }

    /// The recognizer gave up (no speech, a hiccup): a new one starts, the microphone stays on.
    private func recognitionFailed(_ message: String) {
        guard running else { return }
        VoiceLog.write("reconhecimento falhou: \(message)")
        let failedGeneration = generation
        Task {
            try? await Task.sleep(for: .milliseconds(300))
            // Restart only if nothing else already did.
            guard self.running, self.generation == failedGeneration else { return }
            try? self.beginSentence()
        }
    }

    private func heard(_ text: String, final: Bool) {
        guard running else { return }
        if !everHeard, !text.isEmpty {
            everHeard = true
            VoiceLog.write("primeiro texto: “\(text)”")
        }
        if text != partial {
            partial = text
            lastChange = .now
        }
        // Talking over him: a word or two that is not the echo of his own voice.
        if phase == .speaking, ContinuousClock.now - speakingSince > settle, Self.isRealSpeech(text) {
            stopSpeaking()
            phase = .listening
            onBargeIn?()
        }
        if final, phase != .speaking { finishSentence() }
    }

    /// Two letters of noise are not an interruption.
    static func isRealSpeech(_ text: String) -> Bool {
        let words = text.split(separator: " ").filter { $0.count >= 2 }
        return words.count >= 2 || text.trimmingCharacters(in: .whitespaces).count >= 6
    }

    private func finishSentence() {
        let sentence = partial.trimmingCharacters(in: .whitespacesAndNewlines)
        partial = ""
        request?.endAudio()
        try? beginSentence()
        if !sentence.isEmpty { onUtterance?(sentence) }
    }

    // MARK: Speaking through the same engine

    /// Speaks (a voice on the iPhone, the server's own, or the system's), then calls back. A
    /// barge-in stops it without calling back.
    func speak(_ text: String, done: @escaping () -> Void) {
        stopSpeaking()
        guard running, !text.isEmpty else {
            done()
            return
        }
        phase = .speaking
        speakingSince = .now
        // What you said before he started is not an interruption of this.
        if !partial.isEmpty { finishSentence() }
        speech = Task { [weak self] in
            guard let self else { return }
            let finished = await self.render(text)
            guard !Task.isCancelled, finished, self.phase == .speaking else { return }
            self.phase = .listening
            done()
        }
    }

    func stopSpeaking() {
        speech?.cancel()
        speech = nil
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
        player.stop()
        if running { player.play() }
        if phase == .speaking { phase = .listening }
    }

    /// Sentence by sentence, rendering the next while the current plays. True when all was said.
    private func render(_ text: String) async -> Bool {
        let sentences = VoiceRules.sentences(text)
        if let local = LocalVoices.shared.active, await local.ensureLoaded() {
            let rate = local.kind.sampleRate
            return await playSentences(sentences) { sentence in
                let samples = try await local.samples(for: sentence)
                return Clip(Self.buffer(samples, sampleRate: rate))
            }
        }
        if usesServerVoice, let server {
            let parts = (try? await server.sentences(text)) ?? sentences
            return await playSentences(parts) { sentence in
                Clip(Self.buffer(wav: try await server.tts(sentence)))
            }
        }
        let synth = SynthBox(synthesizer)
        let voice = VoiceEngine.bestVoice
        return await playSentences(sentences) { sentence in
            Clip(await Self.systemVoice(sentence, synthesizer: synth, voice: voice))
        }
    }

    private func playSentences(_ sentences: [String], render: @escaping @Sendable (String) async throws -> Clip) async -> Bool {
        guard !sentences.isEmpty else { return true }
        var next: Task<Clip, Error>? = Task { try await render(sentences[0]) }
        for index in sentences.indices {
            guard !Task.isCancelled, let pending = next else { return false }
            let clip = try? await pending.value
            next = index + 1 < sentences.count ? Task { [sentence = sentences[index + 1]] in try await render(sentence) } : nil
            guard !Task.isCancelled else { return false }
            if let buffer = clip?.buffer { await play(buffer) }
        }
        return !Task.isCancelled
    }

    private func play(_ source: AVAudioPCMBuffer) async {
        guard let playFormat, let buffer = Self.convert(source, to: playFormat) else { return }
        nonisolated(unsafe) let node = player
        nonisolated(unsafe) let pcm = buffer
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            node.scheduleBuffer(pcm, at: nil, options: [], completionCallbackType: .dataPlayedBack) { _ in
                continuation.resume()
            }
        }
    }

    // MARK: Audio plumbing (off the main actor)

    nonisolated private static func installTap(
        on node: AVAudioInputNode, format: AVAudioFormat, feed: RequestBox,
        level: @escaping @Sendable (Float) -> Void
    ) {
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            feed.count()
            feed.request?.append(buffer)
            guard let channel = buffer.floatChannelData?[0] else { return }
            let count = Int(buffer.frameLength)
            guard count > 0 else { return }
            var sum: Float = 0
            for i in 0..<count { sum += channel[i] * channel[i] }
            // Voice processing lowers the signal a lot: a decibel scale (-55 dB to -15 dB).
            let rms = sqrt(sum / Float(count))
            let db = 20 * log10(max(rms, 1e-7))
            level(min(1, max(0, (db + 55) / 40)))
        }
    }

    nonisolated private static func recognize(
        with recognizer: SFSpeechRecognizer, request: SFSpeechAudioBufferRecognitionRequest,
        handler: @escaping @Sendable (String, Bool) -> Void,
        failed: @escaping @Sendable (String) -> Void
    ) -> SFSpeechRecognitionTask {
        recognizer.recognitionTask(with: request) { result, error in
            if let result {
                handler(result.bestTranscription.formattedString, result.isFinal)
            } else if let error = error as NSError?, !(error.domain == "kLSRErrorDomain" && error.code == 301) {
                // 301 is "cancelled", which we do ourselves for every new sentence.
                failed("\(error.domain) \(error.code): \(error.localizedDescription)")
            }
        }
    }

    nonisolated static func buffer(_ samples: [Float], sampleRate: Int) -> AVAudioPCMBuffer? {
        guard !samples.isEmpty,
              let format = AVAudioFormat(standardFormatWithSampleRate: Double(sampleRate), channels: 1),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(samples.count)) else { return nil }
        buffer.frameLength = AVAudioFrameCount(samples.count)
        samples.withUnsafeBufferPointer { source in
            buffer.floatChannelData![0].update(from: source.baseAddress!, count: samples.count)
        }
        return buffer
    }

    /// The server's WAV, read through a temporary file.
    nonisolated static func buffer(wav: Data) -> AVAudioPCMBuffer? {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("visao-\(UUID().uuidString).wav")
        defer { try? FileManager.default.removeItem(at: url) }
        guard (try? wav.write(to: url)) != nil, let file = try? AVAudioFile(forReading: url),
              let buffer = AVAudioPCMBuffer(pcmFormat: file.processingFormat, frameCapacity: AVAudioFrameCount(file.length)),
              (try? file.read(into: buffer)) != nil else { return nil }
        return buffer
    }

    nonisolated static func convert(_ buffer: AVAudioPCMBuffer, to format: AVAudioFormat) -> AVAudioPCMBuffer? {
        if buffer.format == format { return buffer }
        guard let converter = AVAudioConverter(from: buffer.format, to: format) else { return nil }
        let ratio = format.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 1024
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: capacity) else { return nil }
        nonisolated(unsafe) var given = false
        nonisolated(unsafe) let input = buffer
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given {
                status.pointee = .endOfStream
                return nil
            }
            given = true
            status.pointee = .haveData
            return input
        }
        return error == nil ? out : nil
    }

    /// The iPhone's own voice rendered to a buffer (instead of straight to the speaker), so it
    /// goes through the echo canceller like the others.
    nonisolated static func systemVoice(_ text: String, synthesizer: SynthBox, voice: AVSpeechSynthesisVoice?) async -> AVAudioPCMBuffer? {
        let synth = synthesizer.synth
        nonisolated(unsafe) let chosen = voice
        let clip: Clip = await withCheckedContinuation { (continuation: CheckedContinuation<Clip, Never>) in
            let utterance = AVSpeechUtterance(string: text)
            utterance.voice = chosen
            utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 1.02
            nonisolated(unsafe) var pieces: [AVAudioPCMBuffer] = []
            nonisolated(unsafe) var resumed = false
            synth.write(utterance) { buffer in
                guard let pcm = buffer as? AVAudioPCMBuffer else { return }
                if pcm.frameLength == 0 {
                    guard !resumed else { return }
                    resumed = true
                    continuation.resume(returning: Clip(Self.join(pieces)))
                } else {
                    pieces.append(pcm)
                }
            }
        }
        return clip.buffer
    }

    nonisolated private static func join(_ pieces: [AVAudioPCMBuffer]) -> AVAudioPCMBuffer? {
        guard let first = pieces.first else { return nil }
        let total = pieces.reduce(0) { $0 + Int($1.frameLength) }
        guard let format = AVAudioFormat(standardFormatWithSampleRate: first.format.sampleRate, channels: 1),
              let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(total)) else { return nil }
        var offset = 0
        for piece in pieces {
            guard let converted = convert(piece, to: format), let source = converted.floatChannelData?[0] else { continue }
            let count = Int(converted.frameLength)
            out.floatChannelData![0].advanced(by: offset).update(from: source, count: min(count, total - offset))
            offset += count
        }
        out.frameLength = AVAudioFrameCount(min(offset, total))
        return out
    }
}

/// The recognition request the audio thread feeds, swapped from the main actor.
final class RequestBox: @unchecked Sendable {
    private let lock = NSLock()
    private var current: SFSpeechAudioBufferRecognitionRequest?
    private var received = 0

    /// Blocks of sound the microphone delivered since the last reset.
    var buffers: Int {
        get { lock.withLock { received } }
        set { lock.withLock { received = newValue } }
    }

    func count() { lock.withLock { received += 1 } }

    var request: SFSpeechAudioBufferRecognitionRequest? {
        get { lock.withLock { current } }
        set { lock.withLock { current = newValue } }
    }
}

/// An audio buffer handed from where it is rendered to where it is played, once.
struct Clip: @unchecked Sendable {
    let buffer: AVAudioPCMBuffer?
    init(_ buffer: AVAudioPCMBuffer?) { self.buffer = buffer }
}

/// The system synthesizer, used from the rendering task only.
struct SynthBox: @unchecked Sendable {
    let synth: AVSpeechSynthesizer
    init(_ synth: AVSpeechSynthesizer) { self.synth = synth }
}

/// A small diary of the call's audio, in the app's caches, read through the cable to find out
/// why it did not hear (xcrun devicectl … --domain-type appDataContainer). Kept short.
enum VoiceLog {
    static var url: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("diario-da-voz.txt")
    }

    static func write(_ line: String) {
        let stamp = Date().formatted(date: .omitted, time: .standard)
        let entry = Data("\(stamp) \(line)\n".utf8)
        if let handle = try? FileHandle(forWritingTo: url) {
            defer { try? handle.close() }
            if (try? handle.seekToEnd()) ?? 0 > 200_000 {
                try? handle.truncate(atOffset: 0)
            }
            try? handle.write(contentsOf: entry)
        } else {
            try? entry.write(to: url)
        }
    }
}
