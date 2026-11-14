import AudioCommon
import CoreML
import Foundation
import KokoroTTS
import Observation
import SupertonicTTS
import VisaoKit

/// Voices that run on the iPhone itself (soniqo/speech-swift, Core ML), with no server and no
/// network once downloaded. Two for now, chosen in Ajustes → Voz no iPhone:
/// - Kokoro-82M, the open voice he chose on the server (pf_dora, docs/decisions/0004). Portuguese
///   The package's Portuguese dictionary is European, so the words go through our own Brazilian
///   phonemes (VisaoKit.BrazilianPhonemes) instead.
/// - Supertonic 3 (Supertone), 31 languages read straight from the text, no phoneme rules.
@MainActor
@Observable
final class LocalVoices {
    static let shared = LocalVoices()

    let kokoro = LocalVoice(.kokoro)
    let supertonic = LocalVoice(.supertonic)
    var all: [LocalVoice] { [supertonic, kokoro] }

    /// Which one speaks; nil is the server's voice or the iPhone's.
    var selected: LocalVoice.Kind? {
        didSet { UserDefaults.standard.set(selected?.rawValue ?? "none", forKey: "localVoice") }
    }

    private init() {
        let saved = UserDefaults.standard.string(forKey: "localVoice")
        if let saved, saved != "none" {
            selected = LocalVoice.Kind(rawValue: saved)
        } else if saved == nil {
            // Before there was a choice, a downloaded Kokoro (switched on) was the voice.
            let kokoroOn = UserDefaults.standard.object(forKey: "kokoroEnabled") as? Bool ?? true
            selected = kokoro.state == .onDisk && kokoroOn ? .kokoro : nil
        }
    }

    func voice(_ kind: LocalVoice.Kind) -> LocalVoice { kind == .kokoro ? kokoro : supertonic }

    /// The voice that speaks now, if one is downloaded, chosen and not known to crash here.
    var active: LocalVoice? {
        guard let selected else { return nil }
        let voice = voice(selected)
        return voice.usable ? voice : nil
    }

    /// Downloads one and makes it the voice.
    func download(_ kind: LocalVoice.Kind) async {
        let voice = voice(kind)
        await voice.download()
        if voice.usable { selected = kind }
    }
}

@MainActor
@Observable
final class LocalVoice: Identifiable {
    enum Kind: String, CaseIterable {
        case kokoro, supertonic

        var name: String { self == .kokoro ? "Kokoro" : "Supertonic 3" }
        var size: String { self == .kokoro ? "335 MB" : "350 MB" }
        var summary: String {
            switch self {
            case .kokoro: "A voz aberta que ele escolheu no servidor (Dora), treinada em português do Brasil, agora com pronúncia brasileira."
            case .supertonic: "Lê o português direto do texto, sem regras de pronúncia: costuma soar mais natural. 10 vozes."
            }
        }
        var source: String {
            switch self {
            case .kokoro: "aufklarer/Kokoro-82M-CoreML · Apache-2.0"
            case .supertonic: "aufklarer/Supertonic-3-CoreML-FP16 · OpenRAIL-M (proíbe imitar pessoas reais)"
            }
        }
        /// The voices it offers, with what to call them.
        var voices: [(id: String, label: String)] {
            switch self {
            case .kokoro: [("pf_dora", "Dora")]
            case .supertonic: (1...5).map { ("F\($0)", "Feminina \($0)") } + (1...5).map { ("M\($0)", "Masculina \($0)") }
            }
        }
        var sampleRate: Int { self == .kokoro ? 24_000 : 44_100 }
    }

    enum State: Equatable {
        case absent
        case downloading(Double)
        /// Downloaded, opened only the first time it has to speak.
        case onDisk
        case loading
        case ready
        case failed(String)
    }

    /// Where the model runs. The GPU path crashed Core ML on the iOS 27.3 beta (MPSGraph), so it
    /// starts on CPU + Neural Engine and falls back to the CPU alone.
    private enum Units: String {
        case neuralEngine, cpu
        var compute: MLComputeUnits { self == .neuralEngine ? .cpuAndNeuralEngine : .cpuOnly }
    }

    nonisolated let kind: Kind
    nonisolated var id: String { kind.rawValue }
    private(set) var state: State = .absent
    private let engine: LocalVoiceEngine

    /// The voice of this model that speaks (Ajustes).
    var voiceId: String {
        didSet { UserDefaults.standard.set(voiceId, forKey: key("voice")) }
    }

    init(_ kind: Kind) {
        self.kind = kind
        engine = LocalVoiceEngine(kind)
        voiceId = UserDefaults.standard.string(forKey: "\(kind.rawValue)Voice") ?? kind.voices[0].id
        guard engine.downloaded else { return }
        state = .onDisk
        // The last attempt to open it took the app down: step down to the CPU, or give up on
        // this system instead of crashing at every use.
        if UserDefaults.standard.bool(forKey: key("Opening")) {
            UserDefaults.standard.set(false, forKey: key("Opening"))
            if units == .neuralEngine {
                units = .cpu
            } else {
                state = .failed("Neste iPhone (iOS 27.3 beta) o sistema travou ao abrir a voz \(kind.name). Tente de novo depois de atualizar o iOS.")
            }
        }
    }

    private func key(_ suffix: String) -> String { kind.rawValue + suffix.prefix(1).uppercased() + suffix.dropFirst() }

    private var units: Units {
        get { Units(rawValue: UserDefaults.standard.string(forKey: key("units")) ?? "") ?? .neuralEngine }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: key("units")) }
    }

    var usable: Bool { state == .ready || state == .onDisk }

    /// Opens the model the first time it has to speak (no network). False: use another voice.
    func ensureLoaded() async -> Bool {
        switch state {
        case .ready: return true
        case .onDisk: break
        case .loading:
            while state == .loading { try? await Task.sleep(for: .milliseconds(100)) }
            return state == .ready
        default: return false
        }
        state = .loading
        UserDefaults.standard.set(true, forKey: key("Opening"))
        do {
            try await engine.load(offline: true, units: units.compute) { _ in }
            UserDefaults.standard.set(false, forKey: key("Opening"))
            state = .ready
            return true
        } catch {
            UserDefaults.standard.set(false, forKey: key("Opening"))
            state = .failed("Não deu para abrir a voz: \(error.localizedDescription)")
            return false
        }
    }

    /// Downloads from Hugging Face, only on request, then opens it.
    func download() async {
        if engine.downloaded {
            units = .neuralEngine
            state = .onDisk
            _ = await ensureLoaded()
            return
        }
        state = .downloading(0)
        UserDefaults.standard.set(true, forKey: key("Opening"))
        do {
            try await engine.load(offline: false, units: units.compute) { [weak self] fraction in
                Task { @MainActor in
                    if case .downloading = self?.state { self?.state = .downloading(fraction) }
                }
            }
            UserDefaults.standard.set(false, forKey: key("Opening"))
            state = .ready
        } catch {
            UserDefaults.standard.set(false, forKey: key("Opening"))
            state = engine.downloaded ? .onDisk : .failed("O download não terminou: \(error.localizedDescription)")
        }
    }

    /// Frees the space.
    func remove() async {
        await engine.unload()
        try? FileManager.default.removeItem(at: engine.cacheDirectory)
        state = .absent
        if LocalVoices.shared.selected == kind { LocalVoices.shared.selected = nil }
    }

    /// One sentence as WAV audio, ready for AVAudioPlayer.
    func audio(for sentence: String) async throws -> Data {
        try await engine.wav(sentence, voice: voiceId)
    }
}

/// Owns a model (they are not thread-safe) and renders off the main thread.
actor LocalVoiceEngine {
    private let kind: LocalVoice.Kind
    private var kokoro: KokoroTTSModel?
    private var supertonic: SupertonicTTSModel?

    nonisolated let modelId: String
    nonisolated let cacheDirectory: URL

    init(_ kind: LocalVoice.Kind) {
        self.kind = kind
        modelId = kind == .kokoro ? KokoroTTSModel.defaultModelId : "aufklarer/Supertonic-3-CoreML-FP16"
        cacheDirectory = (try? HuggingFaceDownloader.getCacheDirectory(for: modelId))
            ?? FileManager.default.temporaryDirectory.appendingPathComponent(kind.rawValue)
    }

    nonisolated var downloaded: Bool {
        let files = kind == .kokoro
            ? ["vocab_index.json", "voices/pf_dora.json"]
            : ["unicode_indexer.json", "tts.json", "voice_styles/F1.json"]
        return files.allSatisfy { FileManager.default.fileExists(atPath: cacheDirectory.appendingPathComponent($0).path) }
    }

    func load(offline: Bool, units: MLComputeUnits, progress: @escaping @Sendable (Double) -> Void) async throws {
        switch kind {
        case .kokoro:
            guard kokoro == nil else { return }
            kokoro = try await KokoroTTSModel.fromPretrained(
                voice: "pf_dora", offlineMode: offline, computeUnits: units, warmUp: true,
                progressHandler: { fraction, _ in progress(fraction) }
            )
        case .supertonic:
            guard supertonic == nil else { return }
            supertonic = try await SupertonicTTSModel.fromPretrained(
                modelId: modelId, offlineMode: offline, computeUnits: units,
                progressHandler: { fraction, _ in progress(fraction) }
            )
        }
    }

    func unload() {
        kokoro = nil
        supertonic = nil
    }

    func wav(_ text: String, voice: String) throws -> Data {
        switch kind {
        case .kokoro:
            guard let kokoro else { throw LocalVoiceError.notLoaded }
            // Brazilian phonemes of our own (BrazilianPhonemes), not the package's European
            // dictionary: each word goes as a code whose pronunciation is registered first.
            let input = BrazilianPhonemes.kokoroInput(text)
            guard !input.text.isEmpty else { return WAV.encode([], sampleRate: kind.sampleRate) }
            kokoro.addPronunciations(input.pronunciations)
            return WAV.encode(try kokoro.synthesize(text: input.text, voice: voice, language: "en"), sampleRate: kind.sampleRate)
        case .supertonic:
            guard let supertonic else { throw LocalVoiceError.notLoaded }
            return WAV.encode(try supertonic.synthesize(text: text, voice: voice, language: "pt"), sampleRate: kind.sampleRate)
        }
    }
}

enum LocalVoiceError: LocalizedError {
    case notLoaded
    var errorDescription: String? { "A voz no iPhone não está carregada." }
}

/// 16-bit mono PCM in a WAV container, for AVAudioPlayer.
enum WAV {
    static func encode(_ samples: [Float], sampleRate: Int) -> Data {
        var pcm = Data(capacity: samples.count * 2)
        for sample in samples {
            var value = Int16(max(-1, min(1, sample)) * Float(Int16.max)).littleEndian
            withUnsafeBytes(of: &value) { pcm.append(contentsOf: $0) }
        }
        var header = Data()
        func append<T: FixedWidthInteger>(_ value: T) {
            var little = value.littleEndian
            withUnsafeBytes(of: &little) { header.append(contentsOf: $0) }
        }
        header.append(contentsOf: Array("RIFF".utf8))
        append(UInt32(36 + pcm.count))
        header.append(contentsOf: Array("WAVEfmt ".utf8))
        append(UInt32(16))
        append(UInt16(1))
        append(UInt16(1))
        append(UInt32(sampleRate))
        append(UInt32(sampleRate * 2))
        append(UInt16(2))
        append(UInt16(16))
        header.append(contentsOf: Array("data".utf8))
        append(UInt32(pcm.count))
        return header + pcm
    }
}
