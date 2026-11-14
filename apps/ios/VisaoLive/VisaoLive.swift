import ActivityKit
import SwiftUI
import WidgetKit

@main
struct VisaoLiveBundle: WidgetBundle {
    var body: some Widget {
        TurnLiveActivity()
    }
}

/// The reply in progress on the lock screen and in the Dynamic Island: the lantern, his name, the
/// step he is on and how long it has been; then "Respondeu" with the first words.
struct TurnLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: VisaoTurnAttributes.self) { context in
            LockScreenCard(attributes: context.attributes, state: context.state)
                .activityBackgroundTint(Color(red: 0x1b / 255, green: 0x26 / 255, blue: 0x2d / 255).opacity(0.92))
                .activitySystemActionForegroundColor(.white)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Lantern(state: context.state).padding(.leading, 4)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Elapsed(attributes: context.attributes, state: context.state)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.trailing, 4)
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.agentName ?? "V.I.S.A.O.")
                        .font(.system(.subheadline, design: .serif))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(headline(context.state))
                            .font(.headline)
                            .lineLimit(1)
                        if let line = secondLine(context.state) {
                            Text(line).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            } compactLeading: {
                Lantern(state: context.state)
            } compactTrailing: {
                if context.state.done {
                    Image(systemName: context.state.failed ? "xmark" : "checkmark")
                        .font(.caption.weight(.bold))
                } else {
                    Text(context.state.current)
                        .font(.caption2)
                        .lineLimit(1)
                        .frame(maxWidth: 64)
                }
            } minimal: {
                Lantern(state: context.state)
            }
            .keylineTint(Color(red: 0xe0 / 255, green: 0x48 / 255, blue: 0x3f / 255))
        }
    }
}

private func headline(_ state: VisaoTurnAttributes.ContentState) -> String {
    if state.done { return state.failed ? "Não respondeu" : "Respondeu" }
    return state.current
}

private func secondLine(_ state: VisaoTurnAttributes.ContentState) -> String? {
    if state.done { return state.excerpt }
    if let detail = state.detail, !detail.isEmpty { return detail }
    return state.steps.count > 1 ? "\(state.steps.count) passos" : nil
}

private struct LockScreenCard: View {
    let attributes: VisaoTurnAttributes
    let state: VisaoTurnAttributes.ContentState

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Lantern(state: state)
                .frame(width: 38, height: 38)
                .background(Circle().fill(.white.opacity(0.08)))
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(attributes.agentName ?? "V.I.S.A.O.")
                        .font(.system(.subheadline, design: .serif))
                        .foregroundStyle(.white.opacity(0.75))
                    Spacer()
                    Elapsed(attributes: attributes, state: state)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.white.opacity(0.6))
                }
                Text(headline(state))
                    .font(.headline)
                    .foregroundStyle(.white)
                    .lineLimit(1)
                if let line = secondLine(state) {
                    Text(line)
                        .font(.footnote)
                        .foregroundStyle(.white.opacity(0.7))
                        .lineLimit(2)
                }
                if !state.done && state.steps.count > 1 {
                    // The steps already done, as small dots, the current one lit.
                    HStack(spacing: 4) {
                        ForEach(Array(state.steps.suffix(8).enumerated()), id: \.offset) { index, _ in
                            Capsule()
                                .fill(index == min(state.steps.count, 8) - 1 ? Color.white : Color.white.opacity(0.3))
                                .frame(width: index == min(state.steps.count, 8) - 1 ? 16 : 6, height: 4)
                        }
                    }
                    .padding(.top, 2)
                }
            }
        }
        .padding(16)
    }
}

/// The lantern of the orb: steady red while it works, a check when it answered.
private struct Lantern: View {
    let state: VisaoTurnAttributes.ContentState

    var body: some View {
        ZStack {
            if state.done {
                Image(systemName: state.failed ? "xmark" : "checkmark")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.white)
            } else {
                Circle()
                    .fill(Color(red: 0xe0 / 255, green: 0x48 / 255, blue: 0x3f / 255))
                    .frame(width: 10, height: 10)
                    .shadow(color: Color(red: 0xe0 / 255, green: 0x48 / 255, blue: 0x3f / 255).opacity(0.7), radius: 4)
            }
        }
        .accessibilityLabel(state.done ? "Respondeu" : "Trabalhando")
    }
}

/// Time since the question, counting on its own (the system updates it, not the app).
private struct Elapsed: View {
    let attributes: VisaoTurnAttributes
    let state: VisaoTurnAttributes.ContentState

    var body: some View {
        if state.done {
            Text("agora")
        } else {
            Text(timerInterval: attributes.startedAt...Date.distantFuture, countsDown: false)
                .multilineTextAlignment(.trailing)
        }
    }
}
