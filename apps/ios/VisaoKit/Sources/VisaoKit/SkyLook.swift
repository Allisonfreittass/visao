import Foundation

/// How the "Neblina" forest looks at an hour: the same key hours and blend as
/// apps/web/src/sky/sky.ts, so the phone and the web show the same sky at the same time.
public struct SkyLook: Equatable, Sendable {
    public typealias RGB = SIMD3<Double>

    public var top: RGB
    public var mid: RGB
    public var low: RGB
    /// The light behind the fog (sun by day, moon at night).
    public var sunColor: RGB
    /// The fog itself.
    public var cloudColor: RGB
    /// The nearest pines; farther ones fade into the fog.
    public var tree: RGB
    /// How thick the fog is, 0...1.
    public var cloud: Double
    /// 0 day, 1 night (dark glass).
    public var night: Double
    /// Where the light sits, 0...1 of the screen (y up).
    public var sun: SIMD2<Double>

    /// The glass turns dark past half-night, as on the web.
    public var isNight: Bool { night > 0.5 }

    static func hex(_ value: UInt32) -> RGB {
        RGB(Double((value >> 16) & 255) / 255, Double((value >> 8) & 255) / 255, Double(value & 255) / 255)
    }

    private struct Key {
        let hour: Double
        let top: UInt32, mid: UInt32, low: UInt32, sunColor: UInt32, cloudColor: UInt32, tree: UInt32
        let cloud: Double, night: Double
    }

    private static let keys: [Key] = [
        Key(hour: 0, top: 0x141c26, mid: 0x1d2833, low: 0x24303b, sunColor: 0x7f93ad, cloudColor: 0x334250, tree: 0x070b0f, cloud: 0.8, night: 1),
        Key(hour: 5, top: 0x1f2a36, mid: 0x2e3a47, low: 0x3a4653, sunColor: 0x9aa3c0, cloudColor: 0x4a5664, tree: 0x0b1116, cloud: 0.9, night: 0.8),
        Key(hour: 6.5, top: 0xc9cdd6, mid: 0xb9bfca, low: 0xa8b0bb, sunColor: 0xf0d9c8, cloudColor: 0xc3c8d0, tree: 0x1d262e, cloud: 1, night: 0.1),
        Key(hour: 9, top: 0xe4e9eb, mid: 0xd3dbdf, low: 0xbcc7cd, sunColor: 0xffffff, cloudColor: 0xd4dce0, tree: 0x1e2b33, cloud: 0.95, night: 0),
        Key(hour: 15, top: 0xe1e7ea, mid: 0xcfd8dd, low: 0xb6c2c9, sunColor: 0xfbf6ee, cloudColor: 0xd0d9de, tree: 0x1c2a32, cloud: 0.85, night: 0),
        Key(hour: 18, top: 0xd8cfcf, mid: 0xc2b8bc, low: 0xa9a1a9, sunColor: 0xf3c9a8, cloudColor: 0xcdc2c3, tree: 0x22232b, cloud: 0.9, night: 0.15),
        Key(hour: 19.5, top: 0x4a4d5d, mid: 0x3d4352, low: 0x343b48, sunColor: 0xb49aa8, cloudColor: 0x545a6a, tree: 0x0d1116, cloud: 0.85, night: 0.7),
        Key(hour: 21, top: 0x161e28, mid: 0x1e2934, low: 0x25313c, sunColor: 0x7f93ad, cloudColor: 0x36444f, tree: 0x070b0f, cloud: 0.8, night: 1),
        Key(hour: 24, top: 0x141c26, mid: 0x1d2833, low: 0x24303b, sunColor: 0x7f93ad, cloudColor: 0x334250, tree: 0x070b0f, cloud: 0.8, night: 1),
    ]

    /// The forest at a local hour (0..<24, fractional; other values wrap).
    public static func at(hour: Double) -> SkyLook {
        let h = (hour.truncatingRemainder(dividingBy: 24) + 24).truncatingRemainder(dividingBy: 24)
        var i = 0
        while i < keys.count - 2 && keys[i + 1].hour <= h { i += 1 }
        let a = keys[i], b = keys[i + 1]
        let raw = (h - a.hour) / (b.hour - a.hour)
        let t = raw * raw * (3 - 2 * raw)
        func mix(_ x: Double, _ y: Double) -> Double { x + (y - x) * t }
        func mixRGB(_ x: UInt32, _ y: UInt32) -> RGB { hex(x) + (hex(y) - hex(x)) * t }
        // The light crosses from 6h to 18h behind the fog; at night the moon sits high and dim.
        let day = (h - 6) / 12
        let sun = (0...1).contains(day)
            ? SIMD2(0.12 + 0.76 * day, 0.55 + 0.35 * sin(Double.pi * day))
            : SIMD2(0.72, 0.85)
        return SkyLook(
            top: mixRGB(a.top, b.top), mid: mixRGB(a.mid, b.mid), low: mixRGB(a.low, b.low),
            sunColor: mixRGB(a.sunColor, b.sunColor), cloudColor: mixRGB(a.cloudColor, b.cloudColor),
            tree: mixRGB(a.tree, b.tree), cloud: mix(a.cloud, b.cloud), night: mix(a.night, b.night), sun: sun
        )
    }

    public static func localHour(_ date: Date = Date(), calendar: Calendar = .current) -> Double {
        let parts = calendar.dateComponents([.hour, .minute], from: date)
        return Double(parts.hour ?? 0) + Double(parts.minute ?? 0) / 60
    }
}
