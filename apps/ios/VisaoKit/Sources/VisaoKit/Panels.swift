import Foundation

// Live panels on Início (docs/PAINEIS.md, ADR-0012): native cards the server keeps up to date. The
// server computes the totals and the distance to the goal; the app only shows them.

public struct PanelItem: Codable, Sendable, Hashable {
    public let kind: String
    public let provider: String
    public let `where`: String
    public let dates: String
    public let connections: Int?
    public let price: String?
    /// What it costs the whole party.
    public let cost: String?
    public let site: String
    public let url: String

    enum CodingKeys: String, CodingKey {
        case kind, provider, `where`, dates, connections, price, cost, site, url
    }
}

public struct PanelPoint: Codable, Sendable, Hashable {
    public let total: String?
    public let checkedAt: Date

    enum CodingKeys: String, CodingKey {
        case total
        case checkedAt = "checked_at"
    }
}

public struct LivePanel: Codable, Sendable, Identifiable, Hashable {
    public struct Spec: Codable, Sendable, Hashable {
        public let travelers: Int?
        public let destination: String?
    }

    public let id: String
    public let title: String
    /// "active", "paused", "error" or "expired".
    public let status: String
    public let spec: Spec
    public let total: String?
    public let goal: String?
    public let goalGap: String?
    /// "R$ 555 acima da meta de R$ 6.000", written by the server.
    public let goalWords: String?
    public let change: String?
    public let items: [PanelItem]
    public let checkedAt: Date?
    /// False: the numbers are from an earlier day; the card says when, never "agora".
    public let checkedToday: Bool
    public let note: String
    public let history: [PanelPoint]?
    /// Near the goal it checks every few hours (3); nil: once a day (ADR-0016).
    public let watchEveryHours: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, status, spec, total, goal, change, items, note, history
        case watchEveryHours = "watch_every_hours"
        case goalGap = "goal_gap"
        case goalWords = "goal_words"
        case checkedAt = "checked_at"
        case checkedToday = "checked_today"
    }

    public var isBelowGoal: Bool { (goalGap.flatMap { Decimal(string: $0) } ?? 0) < 0 }
    public var changeValue: Decimal { change.flatMap { Decimal(string: $0) } ?? 0 }
    public var totalValue: Double? { total.flatMap(Double.init) }
}

public struct PanelSuggestion: Codable, Sendable, Hashable {
    public let text: String
    public let draft: String
}

public enum PanelText {
    private static let formatter: NumberFormatter = {
        let f = NumberFormatter()
        f.locale = Locale(identifier: "pt_BR")
        f.numberStyle = .currency
        f.currencyCode = "BRL"
        return f
    }()

    /// "R$ 5.945" from the server's decimal string.
    public static func brl(_ value: String?) -> String? {
        guard let value, let number = Decimal(string: value) else { return nil }
        let whole = number == number.rounded()
        formatter.maximumFractionDigits = whole ? 0 : 2
        formatter.minimumFractionDigits = whole ? 0 : 2
        return formatter.string(from: number as NSDecimalNumber)?.replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    /// "perto da meta: confiro a cada 3 h", next to when it was checked; nothing when paused or
    /// once a day (watchLabel in PanelsBoard.tsx).
    public static func watch(_ panel: LivePanel) -> String? {
        guard panel.status != "paused", let hours = panel.watchEveryHours, hours > 0 else { return nil }
        return "perto da meta: confiro a cada \(hours) h"
    }

    /// When it was checked; a number from another day never reads as today's.
    public static func checked(_ panel: LivePanel, calendar: Calendar = .current) -> String {
        guard let at = panel.checkedAt else { return "ainda não conferido" }
        let time = at.formatted(date: .omitted, time: .shortened)
        if panel.checkedToday { return "conferido hoje, \(time)" }
        let day = at.formatted(.dateTime.day(.twoDigits).month(.twoDigits))
        return "conferido em \(day), \(time) · não conferido hoje"
    }
}

extension Decimal {
    func rounded() -> Decimal {
        var source = self
        var result = Decimal()
        NSDecimalRound(&result, &source, 0, .plain)
        return result
    }
}

extension APIClient {
    public func panels() async throws -> [LivePanel] {
        try await request("/panels")
    }

    public func panel(id: String) async throws -> LivePanel {
        try await request("/panels/\(id)")
    }

    public func panelSuggestions() async throws -> [PanelSuggestion] {
        try await request("/panels/suggestions")
    }

    public func setPanel(id: String, paused: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["status": paused ? "paused" : "active"])
        _ = try await raw("/panels/\(id)", method: "PATCH", body: body, contentType: "application/json")
    }

    public func deletePanel(id: String) async throws {
        _ = try await raw("/panels/\(id)", method: "DELETE")
    }
}
