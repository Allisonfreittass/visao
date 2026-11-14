import AVFoundation
import Observation
import Speech
import UIKit

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

    override init() {
        super.init()
        synthesizer.delegate = self
    }

    // MARK: Permissions

    /// Microphone and speech recognition, asked once by the system.
    func requestPermissions() async -> Bool {
        let speech = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0 == .authorized) }
        }
        guard speech else { return false }
        return await AVAudioApplication.requestRecordPermission()
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

    /// Speaks, then calls back (also when stopped).
    func speak(_ text: String, done: @escaping () -> Void = {}) {
        stopListening()
        stopSpeaking()
        guard !text.isEmpty else {
            done()
            return
        }
        onSpoken = done
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = Self.bestVoice
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 1.02
        utterance.prefersAssistiveTechnologySettings = true
        phase = .speaking
        synthesizer.speak(utterance)
    }

    func stopSpeaking() {
        if synthesizer.isSpeaking { synthesizer.stopSpeaking(at: .immediate) }
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
        Task { @MainActor in self.spoke() }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor in self.spoke() }
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
