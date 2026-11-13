import Foundation

/// API timestamps are UTC. Pydantic writes microseconds, and older SQLite rows come without an
/// offset ("2026-11-13T12:00:00.123456"): those are UTC too, as in `utcDate` on the web.
public enum APIDate {
    public static func parse(_ value: String) -> Date? {
        var text = value.trimmingCharacters(in: .whitespaces)
        if text.hasSuffix("Z") || text.hasSuffix("z") {
            text.removeLast()
            text += "+00:00"
        } else if !hasOffset(text) {
            text += "+00:00"
        }
        // ISO8601DateFormatter takes at most milliseconds: cut longer fractions to three digits.
        if let dot = text.firstIndex(of: ".") {
            let fractionEnd = text[dot...].dropFirst().firstIndex(where: { !$0.isNumber }) ?? text.endIndex
            let digits = text[text.index(after: dot)..<fractionEnd]
            let kept = String(digits.prefix(3)).padding(toLength: 3, withPad: "0", startingAt: 0)
            text = String(text[..<dot]) + "." + kept + String(text[fractionEnd...])
            return withFraction.date(from: text)
        }
        return plain.date(from: text)
    }

    private static func hasOffset(_ text: String) -> Bool {
        // ...T12:00:00+03:00 or -03:00, after the time part.
        guard let tee = text.firstIndex(of: "T") else { return false }
        return text[tee...].contains("+") || text[tee...].contains("-")
    }

    nonisolated(unsafe) private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    nonisolated(unsafe) private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    public static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parse(raw) else {
                throw DecodingError.dataCorruptedError(in: container, debugDescription: "Data inválida: \(raw)")
            }
            return date
        }
        return d
    }()
}

/// "Hoje, 14:05", "Ontem, 09:12", "03/11, 18:00", as in apps/web/src/labels.ts.
public enum DayLabel {
    public static func text(for date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        let time = date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(locale))
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: date), to: calendar.startOfDay(for: now)).day ?? 0
        if days == 0 { return "Hoje, \(time)" }
        if days == 1 { return "Ontem, \(time)" }
        let sameYear = calendar.component(.year, from: date) == calendar.component(.year, from: now)
        var style = Date.FormatStyle(date: .omitted, time: .omitted).locale(locale)
        style = sameYear ? style.day(.twoDigits).month(.twoDigits) : style.day(.twoDigits).month(.twoDigits).year(.twoDigits)
        return "\(date.formatted(style)), \(time)"
    }

    static let locale = Locale(identifier: "pt_BR")
}
