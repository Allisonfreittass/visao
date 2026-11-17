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
