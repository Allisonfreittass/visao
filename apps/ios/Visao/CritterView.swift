import SwiftUI

/// A mini character of the Ciclope's family (apps/web/src/ciclope/Family.tsx): one per
/// integration (Mac, WhatsApp, e-mail, Caderno) and one per project, flat, with one big eye.
struct CritterView: View {
    enum Kind {
        case mac, whatsapp, email, caderno, projeto

        var color: Color {
            switch self {
            case .mac: Color(rgb: 0x3b6bff)
            case .whatsapp: Color(rgb: 0x18c27a)
            case .email: Color(rgb: 0xffc83d)
            case .caderno, .projeto: Color(rgb: 0x9b87ff)
            }
        }

        /// The eye, in the 100 × 100 box.
        var eye: (cx: Double, cy: Double, r: Double) {
            switch self {
            case .mac: (50, 44, 19)
            case .whatsapp: (51, 47, 20)
            case .email: (50, 58, 17)
            case .caderno: (50, 50, 19)
            case .projeto: (50, 47, 21)
            }
        }
    }

    var kind: Kind
    var size: CGFloat = 24
    /// For a project: its color (`projectColor(name)`).
    var color: Color? = nil
    /// The Mac offline: the eye is a closed line.
    var asleep = false

    private static let projectColors: [UInt32] = [0xff6a1a, 0x3b6bff, 0x18c27a, 0xffc83d, 0x9b87ff, 0xff5c8a, 0x14b8c4]

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
        let (cx, cy, r) = kind.eye
        let ir = r * 0.52
        let ix = cx + 0.25 * r * 0.28, iy = cy - 0.2 * r * 0.28
        ZStack {
            CritterBody(kind: kind).fill(color ?? kind.color)
            CritterBody(kind: kind).fill(LinearGradient(
                stops: [.init(color: .white.opacity(0.3), location: 0), .init(color: .white.opacity(0), location: 0.45), .init(color: .black.opacity(0.28), location: 1)],
                startPoint: .top, endPoint: .bottom
            ))
            CritterExtra(kind: kind).stroke(.black.opacity(0.22), style: StrokeStyle(lineWidth: 3 * u, lineCap: .round, lineJoin: .round))
            if asleep {
                Path { p in
                    p.move(to: CGPoint(x: (cx - r * 0.7) * u, y: cy * u))
                    p.addQuadCurve(to: CGPoint(x: (cx + r * 0.7) * u, y: cy * u), control: CGPoint(x: cx * u, y: (cy + r * 0.55) * u))
                }
                .stroke(.black.opacity(0.5), style: StrokeStyle(lineWidth: 4 * u, lineCap: .round))
            } else {
                dot(cx, cy + 2.5, r, .black.opacity(0.18), u)
                dot(cx, cy, r, .white, u)
                dot(ix, iy, ir, Color(rgb: 0x1b1e3a), u)
                dot(ix, iy, ir * 0.45, Color(rgb: 0x05060c), u)
                dot(ix + ir * 0.38, iy - ir * 0.38, ir * 0.27, .white, u)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private func dot(_ x: Double, _ y: Double, _ r: Double, _ color: Color, _ u: CGFloat) -> some View {
        Circle().fill(color)
            .frame(width: 2 * r * u, height: 2 * r * u)
            .position(x: x * u, y: y * u)
    }
}

private struct CritterBody: Shape {
    let kind: CritterView.Kind

    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        func pt(_ x: Double, _ y: Double) -> CGPoint { CGPoint(x: x * k, y: y * k) }
        var p = Path()
        switch kind {
        case .mac:
            p.addRoundedRect(in: CGRect(x: 2 * k, y: 12 * k, width: 96 * k, height: 66 * k), cornerSize: CGSize(width: 12 * k, height: 12 * k))
            p.move(to: pt(40, 78)); p.addLine(to: pt(60, 78)); p.addLine(to: pt(63, 90)); p.addLine(to: pt(37, 90)); p.closeSubpath()
            p.addRoundedRect(in: CGRect(x: 24 * k, y: 90 * k, width: 52 * k, height: 8 * k), cornerSize: CGSize(width: 4 * k, height: 4 * k))
        case .whatsapp:
            p.move(to: pt(50, 6))
            p.addCurve(to: pt(96, 48), control1: pt(76, 6), control2: pt(96, 24))
            p.addCurve(to: pt(50, 90), control1: pt(96, 72), control2: pt(76, 90))
            p.addCurve(to: pt(29, 85), control1: pt(42, 90), control2: pt(35, 88))
            p.addLine(to: pt(8, 94)); p.addLine(to: pt(15, 74))
            p.addCurve(to: pt(4, 48), control1: pt(8, 67), control2: pt(4, 58))
            p.addCurve(to: pt(50, 6), control1: pt(4, 24), control2: pt(24, 6))
            p.closeSubpath()
        case .email:
            p.addRoundedRect(in: CGRect(x: 2 * k, y: 18 * k, width: 96 * k, height: 72 * k), cornerSize: CGSize(width: 14 * k, height: 14 * k))
        case .caderno:
            p.move(to: pt(20, 2)); p.addLine(to: pt(66, 2)); p.addLine(to: pt(90, 26)); p.addLine(to: pt(90, 88))
            p.addQuadCurve(to: pt(80, 98), control: pt(90, 98))
            p.addLine(to: pt(20, 98))
            p.addQuadCurve(to: pt(10, 88), control: pt(10, 98))
            p.addLine(to: pt(10, 12))
            p.addQuadCurve(to: pt(20, 2), control: pt(10, 2))
            p.closeSubpath()
        case .projeto:
            p.addRoundedRect(in: CGRect(x: 4 * k, y: 4 * k, width: 92 * k, height: 92 * k), cornerSize: CGSize(width: 28 * k, height: 28 * k), style: .continuous)
        }
        return p
    }
}

private struct CritterExtra: Shape {
    let kind: CritterView.Kind

    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        switch kind {
        case .email:
            p.move(to: CGPoint(x: 8 * k, y: 26 * k)); p.addLine(to: CGPoint(x: 50 * k, y: 52 * k)); p.addLine(to: CGPoint(x: 92 * k, y: 26 * k))
        case .caderno:
            p.move(to: CGPoint(x: 66 * k, y: 2 * k)); p.addLine(to: CGPoint(x: 66 * k, y: 20 * k))
            p.addQuadCurve(to: CGPoint(x: 72 * k, y: 26 * k), control: CGPoint(x: 66 * k, y: 26 * k))
            p.addLine(to: CGPoint(x: 90 * k, y: 26 * k))
        default:
            break
        }
        return p
    }
}
