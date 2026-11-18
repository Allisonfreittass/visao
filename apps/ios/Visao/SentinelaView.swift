import SwiftUI

/// What the mascot shows (apps/web/src/ciclope/state.ts). "interrupted" is the listening pose
/// after one mechanical blink.
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

/// The pose of a state in the SVG's units (apps/web/src/ciclope/model.ts): the body is the
/// 100 × 100 box, the eye the circle at 50,46 r 23.
struct SentinelaPose: Equatable {
    /// Upper lid: y at the sides and in the middle (middle lower = an alert V).
    var lidSide: Double = 35
    var lidMid: Double = 35
    /// Lower lid's top edge (76 = out of the eye).
    var lowerLid: Double = 76
    var irisX: Double = 0
    var irisY: Double = 0
    var ring: Double = 1
    var core: Double = 1
    var glow: Double = 0.7
    var iris: Double = 1
    var body: Double = 1
    var outer: Double = 0

    static let shut: Double = 54

    static func of(_ state: CiclopeState) -> SentinelaPose {
        switch state {
        case .idle, .speaking: SentinelaPose()
        case .listening, .interrupted: SentinelaPose(lidSide: 30, lidMid: 30)
        case .thinking: SentinelaPose(lidSide: 37, lidMid: 37, irisY: -4)
        case .working: SentinelaPose(lidSide: 37, lidMid: 47, glow: 1, outer: 1)
        case .error: SentinelaPose(lidSide: 37, lidMid: 50, glow: 1)
        case .offline: SentinelaPose(lidSide: shut, lidMid: shut, lowerLid: shut, glow: 0, iris: 0.15, body: 0.7)
        }
    }

    /// "Fresta": a 6-unit red slit left.
    func slit() -> SentinelaPose {
        var p = self
        p.lidSide = 51; p.lidMid = 51; p.lowerLid = 57
        return p
    }

    func shut(by k: Double) -> SentinelaPose {
        guard k > 0 else { return self }
        var p = self
        p.lidSide += (Self.shut - p.lidSide) * k
        p.lidMid += (Self.shut - p.lidMid) * k
        p.lowerLid += (Self.shut - p.lowerLid) * k
        return p
    }
}

/// The mascot, "Ciclope Sentinela": a graphite block with one red sensor eye under a metal lid,
/// a power LED and a speaker grille. It shows the assistant's state with the eye. Reduce Motion:
/// no loops, no following, no ring turning; only the pose changes.
struct SentinelaView: View {
    var state: CiclopeState
    var size: CGFloat = 96
    /// Voice level 0...1 (speaking, listening).
    var level: Double = 0
    /// Where to look, -1...1 on each axis (a touch, the gyroscope).
    var look: CGPoint? = nil
    /// false: one still pose (small avatars in a list).
    var animated = true
    /// "Fresta" on purpose (the login while the password is typed).
    var eyesClosed = false

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pose = SentinelaPose()
    @State private var since = Date()
    @State private var appeared = Date()
    @State private var lookPoint = CGPoint.zero

    private var still: Bool { reduceMotion || !animated }
    private var tiny: Bool { size < 32 }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 60, paused: still)) { context in
            figure(at: context.date)
        }
        .frame(width: size, height: size)
        .onChange(of: target, initial: true) { _, next in
            if still {
                pose = next
            } else {
                withAnimation(.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.22)) { pose = next }
            }
        }
        .onChange(of: state) { _, _ in since = Date() }
        .onChange(of: look) { _, next in
            let fixed = still || [.thinking, .offline, .working, .error].contains(state) || eyesClosed
            withAnimation(.interpolatingSpring(stiffness: 200, damping: 26)) { lookPoint = fixed ? .zero : (next ?? .zero) }
        }
        .accessibilityElement()
        .accessibilityLabel("V.I.S.A.O., \(state.label)")
    }

    private var target: SentinelaPose {
        let p = SentinelaPose.of(state)
        return eyesClosed ? p.slit() : p
    }

    // MARK: - One frame

    private func figure(at date: Date) -> some View {
        let t = date.timeIntervalSince(appeared)
        let sinceState = date.timeIntervalSince(since)
        let u = size / 116 // the viewBox is -8...108
        var p = pose
        let lv = still ? 0 : min(max(level, 0), 1)
        var grille = 0.0
        if state == .speaking { p.ring = (10.5 + 1.5 * lv) / 10.5; grille = lv }
        if state == .listening || state == .interrupted { p.core = (4.5 + 2 * lv) / 4.5; p.glow = 0.7 + 0.3 * lv }
        let blink = still || eyesClosed || state != .idle && state != .interrupted ? 0 : blinkAmount(t, sinceState: sinceState)
        p = p.shut(by: blink)
        let wander = still || state != .idle ? CGPoint.zero : wanderOffset(t)
        let lx = Double(wander.x + lookPoint.x * 4), ly = Double(wander.y + lookPoint.y * 4)
        let shake = !still && state == .error && sinceState < 0.3 ? 1.5 * sin(sinceState / 0.1 * 2 * .pi) : 0
        let flicker = !still && state == .error && sinceState < 0.36 ? (Int(sinceState / 0.06) % 2 == 0 ? 0.25 : 1) : 1
        let spin = still ? 0 : (t / 1.6 * 360).truncatingRemainder(dividingBy: 360)
        let led = ledOpacity(t)

        // Everything is drawn in the SVG's units, offset by 8 (the viewBox starts at -8).
        func box(_ v: Double) -> CGFloat { (v + 8) * u }

        return ZStack(alignment: .topLeading) {
            // working: the outer ring turning
            Circle()
                .trim(from: 0, to: 110 / 358)
                .stroke(Palette.red, style: StrokeStyle(lineWidth: 5 * u, lineCap: .round))
                .frame(width: 110 * u, height: 110 * u)
                .rotationEffect(.degrees(spin))
                .position(x: box(50), y: box(50))
                .opacity(p.outer)

            ZStack(alignment: .topLeading) {
                RoundedRectangle(cornerRadius: 30 * u, style: .circular).fill(Palette.graphite)
                    .frame(width: 100 * u, height: 100 * u)
                RoundedRectangle(cornerRadius: 30 * u, style: .circular)
                    .fill(LinearGradient(stops: [.init(color: .white.opacity(0.12), location: 0), .init(color: .white.opacity(0), location: 0.5)], startPoint: .top, endPoint: .bottom))
                    .frame(width: 100 * u, height: 100 * u)
                RoundedRectangle(cornerRadius: 29 * u, style: .circular).stroke(Palette.graphiteEdge, lineWidth: 1.5 * u)
                    .frame(width: 98 * u, height: 98 * u).offset(x: u, y: u)
                if !tiny {
                    Circle().fill(Palette.red).frame(width: 5.2 * u, height: 5.2 * u)
                        .position(x: 83 * u, y: 17 * u).opacity(led)
                }
                // the eye
                Circle().fill(Palette.socket).overlay(Circle().stroke(Color(rgb: 0x3e424a), lineWidth: 2 * u))
                    .frame(width: 46 * u, height: 46 * u).position(x: 50 * u, y: 46 * u)
                ZStack {
                    Circle().fill(Palette.red).frame(width: 26 * u, height: 26 * u)
                        .blur(radius: tiny ? 0 : 3.5 * u).opacity(p.glow)
                    Circle()
                        .stroke(Palette.red, style: StrokeStyle(lineWidth: 3 * u, dash: state == .thinking && !still ? [12 * u, 6 * u] : []))
                        .frame(width: 21 * u, height: 21 * u)
                        .rotationEffect(.degrees(state == .thinking && !still ? spin * 4 / 3 : 0))
                        .scaleEffect(p.ring)
                    Circle().fill(Palette.red).frame(width: 9 * u, height: 9 * u).scaleEffect(p.core)
                    Circle().fill(Color(rgb: 0xffe2e0)).frame(width: 3.4 * u, height: 3.4 * u)
                }
                .position(x: (50 + p.irisX + lx) * u, y: (47 + p.irisY + ly) * u)
                .opacity(p.iris * flicker)
                .frame(width: 100 * u, height: 100 * u, alignment: .topLeading)
                // the lids (metal), cut by the eye
                ZStack(alignment: .topLeading) {
                    UpperLid(side: p.lidSide, mid: p.lidMid).fill(Palette.graphite)
                    UpperLidEdge(side: p.lidSide, mid: p.lidMid).stroke(Palette.graphiteLine, style: StrokeStyle(lineWidth: 1.6 * u, lineJoin: .round))
                    LowerLid(top: p.lowerLid).fill(Palette.graphite)
                    if p.lowerLid < 70 {
                        LowerLidEdge(top: p.lowerLid).stroke(Palette.graphiteLine, lineWidth: 1.6 * u)
                    }
                }
                .frame(width: 100 * u, height: 100 * u)
                .clipShape(EyeClip())
                // speaker grille
                if !tiny {
                    Grille().stroke(Color(rgb: 0x15171a), style: StrokeStyle(lineWidth: 2.6 * u, lineCap: .round))
                        .frame(width: 100 * u, height: 100 * u)
                    Grille().stroke(Palette.red, style: StrokeStyle(lineWidth: 2.6 * u, lineCap: .round))
                        .frame(width: 100 * u, height: 100 * u)
                        .opacity(grille)
                }
            }
            .frame(width: 100 * u, height: 100 * u, alignment: .topLeading)
            .offset(x: 8 * u + shake * u, y: 8 * u)
            .opacity(p.body)
        }
        .frame(width: size, height: size, alignment: .topLeading)
    }

    private func ledOpacity(_ t: Double) -> Double {
        if state == .offline { return 0 }
        if still { return 1 }
        switch state {
        case .idle: return 0.675 + 0.325 * cos(t / 2.4 * 2 * .pi)
        case .thinking, .error: return Int(t / 0.2) % 2 == 0 ? 1 : 0.25
        default: return 1
        }
    }

    /// The mechanical blink every 6–10 s (shut 90 ms, hold 60, open 140), plus one right away
    /// when interrupted.
    private func blinkAmount(_ t: Double, sinceState: Double) -> Double {
        if state == .interrupted { return amount(sinceState) }
        let cycle = 8.0
        let k = floor(t / cycle)
        let at = k * cycle + Self.hash(k) * 2
        return amount(t - at)
    }

    private func amount(_ s: Double) -> Double {
        if s < 0 || s >= 0.29 { return 0 }
        if s < 0.09 { return Self.mech(s / 0.09) }
        if s < 0.15 { return 1 }
        return 1 - Self.mech((s - 0.15) / 0.14)
    }

    /// cubic-bezier(.6, 0, .2, 1), close enough: slow start, fast finish.
    private static func mech(_ x: Double) -> Double {
        let t = min(1, max(0, x))
        return t * t * (3 - 2 * t) * (0.6 + 0.4 * t)
    }

    /// Looking around at rest: a new spot every ~5 s, eased over 0.5 s, up to 2 units.
    private func wanderOffset(_ t: Double) -> CGPoint {
        let period = 5.0
        let k = floor(t / period)
        func spot(_ i: Double) -> CGPoint {
            CGPoint(x: (Self.hash(i * 3 + 1) * 2 - 1) * 2, y: (Self.hash(i * 7 + 2) * 2 - 1) * 1.2)
        }
        let a = spot(k - 1), b = spot(k)
        let s = min(1, (t - k * period) / 0.5)
        let e = 0.5 - 0.5 * cos(s * .pi)
        return CGPoint(x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e)
    }

    private static func hash(_ x: Double) -> Double {
        let v = sin(x * 127.1 + 311.7) * 43758.5453
        return v - floor(v)
    }
}

/// Older call sites use the first name of the mascot.
typealias CiclopeView = SentinelaView

// MARK: - Shapes in the body's 100 × 100 box, scaled to the frame

private struct EyeClip: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        return Path(ellipseIn: CGRect(x: 27 * k, y: 23 * k, width: 46 * k, height: 46 * k))
    }
}

private struct UpperLid: Shape {
    var side: Double
    var mid: Double
    var animatableData: AnimatablePair<Double, Double> {
        get { AnimatablePair(side, mid) }
        set { side = newValue.first; mid = newValue.second }
    }
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 22 * k, y: 18 * k))
        p.addLine(to: CGPoint(x: 78 * k, y: 18 * k))
        p.addLine(to: CGPoint(x: 78 * k, y: side * k))
        p.addLine(to: CGPoint(x: 50 * k, y: mid * k))
        p.addLine(to: CGPoint(x: 22 * k, y: side * k))
        p.closeSubpath()
        return p
    }
}

private struct UpperLidEdge: Shape {
    var side: Double
    var mid: Double
    var animatableData: AnimatablePair<Double, Double> {
        get { AnimatablePair(side, mid) }
        set { side = newValue.first; mid = newValue.second }
    }
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 27 * k, y: side * k))
        p.addLine(to: CGPoint(x: 50 * k, y: mid * k))
        p.addLine(to: CGPoint(x: 73 * k, y: side * k))
        return p
    }
}

private struct LowerLid: Shape {
    var top: Double
    var animatableData: Double {
        get { top }
        set { top = newValue }
    }
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        return Path(CGRect(x: 22 * k, y: top * k, width: 56 * k, height: max(0, 76 - top) * k))
    }
}

private struct LowerLidEdge: Shape {
    var top: Double
    var animatableData: Double {
        get { top }
        set { top = newValue }
    }
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 27 * k, y: top * k))
        p.addLine(to: CGPoint(x: 73 * k, y: top * k))
        return p
    }
}

private struct Grille: Shape {
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 100
        var p = Path()
        p.move(to: CGPoint(x: 41 * k, y: 79 * k)); p.addLine(to: CGPoint(x: 59 * k, y: 79 * k))
        p.move(to: CGPoint(x: 44 * k, y: 84 * k)); p.addLine(to: CGPoint(x: 56 * k, y: 84 * k))
        return p
    }
}

#Preview {
    VStack(spacing: 24) {
        HStack(spacing: 24) {
            SentinelaView(state: .idle, size: 80)
            SentinelaView(state: .thinking, size: 80)
            SentinelaView(state: .working, size: 80)
        }
        HStack(spacing: 24) {
            SentinelaView(state: .error, size: 80)
            SentinelaView(state: .offline, size: 80)
            SentinelaView(state: .listening, size: 80, eyesClosed: true)
        }
    }
    .padding(40)
    .background(Color(rgb: 0x09090b))
}
