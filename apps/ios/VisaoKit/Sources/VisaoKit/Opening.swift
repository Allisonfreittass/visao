import Foundation

/// The opening (Intro.tsx on the web, a 1.6 s boot sequence on the iPhone): once a day on this
/// device, never with Reduce Motion, and only when the app is ready to use (not on the login or
/// the first-run questions).
public enum Opening {
    public static let duration: Double = 1.6
    static let dayKey = "openingDay"

    /// "Bom dia" from 5 h to 12 h, "Boa tarde" to 18 h, "Boa noite" the rest.
    public static func greeting(hour: Int) -> String {
        if hour >= 5 && hour < 12 { return "Bom dia" }
        if hour >= 12 && hour < 18 { return "Boa tarde" }
        return "Boa noite"
    }

    public static func greeting(at date: Date = Date(), calendar: Calendar = .current) -> String {
        greeting(hour: calendar.component(.hour, from: date))
    }

    /// The local day, "2026-11-17".
    public static func localDay(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    public static func shouldPlay(now: Date, lastDay: String?, reduceMotion: Bool, calendar: Calendar = .current) -> Bool {
        !reduceMotion && lastDay != localDay(now, calendar: calendar)
    }

    /// Whether it plays now; when it does, today is marked so it does not play again.
    public static func takeTurn(now: Date = Date(), reduceMotion: Bool, defaults: UserDefaults = .standard, calendar: Calendar = .current) -> Bool {
        guard shouldPlay(now: now, lastDay: defaults.string(forKey: dayKey), reduceMotion: reduceMotion, calendar: calendar) else { return false }
        defaults.set(localDay(now, calendar: calendar), forKey: dayKey)
        return true
    }
}
