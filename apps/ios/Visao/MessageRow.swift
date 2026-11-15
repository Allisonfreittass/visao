import SwiftUI
import UIKit
import VisaoKit

/// One message, as in the "Neblina" look of the web: what he says in a solid bubble on the left,
/// what you say in glass on the right. Names and times stay out of the way; only "puxou
/// conversa", "no Mac", "não foi enviada" and the like are shown.
struct MessageRow: View, Equatable {
    /// Redrawn only when the message itself changes, not on every progress check of the chat.
    nonisolated static func == (a: MessageRow, b: MessageRow) -> Bool {
        a.message == b.message && a.speaker == b.speaker
    }

    let message: Message
    let speaker: String
    let onReply: () -> Void
    let onQuoteTap: (String) -> Void
    let onOpenPage: (Artifact) -> Void
    /// Rates a reply; answers what to say back ("Valeu…"), nil when it failed.
    var onFeedback: ((Bool, [String]) async -> String?)?
    @Environment(\.palette) private var palette
    /// Rating lives in the menu (hold the bubble), not under every reply.
    @State private var feedbackOpen = false
    @State private var sourcesOpen = false

    /// Past this, letting go answers the message (as SwipeReply.tsx on the web).
    private let trigger: CGFloat = 56
    private let maxOffset: CGFloat = 84
    @State private var offset: CGFloat = 0
    @State private var armed = false
    /// Decided at the start of a drag: sideways answers, up and down is the list scrolling.
    @State private var axis: Axis?

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

    /// One bubble per part (ADR-0010); a message without parts is one bubble. What belongs to the
    /// whole message goes on the edges: the quote and the files on the first bubble, the page and
    /// the sources on the last. The menu (hold a bubble) is the same on every bubble.
    private var bubble: some View {
        let texts = message.bubbles
        let count = max(texts.count, 1)
        return VStack(alignment: isUser ? .trailing : .leading, spacing: 6) {
            ForEach(0..<count, id: \.self) { index in
                single(text: texts.indices.contains(index) ? texts[index] : "", first: index == 0, last: index == count - 1)
                    .transition(.asymmetric(insertion: .opacity.combined(with: .offset(y: 8)), removal: .opacity))
            }
        }
        .offset(x: offset)
        .sheet(isPresented: $feedbackOpen) {
            FeedbackSheet(send: { positive, tags in await onFeedback?(positive, tags) })
                .presentationDetents([.height(240)])
        }
        .sheet(isPresented: $sourcesOpen) {
            SourcesSheet(sources: message.sources, at: message.createdAt)
                .presentationDetents([.medium, .large])
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isUser ? "Você" : speaker): \(message.content)")
        .accessibilityAction(named: "Responder") { if canReply { onReply() } }
        .accessibilityAction(named: "Avaliar resposta") { if canRate { feedbackOpen = true } }
        .accessibilityAction(named: "Ver fontes") { if !message.sources.isEmpty { sourcesOpen = true } }
    }

    private var canRate: Bool { !isUser && message.local == nil && onFeedback != nil }

    private func single(text: String, first: Bool, last: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if first, let tag = tag {
                Text(tag.text)
                    .font(Typo.text(.caption))
                    .foregroundStyle(tag.isProblem ? palette.erro : palette.tintaSuave)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 3)
                    .background(palette.fundoHover, in: Capsule())
            }
            if first, let quote = message.replyTo {
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
            if first, !message.attachments.isEmpty {
                MessageAttachments(attachments: message.attachments)
            }
            if !text.isEmpty {
                MarkdownView(text: text)
            }
            if last, let artifact = message.artifact {
                ArtifactCard(artifact: artifact) { onOpenPage(artifact) }
                    .padding(.horizontal, -6)
                    .padding(.top, 4)
            }
            if last, !message.sources.isEmpty {
                SourcesPill(sources: message.sources, at: message.createdAt) { sourcesOpen = true }
            }
        }
        .font(Typo.text(.body))
        .foregroundStyle(isUser ? palette.tinta : palette.bolhaDeleTinta)
        .padding(.horizontal, isUser ? 16 : 18)
        .padding(.vertical, isUser ? 12 : 14)
        .background(background)
        .opacity(opacity)
        .contextMenu {
            if canReply {
                Button("Responder", systemImage: "arrowshape.turn.up.left", action: onReply)
            }
            if !message.content.isEmpty {
                Button("Copiar", systemImage: "doc.on.doc") { UIPasteboard.general.string = message.content }
            }
            if canRate {
                Button("Avaliar resposta", systemImage: "hand.thumbsup") { feedbackOpen = true }
            }
            if !message.sources.isEmpty {
                Button("Ver fontes", systemImage: "link") { sourcesOpen = true }
            }
        }
    }

    @ViewBuilder
    private var background: some View {
        let shape = RoundedRectangle(cornerRadius: 20, style: .continuous)
        if isUser {
            // No live blur per bubble: over the moving forest it was redrawn every frame.
            shape.fill(palette.bolhaSua)
                .overlay(shape.strokeBorder(message.local == .failed ? palette.erro : palette.vidroBorda, lineWidth: 1))
                .shadow(color: palette.sombra.opacity(0.35), radius: 4, y: 1)
        } else {
            shape.fill(palette.bolhaDele)
                .overlay(shape.strokeBorder(palette.usesGlass ? .clear : palette.linha, lineWidth: 1))
                .shadow(color: palette.sombra.opacity(0.7), radius: 8, y: 3)
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
                if axis == nil { axis = dx > 0 && dx > abs(dy) * 1.5 ? .horizontal : .vertical }
                // Scrolling the list: touch nothing, so the row is not redrawn on every move.
                guard axis == .horizontal, dx > 0 else {
                    if offset != 0 { withAnimation(.spring(duration: 0.25)) { offset = 0 } }
                    if armed { armed = false }
                    return
                }
                // Resistance after the trigger point, like a spring.
                offset = dx <= trigger ? dx : min(maxOffset, trigger + (dx - trigger) * 0.35)
                let nowArmed = offset >= trigger
                if nowArmed != armed { armed = nowArmed }
            }
            .onEnded { _ in
                axis = nil
                let swiped = armed
                if armed { armed = false }
                withAnimation(.spring(duration: 0.3)) { offset = 0 }
                if swiped { onReply() }
            }
    }
}

/// "ao vivo · google.com · 10:14" when it read prices live, else "3 fontes" (SourcesPill.tsx).
func sourcesLabel(_ sources: [Source], at: Date) -> String {
    let live = sources.filter { $0.source == "ao vivo" }
    guard !live.isEmpty else { return sources.count == 1 ? "1 fonte" : "\(sources.count) fontes" }
    var hosts: [String] = []
    for source in live {
        let host = (URL(string: source.url)?.host() ?? source.url).replacingOccurrences(of: "www.", with: "")
        if !hosts.contains(host) { hosts.append(host) }
    }
    let time = at.formatted(date: .omitted, time: .shortened)
    let others = sources.count - live.count
    return "ao vivo · " + hosts.prefix(2).joined(separator: ", ") + (hosts.count > 2 ? "…" : "") + " · \(time)"
        + (others > 0 ? " · +\(others)" : "")
}

/// The sources out of the way: a small pill that opens the list in a sheet.
private struct SourcesPill: View {
    let sources: [Source]
    let at: Date
    let open: () -> Void
    @Environment(\.palette) private var palette

    var body: some View {
        Button(action: open) {
            Text(sourcesLabel(sources, at: at))
                .font(Typo.mono(.caption2))
                .foregroundStyle(palette.tintaFraca)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .overlay(Capsule().strokeBorder(palette.linha))
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Fontes: \(sourcesLabel(sources, at: at))")
        .accessibilityHint("Abre a lista")
    }
}

private struct SourcesSheet: View {
    let sources: [Source]
    let at: Date
    @Environment(\.palette) private var palette

    var body: some View {
        NavigationStack {
            List(Array(sources.enumerated()), id: \.offset) { _, source in
                if let url = URL(string: source.url), ["http", "https"].contains(url.scheme ?? "") {
                    Link(destination: url) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source.title).font(Typo.text(.body)).foregroundStyle(palette.tinta)
                            Text(source.source == "ao vivo"
                                 ? "ao vivo · \(url.host() ?? "") · \(at.formatted(date: .omitted, time: .shortened))"
                                 : source.source)
                                .font(Typo.text(.footnote)).foregroundStyle(palette.tintaFraca)
                        }
                    }
                }
            }
            .navigationTitle("Fontes")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// Rating a reply, from its menu: thumbs and a few tags, the only evidence its way of answering
/// learns from (FeedbackBar.tsx).
private struct FeedbackSheet: View {
    let send: (Bool, [String]) async -> String?
    @Environment(\.palette) private var palette
    @Environment(\.dismiss) private var dismiss
    @State private var open = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Como foi essa resposta?").font(Typo.text(.headline))
            FeedbackBar(open: $open, send: send)
            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Thumbs and tags (inside FeedbackSheet).
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
                .frame(width: 44, height: 34)
                .overlay(Capsule().strokeBorder(palette.linhaForte))
                .frame(height: 44)
                .contentShape(Rectangle())
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
                .frame(minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}
