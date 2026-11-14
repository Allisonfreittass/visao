import AudioCommon
import CoreML
import Foundation
import KokoroTTS
import Observation

/// Kokoro-82M on the iPhone itself (soniqo/speech-swift, CoreML on the Neural Engine): the same
/// open voice the server uses (pf_dora, docs/decisions/0004), with no server and no network once
/// the model is downloaded. Portuguese goes through a pronunciation dictionary and rules written
/// in Swift: no espeak-ng, no GPL.
@MainActor
@Observable
final class KokoroVoice {
    static let shared = KokoroVoice()

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

    private static let unitsKey = "kokoroUnits"
    /// Set while the model opens; still set at the next launch means opening it crashed the app.
    private static let openingKey = "kokoroOpening"

    private(set) var state: State = .absent
    /// The voice he chose on the server, pf_dora by default.
    static let voice = "pf_dora"
    /// Shown on the download button: the model, the Portuguese and auxiliary dictionaries.
    static let downloadSize = "335 MB"

    /// Kokoro speaks when the model is here and this switch is on (Ajustes → Voz e avisos).
    var enabled: Bool {
        didSet { UserDefaults.standard.set(enabled, forKey: "kokoroEnabled") }
    }

    private let engine = KokoroEngine()

    private init() {
        enabled = UserDefaults.standard.object(forKey: "kokoroEnabled") as? Bool ?? true
        guard KokoroEngine.downloaded else { return }
        state = .onDisk
        // The last attempt to open it took the app down: step down to the CPU, or give up on
        // this system instead of crashing at every use.
        if UserDefaults.standard.bool(forKey: Self.openingKey) {
            UserDefaults.standard.set(false, forKey: Self.openingKey)
            if units == .neuralEngine {
                units = .cpu
            } else {
                state = .failed("Neste iPhone (iOS 27.3 beta) o sistema travou ao abrir a voz Kokoro. Ele fala com a voz do servidor ou do iPhone; tente de novo depois de atualizar o iOS.")
            }
        }
    }

    private var units: Units {
        get { Units(rawValue: UserDefaults.standard.string(forKey: Self.unitsKey) ?? "") ?? .neuralEngine }
        set { UserDefaults.standard.set(newValue.rawValue, forKey: Self.unitsKey) }
    }

    var isReady: Bool { state == .ready }
    /// Downloaded, switched on and not known to crash here: Kokoro is the voice.
    var speaks: Bool { enabled && (state == .ready || state == .onDisk) }

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
        UserDefaults.standard.set(true, forKey: Self.openingKey)
        do {
            try await engine.load(offline: true, units: units.compute) { _ in }
            UserDefaults.standard.set(false, forKey: Self.openingKey)
            state = .ready
            return true
        } catch {
            UserDefaults.standard.set(false, forKey: Self.openingKey)
            state = .failed("Não deu para abrir o modelo: \(error.localizedDescription)")
            return false
        }
    }

    /// Tries again from the start (after an iOS update, say): Neural Engine first.
    func retry() async {
        units = .neuralEngine
        state = KokoroEngine.downloaded ? .onDisk : .absent
        if state == .onDisk { _ = await ensureLoaded() }
    }

    /// Downloads the model from Hugging Face (aufklarer/Kokoro-82M-CoreML), only on request.
    func download() async {
        guard !isReady else { return }
        if KokoroEngine.downloaded {
            await retry()
            return
        }
        state = .downloading(0)
        UserDefaults.standard.set(true, forKey: Self.openingKey)
        do {
            try await engine.load(offline: false, units: units.compute) { fraction in
                Task { @MainActor in
                    if case .downloading = KokoroVoice.shared.state { KokoroVoice.shared.state = .downloading(fraction) }
                }
            }
            UserDefaults.standard.set(false, forKey: Self.openingKey)
            state = .ready
        } catch {
            UserDefaults.standard.set(false, forKey: Self.openingKey)
            state = KokoroEngine.downloaded ? .onDisk : .failed("O download não terminou: \(error.localizedDescription)")
        }
    }

    /// Frees the space; the voice goes back to the server's or the iPhone's.
    func remove() async {
        await engine.unload()
        try? FileManager.default.removeItem(at: KokoroEngine.cacheDirectory)
        state = .absent
    }

    /// One sentence as WAV audio, ready for AVAudioPlayer.
    func audio(for sentence: String) async throws -> Data {
        try await engine.wav(sentence, voice: Self.voice)
    }
}

/// Owns the model (it is not thread-safe) and renders off the main thread.
actor KokoroEngine {
    private var model: KokoroTTSModel?

    static var cacheDirectory: URL {
        (try? HuggingFaceDownloader.getCacheDirectory(for: KokoroTTSModel.defaultModelId))
            ?? FileManager.default.temporaryDirectory.appendingPathComponent("kokoro")
    }

    static var downloaded: Bool {
        FileManager.default.fileExists(atPath: cacheDirectory.appendingPathComponent("vocab_index.json").path)
            && FileManager.default.fileExists(atPath: cacheDirectory.appendingPathComponent("voices/pf_dora.json").path)
    }

    func load(offline: Bool, units: MLComputeUnits, progress: @escaping @Sendable (Double) -> Void) async throws {
        guard model == nil else { return }
        model = try await KokoroTTSModel.fromPretrained(
            voice: KokoroVoice.voice, offlineMode: offline, computeUnits: units, warmUp: true,
            progressHandler: { fraction, _ in progress(fraction) }
        )
    }

    func unload() {
        model = nil
    }

    func wav(_ text: String, voice: String) throws -> Data {
        guard let model else { throw KokoroError.notLoaded }
        let samples = try model.synthesize(text: text, voice: voice, language: "pt")
        return WAV.encode(samples, sampleRate: 24_000)
    }
}

enum KokoroError: LocalizedError {
    case notLoaded
    var errorDescription: String? { "A voz Kokoro não está carregada." }
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
