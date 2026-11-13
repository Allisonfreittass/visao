import SwiftUI
import VisaoKit

/// The message box. It sits in the bottom safe area of the chat, so it rides on top of the
/// keyboard and the messages scroll behind it.
struct Composer: View {
    @Binding var draft: String
    @Binding var replyTo: Message?
    var focused: FocusState<Bool>.Binding
    let speaker: String
    let onSend: () -> Void

    /// Same limit as the API (MessageIn.content, 8000).
    private let maxLength = 8000

    private var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 8) {
            if let replyTo {
                HStack(alignment: .top, spacing: 8) {
                    Rectangle().fill(Color.accentColor).frame(width: 3)
                        .clipShape(RoundedRectangle(cornerRadius: 2))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Respondendo a \(replyTo.role == .assistant ? speaker : "você")")
                            .font(.caption.weight(.semibold))
                        Text(Message.oneLine(replyTo.content, limit: 120))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    Spacer()
                    Button {
                        withAnimation { self.replyTo = nil }
                    } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Não responder a essa mensagem")
                }
                .fixedSize(horizontal: false, vertical: true)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Escreva ou cole código…", text: $draft, axis: .vertical)
                    .lineLimit(1...6)
                    .focused(focused)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(Color(uiColor: .secondarySystemBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                    .onChange(of: draft) { _, value in
                        if value.count > maxLength { draft = String(value.prefix(maxLength)) }
                    }
                    .accessibilityLabel("Mensagem")
                Button(action: onSend) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(.title, design: .rounded))
                        .symbolRenderingMode(.hierarchical)
                }
                .disabled(!canSend)
                .keyboardShortcut(.return, modifiers: .command)
                .accessibilityLabel("Enviar mensagem")
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 8)
        .background(.bar)
        .animation(.easeOut(duration: 0.2), value: replyTo?.id)
    }
}
