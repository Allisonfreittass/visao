import SwiftUI

/// The call button's voice wave (.sky-orb-wave in apps/web/src/ceu.css): three small bars in tin.
/// Red and moving while it listens or speaks, slower while it thinks, faded without a connection.
struct VoiceWave: View {
    enum State: Equatable {
        case idle, thinking, live, offline
    }

    let state: State
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Heights of the bars at rest (ceu.css: 8, 16, 11 px).
    private let heights: [CGFloat] = [8, 16, 11]
    private let delays: [Double] = [0, 0.15, 0.3]
    static let red = Color(rgb: 0xe0483f)

    private var period: Double? {
        switch state {
        case .live: 0.8
        case .thinking: 1.1
        default: nil
        }
    }

    var body: some View {
        TimelineView(.animation(paused: period == nil || reduceMotion)) { context in
            HStack(spacing: 3) {
                ForEach(0..<3, id: \.self) { index in
                    RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                        .fill(state == .live ? Self.red : palette.estanho)
                        .frame(width: 3, height: heights[index])
                        .scaleEffect(y: scale(index, at: context.date), anchor: .center)
                }
            }
            .frame(height: 20)
        }
        .opacity(state == .offline ? 0.4 : state == .idle ? 0.8 : 1)
        .animation(.easeOut(duration: 0.3), value: state)
        .accessibilityHidden(true)
    }

    /// Down to 45% and back, each bar a little after the one before (@keyframes onda).
    private func scale(_ index: Int, at date: Date) -> CGFloat {
        guard let period, !reduceMotion else { return 1 }
        let t = (date.timeIntervalSinceReferenceDate - delays[index]).truncatingRemainder(dividingBy: period) / period
        let dip = 0.5 - 0.5 * cos(2 * .pi * t)
        return 1 - 0.55 * dip
    }
}
