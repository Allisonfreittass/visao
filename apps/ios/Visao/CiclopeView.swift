import SwiftUI

/// What the Ciclope shows (apps/web/src/ciclope/state.ts). "interrupted" is the listening pose
/// after one quick blink.
enum CiclopeState: Equatable {
    case idle, listening, thinking, speaking, working, error, offline, interrupted

    var label: String {
        switch self {
        case .idle: "à toa"
        case .listening: "ouvindo"
        case .thinking: "pensando"
        case .speaking: "falando"
        case .working: "agindo no Mac"
        case .error: "algo deu errado"
        case .offline: "desconectado"
        case .interrupted: "interrompido"
        }
    }
}

/// The pose of a state, in the SVG's units (a 100 × 100 box), as in apps/web/src/ciclope/model.ts.
struct CiclopePose: Equatable {
    var irisX: Double = 0
    var irisY: Double = 0
    var iris: Double = 1
    var pupil: Double = 1
    var lid: Double = 0
    var lidTilt: Double = 0
    var sclera: Double = 1
    var gray: Double = 0
    var ring: Double = 0
    var smile: Double = 1

    static func of(_ state: CiclopeState) -> CiclopePose {
        switch state {
        case .idle: CiclopePose()
        case .listening, .interrupted: CiclopePose(pupil: 1.05, sclera: 1.06)
        case .thinking: CiclopePose(irisX: 2, irisY: -6, lid: 0.2)
        case .speaking: CiclopePose(iris: 10.5 / 11.5)
        case .working: CiclopePose(lid: 0.35, ring: 1)
        case .error: CiclopePose(irisX: -1, irisY: 3, lid: 0.4, lidTilt: -18, smile: -0.8)
        case .offline: CiclopePose(lid: 1, gray: 0.6, smile: 0.5)
        }
    }
}

/// The Ciclope: the orange block with one big eye, the assistant's presence. It shows the state
/// with the eye: it blinks and looks around at rest, opens wide to listen, looks up to think,
/// pulses with the voice, squints at work on the Mac (with a ring turning around it), droops when
/// something fails and sleeps offline. Reduce Motion: no loops and no following, only the pose.
struct CiclopeView: View {
    var state: CiclopeState
    var size: CGFloat = 96
    /// Voice level 0...1 (speaking, listening).
    var level: Double = 0
    /// Where to look, -1...1 on each axis (a touch, the gyroscope); nil looks around by itself.
    var look: CGPoint? = nil
    /// false: one still pose (small avatars in a list).
    var animated = true
    /// Closes the eye on purpose (the login while the password is typed).
    var eyesClosed = false

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pose = CiclopePose()
    @State private var since = Date()
    @State private var appeared = Date()
    @State private var lookPoint = CGPoint.zero

    private static let accent = Palette.accentColor
    private static let iris = Color(rgb: 0x1b1e3a)
    private static let irisRing = Color(rgb: 0x3e4890)
    private static let muted = Color(rgb: 0xba7e5e)

    private var still: Bool { reduceMotion || !animated }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: still)) { context in
            figure(at: context.date)
        }
        .frame(width: size, height: size)
        .onChange(of: target, initial: true) { _, next in
            if still {
                pose = next
            } else {
                withAnimation(.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.24)) { pose = next }
            }
        }
        .onChange(of: state) { _, _ in since = Date() }
        .onChange(of: look) { _, next in
            let goal = still || state == .thinking || state == .offline ? .zero : (next ?? .zero)
            withAnimation(.interpolatingSpring(stiffness: 170, damping: 22)) { lookPoint = goal }
        }
        .accessibilityElement()
        .accessibilityLabel("V.I.S.A.O., \(state.label)")
    }

    private var target: CiclopePose {
        var p = CiclopePose.of(state)
        if eyesClosed { p.lid = 1 }
        return p
    }

    // MARK: - One frame

    private func figure(at date: Date) -> some View {
        let t = date.timeIntervalSince(appeared)
        let sinceState = date.timeIntervalSince(since)
        let u = size / 100
        var p = pose
        let lv = still ? 0 : min(max(level, 0), 1)
        if state == .speaking { p.iris = (10.5 + 2 * lv) / 11.5 }
        if state == .listening || state == .interrupted { p.pupil += 0.5 * lv }
        let mouth = state == .speaking ? lv : 0
        let blink = still || eyesClosed || state == .offline || state == .thinking ? 0 : blinkAmount(t, sinceState: sinceState)
        let lid = max(p.lid, blink)
        let wander = still || state != .idle ? CGPoint.zero : wanderOffset(t)
        let lx = Double(wander.x + lookPoint.x * 5), ly = Double(wander.y + lookPoint.y * 5)
        let breathe = !still && (state == .listening || state == .interrupted) ? 1 + 0.015 * (1 - cos(t / 1.2 * 2 * .pi)) : 1
        let rotate = !still && state == .thinking ? 2 * sin(t / 2.4 * 2 * .pi) : 0
        let shake = !still && state == .error && sinceState < 0.36 ? 2 * sin(sinceState / 0.12 * 2 * .pi) * (1 - sinceState / 0.36) : 0
        let spin = still ? 0 : (t / 1.6 * 360).truncatingRemainder(dividingBy: 360)
        let eyeOpacity = 1 - max(0, (lid - 0.86) / 0.14)

        return ZStack {
            // Working: a thin orange ring turning around the body.
            UnitCircle(cx: 50, cy: 50, r: 62)
                .trim(from: 0, to: 0.18)
                .stroke(Self.accent, style: StrokeStyle(lineWidth: 2.5 * u, lineCap: .round))
                .rotationEffect(.degrees(spin))
                .opacity(p.ring)

            ZStack {
                UnitRoundedRect(r: 23).fill(Self.accent)
                UnitRoundedRect(r: 23).fill(Self.muted).opacity(p.gray / 0.6)
                UnitRoundedRect(r: 23).fill(Self.shade)
                // eye
                UnitCircle(cx: 50, cy: 49, r: 22).fill(.black.opacity(0.2 * (1 - max(0, (lid - 0.8) / 0.2))))
                ZStack {
                    UnitCircle(cx: 50, cy: 46, r: 22).fill(.white)
                    UnitCircle(cx: 50, cy: 46, r: 22).fill(Self.sclera(u))
                    ZStack {
                        ZStack {
                            UnitCircle(cx: 53, cy: 43, r: 11.5).fill(Self.iris)
                            UnitCircle(cx: 53, cy: 43, r: 10.5).stroke(Self.irisRing, lineWidth: 2 * u)
                            UnitCircle(cx: 53, cy: 43, r: 5).fill(Color(rgb: 0x05060c))
                                .scaleEffect(p.pupil, anchor: UnitPoint(x: 0.53, y: 0.43))
                            UnitCircle(cx: 57, cy: 39, r: 3).fill(.white)
                        }
                        .scaleEffect(p.iris, anchor: UnitPoint(x: 0.53, y: 0.43))
                        .offset(x: (p.irisX + lx) * u, y: (p.irisY + ly) * u)
                        // eyelid: body-colored, it comes down to blink, squint and sleep
                        ZStack {
                            Lid().fill(Self.accent)
                            Lid().fill(Self.shade).offset(y: -lid * 54 * u)
                                .mask(Lid())
                            LidEdge().stroke(.black.opacity(0.28), lineWidth: 2 * u)
                        }
                        .offset(y: lid * 54 * u)
                        .rotationEffect(.degrees(p.lidTilt * (1 - lid)), anchor: UnitPoint(x: 0.5, y: 0.46))
                    }
                    .clipShape(UnitCircle(cx: 50, cy: 46, r: 22))
                }
                .scaleEffect(p.sclera, anchor: UnitPoint(x: 0.5, y: 0.46))
                .opacity(eyeOpacity)
                // asleep: the closed eye is a curved line
                ClosedEye().stroke(.black.opacity(0.5), style: StrokeStyle(lineWidth: 3 * u, lineCap: .round))
                    .opacity(max(0, (lid - 0.92) / 0.08))
                // mouth
                Smile().stroke(.black.opacity(0.45), style: StrokeStyle(lineWidth: 3.2 * u, lineCap: .round))
                    .scaleEffect(x: 1, y: p.smile, anchor: UnitPoint(x: 0.5, y: 0.795))
                UnitEllipse(cx: 50, cy: 78, rx: 6, ry: 4).fill(.black.opacity(0.45))
                    .scaleEffect(x: 1, y: max(0.001, mouth), anchor: UnitPoint(x: 0.5, y: 0.78))
                    .opacity(mouth > 0.02 ? 1 : 0)
                UnitRoundedRect(r: 22.4, inset: 0.75).stroke(.white.opacity(0.16), lineWidth: 1.5 * u)
            }
            .scaleEffect(breathe)
            .rotationEffect(.degrees(rotate))
            .offset(x: shake * u)
        }
        .frame(width: size, height: size)
    }

    /// A blink every 3–6 s (close 120 ms, open 160 ms), plus one right away when interrupted.
    private func blinkAmount(_ t: Double, sinceState: Double) -> Double {
        if state == .interrupted, sinceState < 0.28 { return amount(sinceState) }
        let cycle = 4.5
        let k = floor(t / cycle)
        let at = k * cycle + Self.hash(k) * 1.5
        return amount(t - at)
    }

    private func amount(_ s: Double) -> Double {
        if s < 0 || s >= 0.28 { return 0 }
        return s < 0.12 ? s / 0.12 : 1 - (s - 0.12) / 0.16
    }

    /// Looking around at rest: a new spot every ~4 s, eased over 0.6 s, up to 3 units.
    private func wanderOffset(_ t: Double) -> CGPoint {
        let period = 4.0
        let k = floor(t / period)
        func spot(_ i: Double) -> CGPoint {
            CGPoint(x: (Self.hash(i * 3 + 1) * 2 - 1) * 3, y: (Self.hash(i * 7 + 2) * 2 - 1) * 2.1)
        }
        let a = spot(k - 1), b = spot(k)
        let s = min(1, (t - k * period) / 0.6)
        let e = 0.5 - 0.5 * cos(s * .pi)
        return CGPoint(x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e)
    }

    private static func hash(_ x: Double) -> Double {
        let v = sin(x * 127.1 + 311.7) * 43758.5453
        return v - floor(v)
    }

    private static let shade = LinearGradient(
        stops: [
            .init(color: .white.opacity(0.32), location: 0),
            .init(color: .white.opacity(0), location: 0.45),
            .init(color: .black.opacity(0.32), location: 1),
        ],
        startPoint: .top, endPoint: .bottom
    )

    /// The eye's soft inner shadow, placed on the eye (its box is 28...72 × 24...68).
    private static func sclera(_ u: CGFloat) -> RadialGradient {
        RadialGradient(
            stops: [.init(color: .black.opacity(0), location: 0.6), .init(color: .black.opacity(0.18), location: 1)],
            center: UnitPoint(x: 0.465, y: 0.407), startRadius: 0, endRadius: 0.65 * 44 * u
        )
    }
}

// MARK: - Shapes in the SVG's 100 × 100 box, scaled to the frame

private struct UnitCircle: Shape {
    let cx: Double, cy: Double, r: Double
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        return Path(ellipseIn: CGRect(x: (cx - r) * k, y: (cy - r) * k, width: 2 * r * k, height: 2 * r * k))
    }
}

private struct UnitEllipse: Shape {
    let cx: Double, cy: Double, rx: Double, ry: Double
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        return Path(ellipseIn: CGRect(x: (cx - rx) * k, y: (cy - ry) * k, width: 2 * rx * k, height: 2 * ry * k))
    }
}

private struct UnitRoundedRect: Shape {
    let r: Double
    var inset: Double = 0
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        return Path(roundedRect: rect.insetBy(dx: inset * k, dy: inset * k), cornerRadius: r * k, style: .circular)
    }
}

private struct Lid: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 20 * k, y: -40 * k))
        p.addLine(to: CGPoint(x: 80 * k, y: -40 * k))
        p.addLine(to: CGPoint(x: 80 * k, y: 14 * k))
        p.addQuadCurve(to: CGPoint(x: 20 * k, y: 14 * k), control: CGPoint(x: 50 * k, y: 22 * k))
        p.closeSubpath()
        return p
    }
}

private struct LidEdge: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 24 * k, y: 14.6 * k))
        p.addQuadCurve(to: CGPoint(x: 76 * k, y: 14.6 * k), control: CGPoint(x: 50 * k, y: 22 * k))
        return p
    }
}

private struct ClosedEye: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 31 * k, y: 47 * k))
        p.addQuadCurve(to: CGPoint(x: 69 * k, y: 47 * k), control: CGPoint(x: 50 * k, y: 59 * k))
        return p
    }
}

private struct Smile: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 42 * k, y: 77 * k))
        p.addQuadCurve(to: CGPoint(x: 58 * k, y: 77 * k), control: CGPoint(x: 50 * k, y: 82 * k))
        return p
    }
}

#Preview {
    VStack(spacing: 24) {
        HStack(spacing: 24) {
            CiclopeView(state: .idle, size: 80)
            CiclopeView(state: .thinking, size: 80)
            CiclopeView(state: .working, size: 80)
        }
        HStack(spacing: 24) {
            CiclopeView(state: .error, size: 80)
            CiclopeView(state: .offline, size: 80)
            CiclopeView(state: .speaking, size: 80, level: 0.7)
        }
    }
    .padding(40)
}
