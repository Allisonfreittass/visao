import Foundation

/// The phone's position, sent only with a "perto de mim" message (docs/LOCALIZACAO.md, ADR-0020).
/// It is never stored, on the phone or on the server.
public struct SentLocation: Encodable, Sendable, Equatable {
    public let lat: Double
    public let lon: Double
    public let accuracyM: Double?
    public let at: Date

    public init(lat: Double, lon: Double, accuracyM: Double?, at: Date) {
        self.lat = lat
        self.lon = lon
        self.accuracyM = accuracyM
        self.at = at
    }

    enum CodingKeys: String, CodingKey {
        case lat, lon, at
        case accuracyM = "accuracy_m"
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(lat, forKey: .lat)
        try c.encode(lon, forKey: .lon)
        try c.encodeIfPresent(accuracyM, forKey: .accuracyM)
        // ISO 8601 in UTC, as the web sends it.
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(identifier: "UTC")
        try c.encode(formatter.string(from: at), forKey: .at)
    }
}

/// Whether a message asks about somewhere near (NEARBY in apps/web/src/location.ts, the same
/// idea as core/location.py): "perto do Natal" and "daqui a pouco" are not about a place.
public enum Nearby {
    private static let pattern = #"\bperto (daqui|de mim|de onde (eu )?(estou|to))\b|\bperto\s*[?!.]*\s*$|\bmais perto\b|\baqui perto\b|\bpertinho\b|\bpor aqui\b|\baqui (do lado|na rua|no bairro|na regiao)\b|\bmais proxim[oa]s? (daqui|de mim)\b|\b(na|nessa|nesta) (minha )?regiao\b|\bao (meu )?redor\b|\bnos arredores\b|\bonde (eu )?(estou|to) agora\b"#
    nonisolated(unsafe) private static let regex = try! NSRegularExpression(pattern: pattern)

    /// Without accents and in lower case, as the web folds it.
    static func fold(_ text: String) -> String {
        text.folding(options: [.diacriticInsensitive], locale: Locale(identifier: "pt_BR")).lowercased()
    }

    public static func asks(_ text: String) -> Bool {
        guard text.count <= 1000 else { return false }
        let folded = fold(text)
        return regex.firstMatch(in: folded, range: NSRange(folded.startIndex..., in: folded)) != nil
    }
}

/// Where a position comes from: the phone in the app, a fake in the tests.
public protocol PositionSource: Sendable {
    func current() async -> SentLocation?
}

/// "Usar minha localização": off by default, kept on this device only (the App Group's defaults,
/// so the share extension sees the same switch).
public enum LocationPrefs {
    static let key = "useLocation"

    public static func enabled(in defaults: UserDefaults = SharedConfig.main.defaults) -> Bool {
        defaults.bool(forKey: key)
    }

    public static func set(_ on: Bool, in defaults: UserDefaults = SharedConfig.main.defaults) {
        defaults.set(on, forKey: key)
    }

    /// The position to send with this message: only with the switch on and a "perto de mim"
    /// message; otherwise the source is never asked.
    public static func position(for text: String, enabled: Bool, source: PositionSource) async -> SentLocation? {
        guard enabled, Nearby.asks(text) else { return nil }
        return await source.current()
    }
}
