import SwiftUI
import VisaoKit

/// Something he prepared that waits for your yes: an email, an event, work for the Mac. Dark like
/// the page card, as .action-card on the web. Nothing runs without the tap.
struct ActionCard: View {
    let ask: PendingAsk
    let busy: Bool
    let onDecide: (Bool) -> Void
    @Environment(\.palette) private var palette
    @State private var confirmApprove = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(ask.label)
                .font(Typo.text(.caption, weight: .medium))
                .foregroundStyle(Color(rgb: 0x9aa0b4))
            Text(ask.text)
                .font(Typo.text(.body))
                .foregroundStyle(Color(rgb: 0xf5f5f7))
                .fixedSize(horizontal: false, vertical: true)
            if let detail = ask.detail {
                ScrollView {
                    Text(detail)
                        .font(Typo.text(.subheadline))
                        .foregroundStyle(Color(rgb: 0xd7dae3))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(maxHeight: 180)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(rgb: 0x27343c), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            HStack(spacing: 8) {
                Spacer()
                Button { onDecide(false) } label: {
                    Text("Recusar")
                        .font(Typo.text(.callout, weight: .medium))
                        .foregroundStyle(Color(rgb: 0xf5f5f7))
                        .padding(.horizontal, 20)
                        .frame(minHeight: 44)
                        .overlay(Capsule().strokeBorder(Color(rgb: 0x3a3d45)))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                Button { onDecide(true) } label: {
                    Group {
                        if busy { ProgressView().tint(palette.cartaoPagina) } else { Text("Aprovar") }
                    }
                    .font(Typo.text(.callout, weight: .medium))
                    .foregroundStyle(palette.cartaoPagina)
                    .padding(.horizontal, 20)
                    .frame(minHeight: 44)
                    .background(Color(rgb: 0xeef2f3), in: Capsule())
                }
                .buttonStyle(.plain)
            }
            .disabled(busy)
            Text("Nada roda sem o seu toque.")
                .font(Typo.text(.caption))
                .foregroundStyle(Color(rgb: 0x7e8496))
        }
        .padding(18)
        .frame(maxWidth: 440, alignment: .leading)
        .background(palette.cartaoPagina, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.white.opacity(palette.usesGlass ? 0 : 0.09)))
        .shadow(color: .black.opacity(0.22), radius: 20, y: 8)
        .sensoryFeedback(.success, trigger: busy) { was, now in was && !now }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(ask.label): \(ask.text), esperando você")
    }
}
