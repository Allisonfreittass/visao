import SwiftUI
import VisaoKit

/// His bubble while he works (docs/decisions/0011): it breathes with the current step ("Cotando
/// voos"), then the text comes in where the dots were, at a steady pace, and when the reply has
/// arrived and is all on screen it hands over to the message itself. One bubble that changes,
/// never one that disappears while another appears.
struct LiveBubble: View {
    let step: ProgressStep?
    let text: String
    /// The reply arrived: once all of it is shown, `onSettled` turns it into the message.
    let settling: Bool
    let canStop: Bool
    let onStop: () -> Void
    let onSettled: () -> Void
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown: Double = 0
    @State private var shownText = ""
    @State private var breathing = false

    private var revealed: String { String(text.prefix(Int(shown))) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if revealed.isEmpty {
                HStack(spacing: 12) {
                    ThinkingDots(color: palette.tintaFraca)
                    stepLabel(font: .subheadline)
                    stopButton
                }
                .padding(.leading, 20)
                .padding(.trailing, canStop ? 2 : 20)
                .padding(.vertical, canStop ? 2 : 16)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    if !settling, step != nil {
                        HStack {
                            stepLabel(font: .caption)
                            Spacer(minLength: 0)
                            stopButton
                        }
                    }
                    MarkdownView(text: revealed, live: true, freshTail: reduceMotion ? 0 : 10)
                        .font(Typo.text(.body))
                        .foregroundStyle(palette.bolhaDeleTinta)
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 14)
            }
        }
        .background(palette.bolhaDele, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: palette.sombra.opacity(0.7), radius: 8, y: 3)
        .opacity(revealed.isEmpty && breathing && !reduceMotion ? 0.8 : 1)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.trailing, 24)
        .animation(reduceMotion ? nil : .spring(response: 0.4, dampingFraction: 0.85), value: revealed.isEmpty)
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) { breathing = true }
        }
        .task(id: text) { await reveal() }
        .onChange(of: settling) { _, now in
            if now, shown >= Double(text.count) { onSettled() }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(revealed.isEmpty ? (step?.label ?? "Pensando") : text)
    }

    private func stepLabel(font: Font.TextStyle) -> some View {
        Text(step?.label ?? "Pensando")
            .font(Typo.text(font))
            .foregroundStyle(palette.tintaFraca)
            .contentTransition(.opacity)
            .animation(reduceMotion ? nil : .easeInOut, value: step?.label)
    }

    @ViewBuilder
    private var stopButton: some View {
        if canStop && !settling {
            Button(action: onStop) {
                Image(systemName: "xmark")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(palette.tintaSuave)
                    .frame(width: 28, height: 28)
                    .background(palette.fundoHover, in: Circle())
                    .frame(width: 44, height: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Parar")
        }
    }

    /// Lets the text out at a steady pace (VisaoKit.Reveal); a `replace` keeps what was right.
    private func reveal() async {
        let keep = Double(Reveal.commonPrefix(shownText, text))
        if shown > keep { shown = keep }
        shownText = text
        let total = text.count
        if reduceMotion {
            shown = Double(total)
        } else {
            var last = ContinuousClock.now
            while shown < Double(total), !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(16))
                let now = ContinuousClock.now
                let dt = min(0.1, Double((now - last).components.attoseconds) / 1e18 + Double((now - last).components.seconds))
                last = now
                shown = Reveal.step(shown: shown, target: total, dt: dt)
            }
        }
        if settling, shown >= Double(total) { onSettled() }
    }
}
