import SwiftUI
import UIKit
import VisaoKit

/// One message, as in the "Neblina" look of the web: what he says in a solid bubble on the left,
/// what you say in glass on the right. Names and times stay out of the way; only "puxou
/// conversa", "no Mac", "não foi enviada" and the like are shown.
struct MessageRow: View {
    let message: Message
    let speaker: String
    let onReply: () -> Void
    let onQuoteTap: (String) -> Void
    let onOpenPage: (Artifact) -> Void
    /// Rates a reply; answers what to say back ("Valeu…"), nil when it failed.
    var onFeedback: ((Bool, [String]) async -> String?)?
    @Environment(\.palette) private var palette
    @State private var feedbackOpen = false

    /// Past this, letting go answers the message (as SwipeReply.tsx on the web).
    private let trigger: CGFloat = 56
    private let maxOffset: CGFloat = 84
    @State private var offset: CGFloat = 0
    @State private var armed = false

    private var isUser: Bool { message.role == .user }
    private var canReply: Bool { message.local == nil }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 48) }
            bubble
            if !isUser { Spacer(minLength: 24) }
        }
        .background(alignment: .leading) {
            if offset > 0 {
                Image(systemName: "arrowshape.turn.up.left.fill")
                    .foregroundStyle(armed ? palette.tinta : palette.tintaFraca)
                    .frame(width: 32, height: 32)
                    .glassCircle(palette, size: 32)
                    .scaleEffect(armed ? 1.1 : 0.85)
                    .opacity(Double(min(offset / trigger, 1)))
                    .offset(x: max(0, offset / 2 - 16))
                    .accessibilityHidden(true)
            }
        }
        .simultaneousGesture(swipe)
        .sensoryFeedback(.impact(weight: .light), trigger: armed) { _, isArmed in isArmed }
    }

    private var bubble: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let tag = tag {
                Text(tag.text)
                    .font(Typo.text(.caption))
                    .foregroundStyle(tag.isProblem ? palette.erro : palette.tintaSuave)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 3)
                    .background(palette.fundoHover, in: Capsule())
            }
            if let quote = message.replyTo {
                Button { onQuoteTap(quote.id) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(quote.role == .assistant ? speaker : "Você")
                            .font(Typo.text(.caption, weight: .medium))
                            .foregroundStyle(palette.estanho)
                        Text(quote.excerpt)
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.tintaSuave)
                            .lineLimit(2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(palette.fundoHover, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(alignment: .leading) {
                        UnevenRoundedRectangle(topLeadingRadius: 12, bottomLeadingRadius: 12)
                            .fill(palette.estanho)
                            .frame(width: 3)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Respondendo a \(quote.role == .assistant ? speaker : "você"): \(quote.excerpt)")
                .accessibilityHint("Vai para a mensagem")
            }
            if !message.attachments.isEmpty {
                MessageAttachments(attachments: message.attachments)
            }
            if !message.content.isEmpty {
                MarkdownView(text: message.content)
            }
            if let artifact = message.artifact {
                ArtifactCard(artifact: artifact) { onOpenPage(artifact) }
                    .padding(.horizontal, -6)
                    .padding(.top, 4)
            }
            if !message.sources.isEmpty {
                SourcesList(sources: message.sources)
            }
            if !isUser, message.local == nil, let onFeedback {
                FeedbackBar(open: $feedbackOpen, send: onFeedback)
            }
        }
        .font(Typo.text(.body))
        .foregroundStyle(isUser ? palette.tinta : palette.bolhaDeleTinta)
        .padding(.horizontal, isUser ? 16 : 18)
        .padding(.vertical, isUser ? 12 : 14)
        .background(background)
        .opacity(opacity)
        .offset(x: offset)
        .contextMenu {
            if canReply {
                Button("Responder", systemImage: "arrowshape.turn.up.left", action: onReply)
            }
            if !message.content.isEmpty {
                Button("Copiar", systemImage: "doc.on.doc") { UIPasteboard.general.string = message.content }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isUser ? "Você" : speaker): \(message.content)")
        .accessibilityAction(named: "Responder") { if canReply { onReply() } }
    }

    @ViewBuilder
    private var background: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        if isUser {
            Group {
                if palette.usesGlass {
                    shape.fill(.ultraThinMaterial).overlay(shape.fill(palette.bolhaSua))
                } else {
                    shape.fill(palette.bolhaSua)
                }
            }
            .overlay(shape.strokeBorder(message.local == .failed ? palette.erro : palette.vidroBorda, lineWidth: 1))
            .shadow(color: palette.sombra.opacity(0.5), radius: 7, y: 2)
        } else {
            shape.fill(palette.bolhaDele)
                .overlay(shape.strokeBorder(palette.usesGlass ? .clear : palette.linha, lineWidth: 1))
                .shadow(color: palette.sombra, radius: 11, y: 6)
        }
    }

    private var opacity: Double {
        switch message.local {
        case .sending: 0.55
        case .queued: 0.42
        default: 1
        }
    }

    private var tag: (text: String, isProblem: Bool)? {
        switch message.local {
        case .failed: return ("não foi enviada", true)
        case .stopped: return ("parada", true)
        case .queued: return ("na fila", false)
        default: break
        }
        switch message.origin {
        case "initiative": return ("puxou conversa", false)
        case "arm": return ("no Mac", false)
        case "google": return ("no Google", false)
        default: return nil
        }
    }

    /// Only a clearly sideways drag to the right moves the bubble; vertical scrolling stays.
    private var swipe: some Gesture {
        DragGesture(minimumDistance: 14)
            .onChanged { value in
                guard canReply else { return }
                let dx = value.translation.width
                let dy = value.translation.height
                guard dx > 0, dx > abs(dy) * 1.5 else {
                    if offset != 0 { withAnimation(.spring(duration: 0.25)) { offset = 0 } }
                    armed = false
                    return
                }
                // Resistance after the trigger point, like a spring.
                offset = dx <= trigger ? dx : min(maxOffset, trigger + (dx - trigger) * 0.35)
                let nowArmed = offset >= trigger
                if nowArmed != armed { armed = nowArmed }
            }
            .onEnded { _ in
                let swiped = armed
                armed = false
                withAnimation(.spring(duration: 0.3)) { offset = 0 }
                if swiped { onReply() }
            }
    }
}

private struct SourcesList: View {
    let sources: [Source]
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Rotulo("Fontes")
            ForEach(Array(sources.enumerated()), id: \.offset) { index, source in
                if let url = URL(string: source.url), ["http", "https"].contains(url.scheme ?? "") {
                    Link(destination: url) {
                        (Text("\(index + 1). \(source.title)").underline(color: palette.linhaForte)
                            + Text(" · \(source.source)").foregroundColor(palette.tintaFraca))
                            .font(Typo.text(.footnote))
                            .multilineTextAlignment(.leading)
                    }
                    .foregroundStyle(palette.tinta)
                }
            }
        }
        .padding(.top, 4)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Fontes pesquisadas")
    }
}

/// "Como foi essa resposta?": thumbs and a few tags, the only evidence its way of answering
/// learns from (FeedbackBar.tsx).
private struct FeedbackBar: View {
    @Binding var open: Bool
    let send: (Bool, [String]) async -> String?
    @Environment(\.palette) private var palette
    @State private var tags: Set<String> = []
    @State private var done: String?
    @State private var busy = false

    private let options = ["muito longo", "muito curto", "faltou fonte", "perguntas demais"]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let done {
                Text(done).font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
            } else if open {
                HStack(spacing: 8) {
                    thumb("hand.thumbsup", label: "Resposta boa", positive: true)
                    thumb("hand.thumbsdown", label: "Resposta ruim", positive: false)
                }
                FlowChips(options: options, selected: $tags)
            } else {
                Button {
                    withAnimation(.spring(duration: 0.3)) { open = true }
                } label: {
                    Text("Como foi essa resposta?")
                        .font(Typo.text(.caption))
                        .foregroundStyle(palette.tintaFraca)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 2)
    }

    private func thumb(_ icon: String, label: String, positive: Bool) -> some View {
        Button {
            busy = true
            Task {
                let reply = await send(positive, Array(tags))
                busy = false
                withAnimation { done = reply ?? "Não deu para mandar agora." }
            }
        } label: {
            Image(systemName: icon)
                .font(.subheadline)
                .frame(width: 40, height: 34)
                .overlay(Capsule().strokeBorder(palette.linhaForte))
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .sensoryFeedback(.impact(weight: .light), trigger: done)
        .accessibilityLabel(label)
    }
}

/// Tags you tap on and off, wrapping to the next line.
private struct FlowChips: View {
    let options: [String]
    @Binding var selected: Set<String>
    @Environment(\.palette) private var palette

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { chips }
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) { ForEach(options.prefix(2), id: \.self, content: chip) }
                HStack(spacing: 6) { ForEach(options.dropFirst(2), id: \.self, content: chip) }
            }
        }
    }

    private var chips: some View { ForEach(options, id: \.self, content: chip) }

    private func chip(_ tag: String) -> some View {
        let on = selected.contains(tag)
        return Button {
            if on { selected.remove(tag) } else { selected.insert(tag) }
        } label: {
            Text(tag)
                .font(Typo.text(.caption))
                .padding(.horizontal, 10)
                .frame(minHeight: 30)
                .foregroundStyle(on ? palette.pilulaAtivaTinta : palette.tintaSuave)
                .background(on ? palette.pilulaAtiva : .clear, in: Capsule())
                .overlay(Capsule().strokeBorder(on ? .clear : palette.linhaForte))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
