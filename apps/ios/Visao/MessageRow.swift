import SwiftUI
import UIKit
import VisaoKit

enum Theme {
    static let userBubble = Color.accentColor.opacity(0.22)
    static let assistantBubble = Color(uiColor: .secondarySystemBackground)
}

struct MessageRow: View {
    let message: Message
    let speaker: String
    let onReply: () -> Void
    let onQuoteTap: (String) -> Void

    /// Past this, letting go answers the message (as SwipeReply.tsx on the web).
    private let trigger: CGFloat = 56
    private let maxOffset: CGFloat = 84
    @State private var offset: CGFloat = 0
    @State private var armed = false

    private var isUser: Bool { message.role == .user }
    private var canReply: Bool { message.local == nil }

    var body: some View {
        HStack {
            if isUser { Spacer(minLength: 40) }
            bubble
            if !isUser { Spacer(minLength: 24) }
        }
        .background(alignment: .leading) {
            if offset > 0 {
                Image(systemName: "arrowshape.turn.up.left.fill")
                    .foregroundStyle(armed ? Color.accentColor : .secondary)
                    .scaleEffect(armed ? 1.15 : 0.9)
                    .opacity(Double(min(offset / trigger, 1)))
                    .offset(x: max(0, offset / 2 - 10))
                    .accessibilityHidden(true)
            }
        }
        .simultaneousGesture(swipe)
        .sensoryFeedback(.impact(weight: .light), trigger: armed) { _, isArmed in isArmed }
    }

    private var bubble: some View {
        VStack(alignment: .leading, spacing: 8) {
            meta
            if let quote = message.replyTo {
                Button { onQuoteTap(quote.id) } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(quote.role == .assistant ? speaker : "Você")
                            .font(.caption.weight(.semibold))
                        Text(quote.excerpt)
                            .font(.caption)
                            .lineLimit(2)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                    .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(alignment: .leading) {
                        Rectangle().fill(Color.accentColor).frame(width: 3)
                            .clipShape(RoundedRectangle(cornerRadius: 2))
                    }
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Respondendo a \(quote.role == .assistant ? speaker : "você"): \(quote.excerpt)")
                .accessibilityHint("Vai para a mensagem")
            }
            if !message.attachments.isEmpty {
                AttachmentChips(attachments: message.attachments)
            }
            if !message.content.isEmpty {
                MarkdownView(text: message.content)
            }
            if !message.sources.isEmpty {
                SourcesList(sources: message.sources)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(isUser ? Theme.userBubble : Theme.assistantBubble, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .opacity(message.local == .sending || message.local == .queued ? 0.6 : 1)
        .offset(x: offset)
        .contextMenu {
            if canReply {
                Button("Responder", systemImage: "arrowshape.turn.up.left", action: onReply)
            }
            Button("Copiar", systemImage: "doc.on.doc") { UIPasteboard.general.string = message.content }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Responder") { if canReply { onReply() } }
    }

    private var meta: some View {
        HStack(spacing: 6) {
            Text(isUser ? "Você" : speaker).font(.caption.weight(.semibold))
            if let tag = originTag {
                Text(tag)
                    .font(.caption2.weight(.medium))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 1)
                    .background(.quaternary, in: Capsule())
            }
            switch message.local {
            case .failed: Text("não foi enviada").font(.caption).foregroundStyle(.red)
            case .stopped: Text("parada").font(.caption).foregroundStyle(.orange)
            case .queued: Text("na fila").font(.caption).foregroundStyle(.secondary)
            case .sending, .none:
                Text(message.createdAt, format: .dateTime.hour().minute())
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .foregroundStyle(.primary)
    }

    private var originTag: String? {
        switch message.origin {
        case "initiative": "puxou conversa"
        case "arm": "no Mac"
        case "google": "no Google"
        default: nil
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

private struct AttachmentChips: View {
    let attachments: [Attachment]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(attachments) { attachment in
                Label(attachment.filename, systemImage: attachment.isImage ? "photo" : "doc.text")
                    .font(.footnote)
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct SourcesList: View {
    let sources: [Source]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Fontes").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(Array(sources.enumerated()), id: \.offset) { index, source in
                if let url = URL(string: source.url), ["http", "https"].contains(url.scheme ?? "") {
                    Link(destination: url) {
                        (Text("\(index + 1). \(source.title)")
                            + Text(" · \(source.source)").foregroundColor(.secondary))
                            .font(.footnote)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Fontes pesquisadas")
    }
}
