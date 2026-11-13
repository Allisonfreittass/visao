import PhotosUI
import QuickLook
import SwiftUI
import UIKit
import VisaoKit

/// Downloads a message's photos and files with the token, once per session.
@MainActor
final class AttachmentLoader {
    private let api: APIClient
    private var images: [String: UIImage] = [:]
    private var loading: [String: Task<UIImage?, Never>] = [:]
    private var files: [String: URL] = [:]

    init(api: APIClient) {
        self.api = api
    }

    func cachedImage(_ id: String) -> UIImage? { images[id] }

    func image(_ id: String) async -> UIImage? {
        if let image = images[id] { return image }
        if let task = loading[id] { return await task.value }
        let api = self.api
        let task = Task<UIImage?, Never> {
            guard let data = try? await api.attachmentData(id: id) else { return nil }
            return await Task.detached { UIImage(data: data)?.preparingForDisplay() }.value
        }
        loading[id] = task
        let image = await task.value
        loading[id] = nil
        if let image { images[id] = image }
        return image
    }

    /// A local copy with its own name, for Quick Look and the share sheet.
    func file(_ attachment: Attachment) async throws -> URL {
        if let url = files[attachment.id] { return url }
        let data = try await api.attachmentData(id: attachment.id)
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("anexos/\(attachment.id)", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let name = attachment.filename.replacingOccurrences(of: "/", with: "-")
        let url = folder.appendingPathComponent(name.isEmpty ? "arquivo" : name)
        try data.write(to: url, options: .completeFileProtection)
        files[attachment.id] = url
        return url
    }
}

private struct LoaderKey: EnvironmentKey {
    static let defaultValue: AttachmentLoader? = nil
}

extension EnvironmentValues {
    var attachmentLoader: AttachmentLoader? {
        get { self[LoaderKey.self] }
        set { self[LoaderKey.self] = newValue }
    }
}

/// The photos and files under a message, as on the web: photos in a grid, files as chips.
/// Tapping opens them in Quick Look, which also has the share button.
struct MessageAttachments: View {
    let attachments: [Attachment]
    @Environment(\.attachmentLoader) private var loader
    @Environment(\.palette) private var palette
    @State private var preview: URL?
    @State private var opening: String?

    private var photos: [Attachment] { attachments.filter(\.isImage) }
    private var documents: [Attachment] { attachments.filter { !$0.isImage } }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !photos.isEmpty {
                let columns = Array(repeating: GridItem(.flexible(), spacing: 4), count: photos.count == 3 ? 3 : min(photos.count, 2))
                LazyVGrid(columns: columns, spacing: 4) {
                    ForEach(photos) { photo in
                        Button { open(photo) } label: {
                            AttachmentImage(id: photo.id, single: photos.count == 1)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Foto \(photo.filename)")
                    }
                }
                .frame(maxWidth: 360)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
            ForEach(documents) { file in
                Button { open(file) } label: {
                    FileChip(name: file.filename, detail: detail(file), busy: opening == file.id)
                }
                .buttonStyle(.plain)
            }
        }
        .quickLookPreview($preview)
    }

    private func detail(_ file: Attachment) -> String {
        let size = AttachmentRules.formatSize(file.sizeBytes)
        return file.readable == false ? "\(size) · sem texto para ler" : size
    }

    private func open(_ attachment: Attachment) {
        guard let loader, opening == nil else { return }
        opening = attachment.id
        Task {
            defer { opening = nil }
            preview = try? await loader.file(attachment)
        }
    }
}

/// A photo loaded through the API with the token.
struct AttachmentImage: View {
    let id: String
    var single = false
    @Environment(\.attachmentLoader) private var loader
    @Environment(\.palette) private var palette
    @State private var image: UIImage?

    var body: some View {
        Group {
            if let image {
                if single {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 320)
                } else {
                    Color.clear
                        .frame(height: 140)
                        .overlay { Image(uiImage: image).resizable().scaledToFill() }
                        .clipped()
                }
            } else {
                palette.fundoHover
                    .frame(height: single ? 180 : 140)
                    .overlay { ProgressView() }
            }
        }
        .task(id: id) {
            image = loader?.cachedImage(id)
            if image == nil { image = await loader?.image(id) }
        }
    }
}

/// A file as a chip: its extension in a tile, the name and a detail line.
struct FileChip: View {
    let name: String
    let detail: String
    var busy = false
    var failed = false
    @Environment(\.palette) private var palette

    var body: some View {
        HStack(spacing: 10) {
            Text(ext)
                .font(Typo.mono(.caption2).weight(.medium))
                .tracking(0.6)
                .foregroundStyle(palette.estanho)
                .frame(width: 40, height: 40)
                .background(palette.fundoHover, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                .overlay { if busy { ProgressView() } }
            VStack(alignment: .leading, spacing: 1) {
                Text(name)
                    .font(Typo.text(.subheadline, weight: .medium))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(detail)
                    .font(Typo.text(.caption))
                    .foregroundStyle(failed ? palette.erro : palette.tintaFraca)
                    .lineLimit(2)
            }
            Spacer(minLength: 0)
        }
        .padding(6)
        .padding(.trailing, 6)
        .frame(maxWidth: 320, alignment: .leading)
        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(failed ? palette.erro : palette.linhaForte))
        .accessibilityElement(children: .combine)
    }

    private var ext: String {
        let value = (name as NSString).pathExtension.uppercased()
        return value.isEmpty ? "ARQ" : String(value.prefix(4))
    }
}

/// What waits in the message box before sending: photos as thumbnails, files as chips, each with
/// its upload state and a button to take it out.
struct DraftAttachmentsRow: View {
    let draft: AttachmentDraft
    @Environment(\.palette) private var palette

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(draft.items) { item in
                    ZStack(alignment: .topTrailing) {
                        content(item)
                        Button {
                            withAnimation { draft.remove(item.id) }
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .symbolRenderingMode(.palette)
                                .foregroundStyle(palette.pilulaAtivaTinta, palette.pilulaAtiva)
                                .font(.title3)
                        }
                        .buttonStyle(.plain)
                        .offset(x: 6, y: -6)
                        .accessibilityLabel("Tirar \(item.filename)")
                    }
                }
            }
            .padding(.top, 8)
            .padding(.horizontal, 4)
        }
    }

    @ViewBuilder
    private func content(_ item: AttachmentDraft.Item) -> some View {
        let failed: String? = if case .failed(let why) = item.status { why } else { nil }
        if item.isImage, let data = item.preview, let image = UIImage(data: data), failed == nil {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: 56, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .opacity(item.status == .uploading ? 0.55 : 1)
                .overlay { if item.status == .uploading { ProgressView() } }
                .accessibilityLabel(item.filename)
        } else {
            FileChip(
                name: item.filename,
                detail: failed ?? (item.status == .uploading ? "Enviando…" : "Pronto"),
                busy: item.status == .uploading,
                failed: failed != nil
            )
            .frame(width: 220)
        }
    }
}

/// The camera, for a photo taken right now.
struct CameraPicker: UIViewControllerRepresentable {
    let onPhoto: (Data) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker

        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.9) {
                parent.onPhoto(data)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

/// "foto-14h05.jpg", like the web names pasted prints.
func photoName(index: Int, ext: String) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "HH'h'mm"
    let stamp = formatter.string(from: Date())
    return "foto-\(stamp)\(index > 0 ? "-\(index + 1)" : "").\(ext)"
}
