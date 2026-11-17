import SwiftUI
import VisaoKit

/// The sheet: what goes (link, picture, the start of the text), a comment, Enviar. The app's
/// colors (Theme.swift, "Neblina" by day and by night), on a plain card.
struct ShareView: View {
    @Bindable var model: ShareModel
    @Environment(\.colorScheme) private var scheme
    @FocusState private var noteFocused: Bool

    private var ink: Color { scheme == .dark ? Color(rgb: 0xf5f5f7) : Color(rgb: 0x17222a) }
    private var soft: Color { scheme == .dark ? Color(rgb: 0xc7cbd8) : Color(rgb: 0x36454e) }
    private var faint: Color { scheme == .dark ? Color(rgb: 0x9aa0b4) : Color(rgb: 0x56656e) }
    private var tin: Color { scheme == .dark ? Color(rgb: 0xa9bcbd) : Color(rgb: 0x4f6366) }
    private var card: Color { scheme == .dark ? Color(rgb: 0x1c2034) : Color(rgb: 0xf4f7f8) }
    private var well: Color { scheme == .dark ? Color(rgb: 0xf5f5f7, opacity: 0.08) : Color(rgb: 0x17222a, opacity: 0.05) }
    private var errorColor: Color { scheme == .dark ? Color(rgb: 0xff7a6e) : Color(rgb: 0xb3342b) }
    private var primary: Color { scheme == .dark ? Color(rgb: 0xf5f5f7) : Color(rgb: 0x2e3d45) }
    private var primaryInk: Color { scheme == .dark ? Color(rgb: 0x1d1d1f) : Color(rgb: 0xeef2f3) }

    var body: some View {
        VStack(spacing: 0) {
            Spacer(minLength: 0)
            VStack(alignment: .leading, spacing: 16) {
                header
                switch model.sender.state {
                case .signedOut:
                    message(ShareSender.signedOutText, color: ink)
                case .sent:
                    message(ShareSender.sentText, color: ink)
                default:
                    form
                }
            }
            .padding(20)
            .frame(maxWidth: 520)
            .background(card, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
            .shadow(color: .black.opacity(0.18), radius: 24, y: 8)
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.opacity(0.2).ignoresSafeArea().onTapGesture { noteFocused = false })
    }

    private var header: some View {
        HStack {
            Button("Cancelar") { model.cancel() }
                .font(.subheadline)
                .foregroundStyle(soft)
                .frame(minWidth: 44, minHeight: 44)
                .disabled(model.sender.state == .sending)
            Spacer()
            Text("Visão")
                .font(.system(.title3, design: .serif))
                .foregroundStyle(ink)
            Spacer()
            Color.clear.frame(width: 70, height: 44)
        }
    }

    @ViewBuilder
    private var form: some View {
        preview
        VStack(alignment: .leading, spacing: 6) {
            Text("Comentário")
                .font(.caption.weight(.medium))
                .foregroundStyle(faint)
            TextField("“vale a pena?”, “cota isso pra agosto”", text: $model.note, axis: .vertical)
                .lineLimit(1...4)
                .focused($noteFocused)
                .font(.body)
                .foregroundStyle(ink)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(well, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        if let problem = model.problem {
            Text(problem).font(.footnote).foregroundStyle(errorColor)
        }
        if case .failed(let reason) = model.sender.state {
            Label(reason, systemImage: "exclamationmark.triangle")
                .font(.footnote)
                .foregroundStyle(errorColor)
        }
        Button {
            noteFocused = false
            Task { await model.send() }
        } label: {
            HStack(spacing: 8) {
                if model.sender.state == .sending { ProgressView().tint(primaryInk) }
                Text(sendTitle).font(.body.weight(.medium))
            }
            .foregroundStyle(primaryInk)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(primary, in: Capsule())
            .opacity(model.canSend ? 1 : 0.45)
        }
        .buttonStyle(.plain)
        .disabled(!model.canSend)
    }

    private var sendTitle: String {
        switch model.sender.state {
        case .sending: "Enviando…"
        case .failed: "Tentar de novo"
        default: "Enviar"
        }
    }

    @ViewBuilder
    private var preview: some View {
        if model.loading {
            HStack(spacing: 10) {
                ProgressView()
                Text("Lendo o que você escolheu…").font(.footnote).foregroundStyle(soft)
            }
        } else {
            HStack(alignment: .top, spacing: 12) {
                if let thumbnail = model.thumbnail {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .scaledToFill()
                        .frame(width: 64, height: 64)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .accessibilityLabel("Imagem")
                } else if model.content.files.contains(where: { $0.mimeType == "application/pdf" }) {
                    Image(systemName: "doc.richtext")
                        .font(.title2)
                        .foregroundStyle(tin)
                        .frame(width: 64, height: 64)
                        .background(well, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                VStack(alignment: .leading, spacing: 4) {
                    if let title = model.content.title {
                        Text(title).font(.subheadline.weight(.medium)).foregroundStyle(ink).lineLimit(2)
                    }
                    if let domain = model.content.domain {
                        Label(domain, systemImage: "link").font(.footnote).foregroundStyle(tin).lineLimit(1)
                    }
                    if let text = model.content.text {
                        Text(text.prefix(220)).font(.footnote).foregroundStyle(soft).lineLimit(4)
                    }
                    if !model.content.files.isEmpty {
                        Text(filesLabel).font(.caption).foregroundStyle(faint)
                    }
                    if model.content.url == nil && model.content.text == nil && model.content.files.isEmpty {
                        Text("Nada que eu consiga ler aqui. Escreva um comentário, se quiser mandar mesmo assim.")
                            .font(.footnote).foregroundStyle(soft)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(12)
            .background(well, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
    }

    private var filesLabel: String {
        let images = model.content.files.filter { $0.mimeType.hasPrefix("image/") }.count
        let pdfs = model.content.files.count - images
        var parts: [String] = []
        if images > 0 { parts.append("\(images) \(images == 1 ? "imagem" : "imagens")") }
        if pdfs > 0 { parts.append("\(pdfs) \(pdfs == 1 ? "PDF" : "PDFs")") }
        return parts.joined(separator: " · ")
    }

    private func message(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.system(.title3, design: .serif))
            .foregroundStyle(color)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity, minHeight: 80)
    }
}

extension Color {
    init(rgb: UInt32, opacity: Double = 1) {
        self.init(
            red: Double((rgb >> 16) & 0xff) / 255, green: Double((rgb >> 8) & 0xff) / 255,
            blue: Double(rgb & 0xff) / 255, opacity: opacity
        )
    }
}
