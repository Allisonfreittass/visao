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

    private let endOfSentence: Duration = .milliseconds(1300)
    /// Right after he starts a sentence, the echo canceller is still settling: ignore that much.
    private let settle: Duration = .milliseconds(450)

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "pt-BR"))
    private let audio = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let synthesizer = AVSpeechSynthesizer()
    private var playFormat: AVAudioFormat?
    private var request: SFSpeechAudioBufferRecognitionRequest?
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

    func start(api: APIClient) async throws {
        server = api
        if let status = try? await api.voiceStatus() { usesServerVoice = status.enabled }

        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat, options: [.defaultToSpeaker, .allowBluetoothHFP])
        try session.setActive(true)

        let input = audio.inputNode
        // The voice processing unit: echo cancellation of what this engine plays.
        try input.setVoiceProcessingEnabled(true)
        audio.attach(player)
        let rate = audio.outputNode.outputFormat(forBus: 0).sampleRate
        let format = AVAudioFormat(standardFormatWithSampleRate: rate > 0 ? rate : 48_000, channels: 1)!
        playFormat = format
        audio.connect(player, to: audio.mainMixerNode, format: format)

        Self.installTap(on: input, format: input.outputFormat(forBus: 0), feed: feed) { [weak self] level in
            Task { @MainActor in self?.level = level }
        }
        audio.prepare()
        try audio.start()
        player.play()
        running = true
        try beginSentence()
    }

    func stop() {
        running = false
        stopSpeaking()
        silenceWatch?.cancel()
        feed.request = nil
        request?.endAudio()
        task?.cancel()
        if audio.isRunning {
            player.stop()
            audio.inputNode.removeTap(onBus: 0)
            audio.stop()
        }
        try? audio.inputNode.setVoiceProcessingEnabled(false)
        phase = .idle
        level = 0
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: Listening, all the time

    /// A new recognition for your next sentence; the microphone itself never stops.
    private func beginSentence() throws {
        guard running, let recognizer, recognizer.isAvailable else { throw VoiceError.unavailable }
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
            Task { @MainActor in self?.heard(text, final: final) }
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

    private func heard(_ text: String, final: Bool) {
        guard running else { return }
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
            feed.request?.append(buffer)
            guard let channel = buffer.floatChannelData?[0] else { return }
            let count = Int(buffer.frameLength)
            guard count > 0 else { return }
            var sum: Float = 0
            for i in 0..<count { sum += channel[i] * channel[i] }
            level(min(1, sqrt(sum / Float(count)) * 12))
        }
    }

    nonisolated private static func recognize(
        with recognizer: SFSpeechRecognizer, request: SFSpeechAudioBufferRecognitionRequest,
        handler: @escaping @Sendable (String, Bool) -> Void
    ) -> SFSpeechRecognitionTask {
        recognizer.recognitionTask(with: request) { result, _ in
            guard let result else { return }
            handler(result.bestTranscription.formattedString, result.isFinal)
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
