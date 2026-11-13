import SwiftUI
import UIKit
import VisaoKit

/// The message box of the "Neblina" look: the orb, then a glass pill with the text, + and send.
/// It sits in the bottom safe area of the chat, so it rides on top of the keyboard.
struct Composer: View {
    @Binding var text: String
    @Binding var replyTo: Message?
    var focused: FocusState<Bool>.Binding
    let draft: AttachmentDraft
    let thinking: Bool
    let speaker: String
    let onPick: (ChatScreen.Picker) -> Void
    let onSend: () -> Void
    @Environment(\.palette) private var palette

    /// Same limit as the API (MessageIn.content, 8000).
    private let maxLength = 8000

    private var canSend: Bool {
        !draft.isUploading && (!text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !draft.ready.isEmpty)
    }

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            Orb(thinking: thinking, size: 48)
            VStack(alignment: .leading, spacing: 0) {
                if let replyTo {
                    replyBanner(replyTo)
                }
                if !draft.items.isEmpty {
                    DraftAttachmentsRow(draft: draft)
                }
                HStack(alignment: .bottom, spacing: 4) {
                    TextField(draft.items.isEmpty ? "Escreva ou cole código…" : "Quer dizer algo sobre isso?", text: $text, axis: .vertical)
                        .font(Typo.text(.body))
                        .lineLimit(1...6)
                        .focused(focused)
                        .padding(.leading, 10)
                        .padding(.vertical, 10)
                        .onChange(of: text) { _, value in
                            if value.count > maxLength { text = String(value.prefix(maxLength)) }
                        }
                        .accessibilityLabel("Mensagem")
                    attachMenu
                    if canSend {
                        Button(action: onSend) {
                            Image(systemName: "arrow.up")
                                .font(.body.weight(.semibold))
                                .foregroundStyle(palette.pilulaAtivaTinta)
                                .frame(width: 40, height: 40)
                                .background(palette.pilulaAtiva, in: Circle())
                        }
                        .buttonStyle(.plain)
                        .keyboardShortcut(.return, modifiers: .command)
                        .accessibilityLabel("Enviar mensagem")
                        .transition(.scale.combined(with: .opacity))
                    }
                }
            }
            .padding(4)
            .padding(.leading, 2)
            .glass(palette, cornerRadius: 26)
        }
        .padding(.horizontal, 10)
        .padding(.top, 6)
        .padding(.bottom, 8)
        .animation(.easeOut(duration: 0.18), value: canSend)
        .animation(.easeOut(duration: 0.2), value: replyTo?.id)
        .animation(.easeOut(duration: 0.2), value: draft.items.count)
    }

    private var attachMenu: some View {
        Menu {
            Button("Fotos", systemImage: "photo.on.rectangle") { onPick(.photos) }
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button("Câmera", systemImage: "camera") { onPick(.camera) }
            }
            Button("Arquivos", systemImage: "folder") { onPick(.files) }
        } label: {
            Image(systemName: "plus")
                .font(.title3)
                .frame(width: 40, height: 40)
                .contentShape(Rectangle())
        }
        .disabled(draft.room <= 0)
        .accessibilityLabel("Anexar foto ou arquivo")
    }

    private func replyBanner(_ message: Message) -> some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Respondendo a \(message.role == .assistant ? speaker : "você")")
                    .font(Typo.text(.caption, weight: .medium))
                    .foregroundStyle(palette.estanho)
                Text(Message.oneLine(message.content, limit: 120))
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.tintaSuave)
                    .lineLimit(2)
            }
            Spacer()
            Button {
                replyTo = nil
            } label: {
                Image(systemName: "xmark")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(palette.tintaFraca)
                    .frame(width: 26, height: 26)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Não responder a essa mensagem")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(palette.fundoHover, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(alignment: .leading) {
            UnevenRoundedRectangle(topLeadingRadius: 16, bottomLeadingRadius: 16)
                .fill(palette.estanho)
                .frame(width: 3)
        }
        .padding(4)
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }
}
