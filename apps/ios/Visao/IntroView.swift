import SwiftUI
import VisaoKit

/// The opening (Intro.tsx and "The opening" in styles.css on the web): ~44 points drift in from
/// beyond the edges and become the orb, a ring pulses out, "V.I.S.A.O." is written with the
/// greeting, and the app shows through. 4 s; a tap skips it. Only the orb and the name: no mascot,
/// no logo, nobody else's mark.
struct IntroView: View {
    let onDone: () -> Void
    @Environment(Appearance.self) private var appearance
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var start = Date()
    @State private var dots = IntroView.scatter(44)
    private let hello = Opening.greeting()

    private static let red = Color(rgb: 0xe0483f)
    private static let orbSize: CGFloat = 132

    var body: some View {
        GeometryReader { proxy in
            let wide = sizeClass == .regular || proxy.size.width > 700
            TimelineView(.animation) { context in
                let t = context.date.timeIntervalSince(start)
                stage(t: t, size: proxy.size, wide: wide)
                    .opacity(1 - Self.ease(t, from: 3.4, to: 4.0))
            }
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        .onTapGesture(perform: onDone)
        .task {
            start = Date()
            try? await Task.sleep(for: .seconds(Opening.duration))
            onDone()
        }
        .accessibilityElement()
        .accessibilityLabel("\(hello). O que a gente resolve hoje?")
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Toque para pular")
    }

    private var night: Bool { appearance.isDark }
    private var tin: Color { night ? Color(rgb: 0xa9bcbd) : Color(rgb: 0x4f6366) }
    private var ink: Color { night ? Color(rgb: 0xf5f5f7) : Color(rgb: 0x17222a) }
    private var soft: Color { night ? Color(rgb: 0xc7cbd8) : Color(rgb: 0x36454e) }

    private func stage(t: Double, size: CGSize, wide: Bool) -> some View {
        let words = Self.ease(t, from: 1.8, to: 2.7)
        let greet = Self.ease(t, from: 2.4, to: 3.0)
        // Wide: the orb moves left as the name slides in beside it.
        let shift: CGFloat = wide ? -150 * words : 0
        let center = CGPoint(x: size.width / 2 + shift, y: size.height / 2 - (wide ? 0 : 50))
        return ZStack {
            background(size: size)
            ForEach(dots.indices, id: \.self) { index in
                dot(dots[index], t: t, size: size, center: center)
            }
            ring(t: t).position(center)
            orb(t: t).position(center)
            wordsView(words: words, greet: greet, wide: wide)
                .position(
                    wide
                        ? CGPoint(x: center.x + Self.orbSize / 2 + 24 + 170 + (1 - words) * 40, y: center.y)
                        : CGPoint(x: size.width / 2, y: center.y + Self.orbSize / 2 + 70 + (1 - words) * 14)
                )
        }
        .frame(width: size.width, height: size.height)
    }

    /// Solid, with three soft spots: a faint red-pink top left, tin on the right, a fainter red below.
    private func background(size: CGSize) -> some View {
        let big = max(size.width, size.height)
        return ZStack {
            (night ? Color(rgb: 0x141828) : Color(rgb: 0xeef2f3))
            RadialGradient(colors: [Self.red.opacity(night ? 0.14 : 0.12), .clear], center: UnitPoint(x: 0.08, y: 0.12), startRadius: 0, endRadius: big * 0.42)
            RadialGradient(colors: [tin.opacity(0.22), .clear], center: UnitPoint(x: 0.96, y: 0.6), startRadius: 0, endRadius: big * 0.48)
            RadialGradient(colors: [Self.red.opacity(0.07), .clear], center: UnitPoint(x: 0.4, y: 1.04), startRadius: 0, endRadius: big * 0.3)
        }
    }

    private func dot(_ dot: Dot, t: Double, size: CGSize, center: CGPoint) -> some View {
        let far = max(size.width, size.height) * dot.far
        let travel = Self.ease(t, from: dot.delay, to: dot.delay + 1.1, curve: .out)
        let x = cos(dot.angle) * far * (1 - travel) + cos(dot.turn) * dot.near * travel
        let y = sin(dot.angle) * far * (1 - travel) + sin(dot.turn) * dot.near * travel
        // From ~1.1 s they shrink and go into the orb.
        let gone = Self.ease(t, from: max(1.1, dot.delay + 0.75), to: 1.5)
        return Circle()
            .fill(dot.warm ? Self.red : tin)
            .frame(width: dot.size, height: dot.size)
            .scaleEffect(1 - gone)
            .opacity(1 - gone)
            .position(x: center.x + x, y: center.y + y)
    }

    private func ring(t: Double) -> some View {
        let p = Self.ease(t, from: 1.05, to: 2.15, curve: .out)
        return Circle()
            .strokeBorder(tin.opacity(0.7), lineWidth: 1.5)
            .frame(width: Self.orbSize, height: Self.orbSize)
            .scaleEffect(0.5 + 1.2 * p)
            .opacity(t < 1.05 ? 0 : 1 - p)
    }

    private func orb(t: Double) -> some View {
        let p = Self.ease(t, from: 1.05, to: 1.75, curve: .out)
        return Orb(size: Self.orbSize, control: false)
            .scaleEffect(0.6 + 0.4 * p)
            .opacity(p)
    }

    private func wordsView(words: Double, greet: Double, wide: Bool) -> some View {
        VStack(alignment: wide ? .leading : .center, spacing: 10) {
            Text("V.I.S.A.O.")
                .font(Typo.display(38, relativeTo: .largeTitle))
                .foregroundStyle(ink)
                .opacity(words)
            (Text("\(hello). ") + Text("O que a gente resolve hoje?").italic())
                .font(Typo.display(20, relativeTo: .title3))
                .foregroundStyle(soft)
                .multilineTextAlignment(wide ? .leading : .center)
                .opacity(greet)
                .offset(y: (1 - greet) * 8)
        }
        .frame(width: 340, alignment: wide ? .leading : .center)
    }

    // MARK: Timing

    enum Curve { case inOut, out }

    /// 0 before `from`, 1 after `to`, eased in between.
    static func ease(_ t: Double, from: Double, to: Double, curve: Curve = .inOut) -> Double {
        guard to > from else { return t >= to ? 1 : 0 }
        let x = min(max((t - from) / (to - from), 0), 1)
        switch curve {
        case .out: return 1 - pow(1 - x, 3)
        case .inOut: return x < 0.5 ? 4 * x * x * x : 1 - pow(-2 * x + 2, 3) / 2
        }
    }

    struct Dot {
        let angle: Double
        let turn: Double
        /// From beyond the edges, as a share of the screen's long side.
        let far: Double
        /// Where it lands on the orb, in points from its center (inside a 46 pt disc).
        let near: Double
        let size: CGFloat
        let delay: Double
        let warm: Bool
    }

    static func scatter(_ count: Int) -> [Dot] {
        (0..<count).map { i in
            let angle = Double.random(in: 0..<(2 * .pi))
            return Dot(
                angle: angle,
                turn: angle + Double.random(in: -0.6...0.6),
                far: 0.75 + Double.random(in: 0...0.3),
                near: sqrt(Double.random(in: 0...1)) * 46,
                size: CGFloat.random(in: 3...7),
                delay: Double.random(in: 0...0.35),
                warm: i % 8 == 0
            )
        }
    }
}
