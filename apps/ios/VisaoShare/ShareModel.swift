import LinkPresentation
import Observation
import UIKit
import UniformTypeIdentifiers
import VisaoKit

/// What was picked in the other app, read into a `ShareContent`, and the send.
@MainActor
@Observable
final class ShareModel {
    private(set) var content = ShareContent()
    private(set) var thumbnail: UIImage?
    private(set) var loading = true
    /// A file that could not go (too big, unreadable); the rest still goes.
    private(set) var problem: String?
    var note = ""
    let sender: ShareSender
    private let close: () -> Void

    init(api: APIClient, close: @escaping () -> Void) {
        sender = ShareSender(api: api)
        self.close = close
        // Without a token there is nothing to do here: say so and close.
        if !api.isAuthenticated { signedOut() }
    }

    var canSend: Bool {
        !loading && sender.state != .sending && sender.state != .sent
            && (content.url != nil || content.text != nil || !content.files.isEmpty || !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }

    func load(_ items: [NSExtensionItem]) async {
        defer { loading = false }
        var url: URL?
        var title: String?
        var texts: [String] = []
        var files: [PreparedFile] = []
        for item in items {
            if title == nil, let text = (item.attributedTitle ?? item.attributedContentText)?.string, !text.isEmpty {
                title = text
            }
            for provider in item.attachments ?? [] {
                if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                    guard files.count < AttachmentRules.maxPerMessage else { continue }
                    if let file = await image(provider, index: files.count) { files.append(file) }
                } else if provider.hasItemConformingToTypeIdentifier(UTType.pdf.identifier) {
                    guard files.count < AttachmentRules.maxPerMessage else { continue }
                    if let file = await pdf(provider, index: files.count) { files.append(file) }
                } else if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
                    if url == nil, let found = await loadURL(provider), ["http", "https"].contains(found.scheme?.lowercased()) {
                        url = found
                    }
                } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                    guard let text = await loadText(provider)?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { continue }
                    // A link shared as text (many apps do it) is a link.
                    if url == nil, let link = URL(string: text), ["http", "https"].contains(link.scheme?.lowercased()), link.host != nil, !text.contains(" ") {
                        url = link
                    } else {
                        texts.append(text)
                    }
                }
            }
        }
        // The title some apps send is the link itself, or the same text: not a title then.
        if let t = title, t == url?.absoluteString || texts.contains(t) { title = nil }
        content = ShareContent(url: url, title: title, text: texts.isEmpty ? nil : texts.joined(separator: "\n\n"), files: files)
        if let first = files.first(where: { $0.mimeType.hasPrefix("image/") }) {
            thumbnail = (try? ImagePreparation.thumbnail(first.data, maxSide: 240)).flatMap(UIImage.init(data:))
        }
        if let url, content.title == nil { await fetchTitle(url) }
    }

    func send() async {
        // The same switch as the app's (App Group); without "Durante o uso", nothing is asked.
        await sender.send(content, note: note) { text in
            await LocationPrefs.position(for: text, enabled: LocationPrefs.enabled(), source: DevicePosition())
        }
        switch sender.state {
        case .sent:
            try? await Task.sleep(for: .seconds(1))
            close()
        case .signedOut:
            signedOut()
        default:
            break
        }
    }

    func cancel() { close() }

    private func signedOut() {
        Task {
            try? await Task.sleep(for: .seconds(2))
            close()
        }
    }

    // MARK: Reading the providers

    private func image(_ provider: NSItemProvider, index: Int) async -> PreparedFile? {
        guard let data = await loadData(provider, type: .image) else {
            problem = "Uma imagem não pôde ser lida."
            return nil
        }
        let name = provider.suggestedName ?? "imagem-\(index + 1)"
        // Shrunk before it goes up: the extension has little memory, and the server only looks at
        // 1568 px anyway.
        do {
            return try await Task.detached(priority: .userInitiated) { try ImagePreparation.prepare(data, filename: name) }.value
        } catch {
            problem = (error as? LocalizedError)?.errorDescription
            return nil
        }
    }

    private func pdf(_ provider: NSItemProvider, index: Int) async -> PreparedFile? {
        guard let data = await loadData(provider, type: .pdf) else {
            problem = "Um PDF não pôde ser lido."
            return nil
        }
        guard data.count <= AttachmentRules.maxDocumentBytes else {
            problem = AttachmentError.tooLarge(limit: AttachmentRules.maxDocumentBytes).errorDescription
            return nil
        }
        var name = provider.suggestedName ?? "documento-\(index + 1)"
        if !name.lowercased().hasSuffix(".pdf") { name += ".pdf" }
        return PreparedFile(data: data, filename: name, mimeType: "application/pdf")
    }

    private func loadData(_ provider: NSItemProvider, type: UTType) async -> Data? {
        await withCheckedContinuation { continuation in
            _ = provider.loadDataRepresentation(for: type) { data, _ in continuation.resume(returning: data) }
        }
    }

    private func loadURL(_ provider: NSItemProvider) async -> URL? {
        await withCheckedContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, _ in continuation.resume(returning: url) }
        }
    }

    private func loadText(_ provider: NSItemProvider) async -> String? {
        await withCheckedContinuation { continuation in
            _ = provider.loadObject(ofClass: String.self) { text, _ in continuation.resume(returning: text) }
        }
    }

    /// The page's title for the preview when the app did not send one (3 s at most).
    private func fetchTitle(_ url: URL) async {
        let metadata = LPMetadataProvider()
        metadata.timeout = 3
        guard let title = try? await metadata.startFetchingMetadata(for: url).title, !title.isEmpty else { return }
        content.title = title
    }
}
