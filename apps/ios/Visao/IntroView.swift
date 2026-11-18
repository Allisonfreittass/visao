import SwiftUI
import VisaoKit

/// The opening, a boot sequence (apps/web/src/components/Intro.tsx, 1.6 s on the iPhone): the
/// dark grid with the mascot off and shut; its LED blinks twice; the lid opens and the eye lights
/// up with the red glow; the sensors come online in orbit one by one as a thin red ring sweeps
/// once; they fold in, the mascot slides left and the name is typed, the last dot red; then the
/// lockup shrinks toward the Início tab as the app shows through. A tap skips it.
struct IntroView: View {
    let onDone: () -> Void
    @Environment(\.palette) private var palette
    @State private var start = Date()
    private let hello = Opening.greeting()

    private static let sensors: [SensorView.Kind] = [.mac, .email, .caderno]
    private static let word = Array("V.I.S.A.O.")

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
        let awake = t >= 0.37
        let led = t > 0.17 && t < 0.37 && (Int((t - 0.17) / 0.05) % 2 == 0)
        let glow = Self.ease(t, 0.37, 0.6)
        let sweep = Self.ease(t, 0.63, 1.0)
        let fold = Self.ease(t, 1.0, 1.15)
        let slide = Self.ease(t, 1.0, 1.27)
        let typed = Int(max(0, (t - 1.01) / 0.027))
        let fly = Self.ease(t, 1.27, 1.6)
        let wordWidth: CGFloat = 176
        let shift = (wordWidth + 14) / 2 * (1 - slide)
        let center = CGPoint(x: size.width / 2, y: size.height / 2)
        let tab = CGPoint(x: size.width / 6, y: size.height - 48)

        return ZStack {
            Color(rgb: 0x09090b)
            AmbientBackground().opacity(glow)

            HStack(spacing: 14) {
                ZStack {
                    Circle()
                        .trim(from: 0, to: 0.18)
                        .stroke(Palette.red, style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                        .frame(width: 128, height: 128)
                        .rotationEffect(.degrees(-90 + 360 * sweep))
                        .opacity(sweep > 0 && sweep < 1 ? 1 : 0)
                    ForEach(Self.sensors.indices, id: \.self) { i in
                        sensor(i, t: t, fold: fold)
                    }
                    SentinelaView(state: awake ? .idle : .offline, size: 88)
                    Circle().fill(Palette.red).frame(width: 5, height: 5)
                        .shadow(color: Palette.red, radius: 4)
                        .offset(x: 88 * (83 + 8) / 116 - 44, y: 88 * (17 + 8) / 116 - 44)
                        .opacity(led ? 1 : 0)
                }
                .frame(width: 88, height: 88)
                HStack(spacing: 0) {
                    ForEach(Self.word.indices, id: \.self) { i in
                        let c = Self.word[i]
                        Text(String(c))
                            .foregroundStyle(c == "." ? (i == Self.word.count - 1 ? palette.red : palette.textMuted) : palette.text)
                            .opacity(i < typed ? 1 : 0)
                    }
                }
                .font(Typo.display(32, relativeTo: .largeTitle))
                .tracking(1.2)
                .fixedSize()
                .frame(width: wordWidth, alignment: .leading)
            }
            .offset(x: shift)
            .scaleEffect(1 - 0.7 * fly)
            .position(x: center.x + (tab.x - center.x) * fly, y: center.y + (tab.y - center.y) * fly)
        }
        .opacity(1 - Self.ease(t, 1.32, 1.6))
    }

    private func sensor(_ i: Int, t: Double, fold: Double) -> some View {
        let angle = -Double.pi / 2 + Double(i) / Double(Self.sensors.count) * 2 * .pi
        let r = 78.0
        let start = 0.6 + Double(i) * 0.08
        let pop = Self.clamp((t - start) / 0.16)
        let lit = t >= start + 0.07
        let k = 1 - fold
        return SensorView(kind: Self.sensors[i], size: 30, asleep: !lit)
            .scaleEffect((0.3 + 0.7 * Self.back(pop)) * (1 - 0.8 * fold))
            .offset(x: cos(angle) * r * k, y: sin(angle) * r * k)
            .opacity(pop <= 0 ? 0 : 1 - fold)
    }

    private static func clamp(_ x: Double) -> Double { min(1, max(0, x)) }

    private static func ease(_ t: Double, _ from: Double, _ to: Double) -> Double {
        let x = clamp((t - from) / (to - from))
        return 1 - pow(1 - x, 3)
    }

    /// A small overshoot, for the sensors popping on.
    private static func back(_ x: Double) -> Double {
        let c1 = 1.2, c3 = c1 + 1
        return 1 + c3 * pow(x - 1, 3) + c1 * pow(x - 1, 2)
    }
}
