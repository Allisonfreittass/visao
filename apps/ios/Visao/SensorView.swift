import SwiftUI

/// A sensor (apps/web/src/ciclope/Family.tsx): the mascot's family, one per integration and one
/// per project. A graphite block with a colored rim and one colored eye; the eye goes dark
/// (opacity .2) when the integration is disconnected.
struct SensorView: View {
    enum Kind {
        case mac, whatsapp, email, caderno, projeto

        var color: Color {
            switch self {
            case .mac: Color(rgb: 0x3b6bff)
            case .whatsapp: Color(rgb: 0x18c27a)
            case .email: Color(rgb: 0xe0a800)
            case .caderno, .projeto: Color(rgb: 0x9b87ff)
            }
        }
    }

    var kind: Kind
    var size: CGFloat = 24
    /// For a project: its color (`projectColor(name)`).
    var color: Color? = nil
    /// Disconnected: the eye goes dark.
    var asleep = false

    private static let projectColors: [UInt32] = [0x3b6bff, 0x18c27a, 0xe0a800, 0x9b87ff, 0x14b8c4, 0x8e9aaf]

    /// The same color for the same name, always (FNV-1a, as on the web).
    static func projectColor(_ name: String) -> Color {
        var h: UInt32 = 2_166_136_261
        for unit in name.trimmingCharacters(in: .whitespaces).lowercased().utf16 {
            h ^= UInt32(unit)
            h = h &* 16_777_619
        }
        let slot = Double(h % 10_000) / 10_000
        return Color(rgb: projectColors[Int(slot * Double(projectColors.count))])
    }

    var body: some View {
        let u = size / 100
        let tint = color ?? kind.color
        ZStack {
            RoundedRectangle(cornerRadius: 30 * u, style: .circular).fill(Color(rgb: 0x24252b))
            RoundedRectangle(cornerRadius: 28 * u, style: .circular)
                .strokeBorder(tint.opacity(0.6), lineWidth: 4 * u)
            Circle().fill(Palette.socket).frame(width: 48 * u, height: 48 * u)
            ZStack {
                Circle().fill(tint).frame(width: 22 * u, height: 22 * u)
                Circle().fill(Palette.socket).frame(width: 9 * u, height: 9 * u)
            }
            .opacity(asleep ? 0.2 : 1)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// Older call sites use the family's first name.
typealias CritterView = SensorView
