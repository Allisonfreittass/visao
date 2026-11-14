import AVFoundation
import Observation
import Speech
import UIKit
import VisaoKit

/// The iPhone's own voice (docs/VOICE.md, "Voz do aparelho"): listens in Brazilian Portuguese with
/// the speech recognizer and speaks with the system synthesizer. Recognition stays on the device
/// when the iPhone supports it. While it speaks it does not listen: the system voice is not
/// cancelled out of the microphone, so it would hear itself (Interromper stops it).
@MainActor
@Observable
final class VoiceEngine: NSObject {
    enum Phase: Equatable { case idle, listening, speaking }

    private(set) var phase: Phase = .idle
    /// What it is hearing right now, before the sentence ends.
    private(set) var partial = ""
    /// The microphone level, 0...1, for the orb.
    private(set) var level: Float = 0
    /// True when recognition runs on the iPhone itself (no audio leaves it).
    var onDevice: Bool { recognizer?.supportsOnDeviceRecognition ?? false }
    var canListen: Bool { recognizer?.isAvailable ?? false }

    /// A sentence ends after this much silence.
    private let endOfSentence: Duration = .milliseconds(1300)

    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "pt-BR"))
    private let audio = AVAudioEngine()
    private let synthesizer = AVSpeechSynthesizer()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var lastChange = ContinuousClock.now
    private var silenceWatch: Task<Void, Never>?
    private var onUtterance: ((String) -> Void)?
    private var onSpoken: (() -> Void)?

    /// The server's own voice (Kokoro, "voz própria"), when it has one; the iPhone's otherwise.
    private(set) var usesServerVoice = false
    private(set) var serverVoiceName: String?
    private var server: APIClient?
    private var serverSpeech: Task<Void, Never>?
    private var player: AVAudioPlayer?
    private var playerDone: CheckedContinuation<Void, Never>?
    /// The utterance being said: a late "cancelled" from the previous one must not end this one.
    private var currentUtterance: ObjectIdentifier?

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    // MARK: Permissions

    /// Microphone and speech recognition, asked once by the system.
    func requestPermissions() async -> Bool {
        guard await Self.speechAuthorization() else { return false }
        return await AVAudioApplication.requestRecordPermission()
    }

    /// The system answers on a background queue: asked outside the main actor, or Swift stops the
    /// app for answering on the wrong thread.
    nonisolated private static func speechAuthorization() async -> Bool {
        await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
            SFSpeechRecognizer.requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
    }

    // MARK: Session

    func activate() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .duckOthers])
        try session.setActive(true)
    }

    func deactivate() {
        stopListening()
        stopSpeaking()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    // MARK: Listening

    /// Listens until a sentence ends (a short silence), then hands it over and stops.
    func listen(_ handler: @escaping (String) -> Void) throws {
        stopListening()
        guard let recognizer, recognizer.isAvailable else { throw VoiceError.unavailable }
        onUtterance = handler
        partial = ""

        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.taskHint = .dictation
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        self.request = request

        let input = audio.inputNode
        let format = input.outputFormat(forBus: 0)
        Self.installTap(on: input, format: format, request: request) { [weak self] level in
            Task { @MainActor in self?.level = level }
        }
        audio.prepare()
        try audio.start()

        task = Self.recognize(with: recognizer, request: request) { [weak self] text, final in
            Task { @MainActor in self?.heard(text, final: final) }
        }
        phase = .listening
        lastChange = .now
        silenceWatch = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(200))
                guard let self else { return }
                if !self.partial.isEmpty, ContinuousClock.now - self.lastChange > self.endOfSentence {
                    self.finish()
                    return
                }
            }
        }
    }

    func stopListening() {
        silenceWatch?.cancel()
        silenceWatch = nil
        if audio.isRunning {
            audio.stop()
            audio.inputNode.removeTap(onBus: 0)
        }
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
        level = 0
        if phase == .listening { phase = .idle }
    }

    private func heard(_ text: String, final: Bool) {
        guard phase == .listening else { return }
        if text != partial {
            partial = text
            lastChange = .now
        }
        if final { finish() }
    }

    private func finish() {
        let sentence = partial.trimmingCharacters(in: .whitespacesAndNewlines)
        let handler = onUtterance
        onUtterance = nil
        stopListening()
        partial = ""
        if !sentence.isEmpty { handler?(sentence) }
    }

    /// The audio tap runs on the audio thread: built outside the main actor on purpose.
    nonisolated private static func installTap(
        on node: AVAudioInputNode, format: AVAudioFormat, request: SFSpeechAudioBufferRecognitionRequest,
        level: @escaping @Sendable (Float) -> Void
    ) {
        nonisolated(unsafe) let request = request
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            request.append(buffer)
            guard let channel = buffer.floatChannelData?[0] else { return }
            let count = Int(buffer.frameLength)
            guard count > 0 else { return }
            var sum: Float = 0
            for i in 0..<count { sum += channel[i] * channel[i] }
            let rms = sqrt(sum / Float(count))
            level(min(1, rms * 12))
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

    // MARK: Speaking

    /// Asks the server whether it has its own voice; from then on it speaks with it.
    func prepare(api: APIClient) async {
        server = api
        guard let status = try? await api.voiceStatus() else { return }
        usesServerVoice = status.enabled
        serverVoiceName = status.currentVoice
    }

    /// Speaks, then calls back (also when stopped).
    func speak(_ text: String, done: @escaping () -> Void = {}) {
        stopListening()
        stopSpeaking()
        guard !text.isEmpty else {
            done()
            return
        }
        onSpoken = done
        // A voice on the iPhone first (no network), then the server's own voice, then the iPhone's.
        if let local = LocalVoices.shared.active {
            phase = .speaking
            let sentences = VoiceRules.sentences(text)
            serverSpeech = Task { [weak self] in
                // Opened on first use; if it cannot open here, the next voice in line speaks.
                guard await local.ensureLoaded() else {
                    self?.speakWithoutKokoro(text)
                    return
                }
                await self?.speakClips(sentences, fallbackText: text) { try await local.audio(for: $0) }
            }
            return
        }
        speakWithoutKokoro(text)
    }

    private func speakWithoutKokoro(_ text: String) {
        guard !Task.isCancelled else { return }
        if usesServerVoice, let server {
            phase = .speaking
            serverSpeech = Task { [weak self] in await self?.speakWithServer(text, api: server) }
            return
        }
        speakWithDevice(text)
    }

    private func speakWithDevice(_ text: String) {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.bestVoice
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 1.02
        utterance.prefersAssistiveTechnologySettings = true
        phase = .speaking
        currentUtterance = ObjectIdentifier(utterance)
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        serverSpeech?.cancel()
        serverSpeech = nil
        player?.stop()
        player = nil
        playerDone?.resume()
        playerDone = nil
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
    }

    /// Sentence by sentence, the next one synthesized while the current plays (as the web does).
    /// If the server fails midway, the rest is said with the iPhone's voice.
    private func speakWithServer(_ text: String, api: APIClient) async {
        guard let sentences = try? await api.sentences(text), !sentences.isEmpty else {
            if !Task.isCancelled { speakWithDevice(text) }
            return
        }
        await speakClips(sentences, fallbackText: text) { try await api.tts($0) }
    }

    /// Plays sentence after sentence, rendering the next while the current plays. A failure
    /// midway says the rest with the iPhone's voice.
    private func speakClips(_ sentences: [String], fallbackText: String, render: @escaping @Sendable (String) async throws -> Data) async {
        guard !sentences.isEmpty else {
            if !Task.isCancelled { spoke() }
            return
        }
        var next: Task<Data, Error>? = Task { try await render(sentences[0]) }
        for index in sentences.indices {
            guard !Task.isCancelled, let pending = next else { return }
            guard let audio = try? await pending.value else {
                if !Task.isCancelled { speakWithDevice(sentences[index...].joined(separator: " ")) }
                return
            }
            next = index + 1 < sentences.count ? Task { [sentence = sentences[index + 1]] in try await render(sentence) } : nil
            guard !Task.isCancelled else { return }
            await play(audio)
        }
        if !Task.isCancelled { spoke() }
    }

    private func play(_ audio: Data) async {
        guard let player = try? AVAudioPlayer(data: audio) else { return }
        self.player = player
        player.delegate = self
        player.isMeteringEnabled = true
        await withCheckedContinuation { continuation in
            playerDone = continuation
            if !player.play() {
                playerDone = nil
                continuation.resume()
            }
        }
        self.player = nil
    }

    fileprivate func finishedClip() {
        playerDone?.resume()
        playerDone = nil
    }

    fileprivate func deviceSpoke(_ id: ObjectIdentifier) {
        guard id == currentUtterance else { return }
        currentUtterance = nil
        spoke()
    }

    private func spoke() {
        if phase == .speaking { phase = .idle }
        let callback = onSpoken
        onSpoken = nil
        callback?()
    }

    /// A Brazilian voice from the iPhone, the best quality installed (Ajustes → Acessibilidade →
    /// Conteúdo Falado → Vozes downloads better ones).
    static var bestVoice: AVSpeechSynthesisVoice? {
        let voices = AVSpeechSynthesisVoice.speechVoices().filter { $0.language == "pt-BR" }
        return voices.max { $0.quality.rawValue < $1.quality.rawValue } ?? AVSpeechSynthesisVoice(language: "pt-BR")
    }

    static var voiceName: String { bestVoice?.name ?? "voz do aparelho" }
}

extension VoiceEngine: AVSpeechSynthesizerDelegate {
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        let id = ObjectIdentifier(utterance)
        Task { @MainActor in self.deviceSpoke(id) }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        let id = ObjectIdentifier(utterance)
        Task { @MainActor in self.deviceSpoke(id) }
    }
}

enum VoiceError: LocalizedError {
    case unavailable
    case denied

    var errorDescription: String? {
        switch self {
        case .unavailable: "O reconhecimento de voz não está disponível agora."
        case .denied: "Para ligar, permita o microfone e o reconhecimento de fala em Ajustes do iPhone."
        }
    }
}

/// The voice switches kept on this iPhone (Ajustes → Voz e avisos).
enum VoicePrefs {
    static var speakReplies: Bool {
        get { UserDefaults.standard.bool(forKey: "speakReplies") }
        set { UserDefaults.standard.set(newValue, forKey: "speakReplies") }
    }

    /// On unless turned off, as on the web.
    static var voiceApproval: Bool {
        get { UserDefaults.standard.object(forKey: "voiceApproval") as? Bool ?? true }
        set { UserDefaults.standard.set(newValue, forKey: "voiceApproval") }
    }
}

extension VoiceEngine: AVAudioPlayerDelegate {
    nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        Task { @MainActor in self.finishedClip() }
    }
}
