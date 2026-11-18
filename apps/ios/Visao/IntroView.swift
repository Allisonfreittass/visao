import SwiftUI
import VisaoKit

/// The opening (apps/web/src/components/Intro.tsx, shortened to 1.8 s): the Ciclope wakes up on a
/// dark floor that turns light, its family bounces in from the edges and joins it, a thin orange
/// ring draws around it and pops confetti, the name slides in beside it, and the lockup shrinks
/// toward the tab bar as the app shows through. A tap skips it; never with Reduce Motion.
struct IntroView: View {
    let onDone: () -> Void
    @Environment(\.palette) private var palette
    @State private var start = Date()
    private let hello = Opening.greeting()

    private static let family: [CritterView.Kind] = [.mac, .whatsapp, .email, .caderno]
    /// Where each one comes from (a fraction of the screen from the center) and lands (points).
    private static let entries: [(from: CGPoint, land: CGPoint)] = [
        (CGPoint(x: -0.7, y: -0.45), CGPoint(x: -78, y: -50)),
        (CGPoint(x: 0.7, y: -0.4), CGPoint(x: 78, y: -50)),
        (CGPoint(x: -0.65, y: 0.5), CGPoint(x: -78, y: 50)),
        (CGPoint(x: 0.7, y: 0.45), CGPoint(x: 78, y: 50)),
    ]
    private static let confettiColors: [Color] = [0x3b6bff, 0x18c27a, 0xffc83d, 0x9b87ff, 0xff6a1a].map { Color(rgb: $0) }

    var body: some View {
        GeometryReader { proxy in
            TimelineView(.animation) { context in
                stage(t: context.date.timeIntervalSince(start), size: proxy.size)
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
        .accessibilityLabel("V.I.S.A.O. \(hello).")
        .accessibilityAddTraits(.isButton)
        .accessibilityHint("Toque para pular")
    }

    private func stage(t: Double, size: CGSize) -> some View {
        let light = Self.ease(t, 0.2, 0.48)
        let grow = Self.back(Self.clamp((t - 0.2) / 0.32))
        let merge = Self.ease(t, 0.9, 1.08)
        let ringDraw = Self.ease(t, 0.97, 1.18)
        let ringFade = Self.ease(t, 1.18, 1.4)
        let pop = Self.clamp((t - 1.08) / 0.44)
        let slide = Self.ease(t, 1.18, 1.5)
        let word = Self.ease(t, 1.24, 1.52)
        let fly = Self.ease(t, 1.5, 1.8)
        let wordWidth: CGFloat = 190
        let shift = (wordWidth + 16) / 2 * (1 - slide)
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        // The end: toward the Início tab, where the Ciclope lives in the tab bar.
        let tab = CGPoint(x: size.width / 6, y: size.height - 48)

        return ZStack {
            Color(rgb: 0x0e0f13)
            AmbientBackground().opacity(light)

            HStack(spacing: 16) {
                ZStack {
                    Circle()
                        .trim(from: 0, to: ringDraw)
                        .stroke(Palette.accentColor, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .frame(width: 128, height: 128)
                        .scaleEffect(1 + 0.15 * ringFade)
                        .opacity(1 - ringFade)
                    ForEach(0..<14, id: \.self) { i in
                        confetti(i, pop: pop)
                    }
                    CiclopeView(state: .idle, size: 88, eyesClosed: t < 0.22)
                        .scaleEffect((0.55 + 0.45 * grow) * (1 + 0.08 * sin(Self.clamp((t - 1.1) / 0.18) * .pi)))
                    ForEach(Self.family.indices, id: \.self) { i in
                        critter(i, t: t, merge: merge, size: size)
                    }
                }
                .frame(width: 88, height: 88)
                Text("V.I.S.A.O.")
                    .font(Typo.display(34, relativeTo: .largeTitle))
                    .foregroundStyle(palette.text)
                    .fixedSize()
                    .frame(width: wordWidth, alignment: .leading)
                    .opacity(word)
                    .offset(x: -14 * (1 - word))
            }
            .offset(x: shift)
            .scaleEffect(1 - 0.7 * fly)
            .position(x: center.x + (tab.x - center.x) * fly, y: center.y + (tab.y - center.y) * fly)
        }
        .opacity(1 - Self.ease(t, 1.56, 1.8))
    }

    private func critter(_ i: Int, t: Double, merge: Double, size: CGSize) -> some View {
        let entry = Self.entries[i]
        let p = Self.clamp((t - 0.48 - Double(i) * 0.03) / (0.42 - Double(i) * 0.03))
        let k = Self.back(p)
        let from = CGPoint(x: entry.from.x * size.width, y: entry.from.y * size.height)
        let x = from.x + (entry.land.x - from.x) * k
        let y = from.y + (entry.land.y - from.y) * k
        return CritterView(kind: Self.family[i], size: 36)
            .rotationEffect(.degrees((entry.from.x > 0 ? 40 : -40) * (1 - p)))
            .scaleEffect((0.6 + 0.4 * p) * (1 - 0.8 * merge))
            .offset(x: x * (1 - merge), y: y * (1 - merge))
            .opacity(p <= 0 ? 0 : 1 - merge)
    }

    private func confetti(_ i: Int, pop: Double) -> some View {
        let angle = Double(i) / 14 * 2 * .pi + 0.2
        let reach = 96 + Double(i % 3) * 22
        let e = 1 - pow(1 - pop, 3)
        return Circle()
            .fill(Self.confettiColors[i % Self.confettiColors.count])
            .frame(width: 7, height: 7)
            .offset(x: cos(angle) * reach * e, y: sin(angle) * reach * e + 24 * pop * pop)
            .opacity(pop <= 0 || pop >= 1 ? 0 : (pop < 0.35 ? pop / 0.35 : 1 - (pop - 0.35) / 0.65))
    }

    private static func clamp(_ x: Double) -> Double { min(1, max(0, x)) }

    /// cubic-bezier(.2,.8,.2,1)-like ease between two times.
    private static func ease(_ t: Double, _ from: Double, _ to: Double) -> Double {
        let x = clamp((t - from) / (to - from))
        return 1 - pow(1 - x, 3)
    }

    /// An ease with a little overshoot, for the bounce.
    private static func back(_ x: Double) -> Double {
        let c1 = 1.70158, c3 = c1 + 1
        return 1 + c3 * pow(x - 1, 3) + c1 * pow(x - 1, 2)
    }
}
