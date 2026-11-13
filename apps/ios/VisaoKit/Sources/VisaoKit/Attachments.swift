import Foundation
import ImageIO
import Observation
import UniformTypeIdentifiers

/// What the server accepts (docs/ANEXOS.md, core/conversation/attachments.py). The server decides
/// by the bytes either way; this only spares a pointless upload and says why up front.
public enum AttachmentRules {
    public static let maxPerMessage = 4
    public static let maxImageBytes = 5 * 1024 * 1024
    public static let maxDocumentBytes = 10 * 1024 * 1024
    /// The long side a vision model actually looks at; anything bigger only costs upload time.
    public static let maxImageSide = 1568
    /// Photos that already fit are sent untouched unless heavier than this.
    public static let reencodeAboveBytes = 1_572_864
    public static let jpegQuality = 0.85

    /// Formats the server takes as a photo as they are. Everything else (HEIC from the iPhone
    /// camera, TIFF, …) becomes a JPEG first.
    static let sendableImageTypes: Set<String> = [UTType.jpeg.identifier, UTType.png.identifier, UTType.webP.identifier, UTType.gif.identifier]

    /// What the Files picker offers: photos, PDF and text or code.
    public static let documentTypes: [UTType] = {
        var types: [UTType] = [.pdf, .plainText, .commaSeparatedText, .tabSeparatedText, .json, .xml, .html, .yaml, .sourceCode, .swiftSource, .pythonScript, .shellScript, .javaScript, .image]
        for ext in ["md", "markdown", "ts", "tsx", "jsx", "kt", "go", "rs", "rb", "php", "cs", "toml", "ini", "vue", "dart", "sql", "log"] {
            if let type = UTType(filenameExtension: ext) { types.append(type) }
        }
        return types
    }()

    public static func mimeType(forFilename name: String) -> String {
        let ext = (name as NSString).pathExtension
        return UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
    }

    /// "120 KB", "1,4 MB", as the web shows it.
    public static func formatSize(_ bytes: Int) -> String {
        if bytes < 1024 { return "\(bytes) B" }
        if bytes < 1024 * 1024 { return "\(Int((Double(bytes) / 1024).rounded())) KB" }
        let mb = Double(bytes) / (1024 * 1024)
        return String(format: "%.1f MB", mb).replacingOccurrences(of: ".", with: ",")
    }
}

/// A photo ready to travel: its bytes, name and type.
public struct PreparedFile: Sendable, Equatable {
    public let data: Data
    public let filename: String
    public let mimeType: String

    public init(data: Data, filename: String, mimeType: String) {
        self.data = data
        self.filename = filename
        self.mimeType = mimeType
    }
}

public enum AttachmentError: Error, LocalizedError, Equatable {
    case tooLarge(limit: Int)
    case unreadableImage

    public var errorDescription: String? {
        switch self {
        case .tooLarge(let limit): "Grande demais (máximo \(AttachmentRules.formatSize(limit)))."
        case .unreadableImage: "Não deu para ler essa imagem."
        }
    }
}

public enum ImagePreparation {
    /// The size a photo goes at: the long side down to 1568 px, never up.
    public static func targetSize(width: Int, height: Int, maxSide: Int = AttachmentRules.maxImageSide) -> (width: Int, height: Int) {
        let long = max(width, height)
        guard long > maxSide else { return (width, height) }
        let scale = Double(maxSide) / Double(long)
        return (Int((Double(width) * scale).rounded()), Int((Double(height) * scale).rounded()))
    }

    /// Shrinks and converts a photo the way the web does before upload: GIFs stay as they are
    /// (animation), a JPEG/PNG/WebP that already fits stays, everything else becomes a JPEG of at
    /// most 1568 px with the camera's rotation applied.
    public static func prepare(_ data: Data, filename: String) throws -> PreparedFile {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil), let type = CGImageSourceGetType(source) as String? else {
            throw AttachmentError.unreadableImage
        }
        let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] ?? [:]
        let width = properties[kCGImagePropertyPixelWidth] as? Int ?? 0
        let height = properties[kCGImagePropertyPixelHeight] as? Int ?? 0
        let orientation = properties[kCGImagePropertyOrientation] as? Int ?? 1
        let base = (filename as NSString).deletingPathExtension.isEmpty ? "foto" : (filename as NSString).deletingPathExtension

        if type == UTType.gif.identifier {
            guard data.count <= AttachmentRules.maxImageBytes else { throw AttachmentError.tooLarge(limit: AttachmentRules.maxImageBytes) }
            return PreparedFile(data: data, filename: named(filename, base: base, ext: "gif"), mimeType: "image/gif")
        }
        let fits = max(width, height) <= AttachmentRules.maxImageSide && data.count <= AttachmentRules.reencodeAboveBytes && orientation == 1
        if AttachmentRules.sendableImageTypes.contains(type), fits {
            let mime = UTType(type)?.preferredMIMEType ?? "image/jpeg"
            let ext = UTType(type)?.preferredFilenameExtension ?? "jpg"
            return PreparedFile(data: data, filename: named(filename, base: base, ext: ext), mimeType: mime)
        }

        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: min(max(width, height, 1), AttachmentRules.maxImageSide),
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else {
            throw AttachmentError.unreadableImage
        }
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else {
            throw AttachmentError.unreadableImage
        }
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: AttachmentRules.jpegQuality] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw AttachmentError.unreadableImage }
        let jpeg = out as Data
        guard jpeg.count <= AttachmentRules.maxImageBytes else { throw AttachmentError.tooLarge(limit: AttachmentRules.maxImageBytes) }
        return PreparedFile(data: jpeg, filename: "\(base).jpg", mimeType: "image/jpeg")
    }

    private static func named(_ filename: String, base: String, ext: String) -> String {
        (filename as NSString).pathExtension.isEmpty ? "\(base).\(ext)" : filename
    }
}

/// The photos and files waiting in the message box: each one uploads as soon as it is picked, so
/// sending is instant. Up to 4 per message.
@MainActor
@Observable
public final class AttachmentDraft {
    public enum Status: Equatable, Sendable {
        case uploading
        case ready(Attachment)
        case failed(String)
    }

    public struct Item: Identifiable, Equatable {
        public let id: UUID
        public let filename: String
        public let isImage: Bool
        /// A small local preview of a photo (JPEG bytes), shown while it uploads.
        public let preview: Data?
        public var status: Status
    }

    public private(set) var items: [Item] = []
    private let api: APIClient

    public init(api: APIClient) {
        self.api = api
    }

    public var room: Int { AttachmentRules.maxPerMessage - items.count }
    public var isUploading: Bool { items.contains { $0.status == .uploading } }
    public var ready: [Attachment] {
        items.compactMap { if case .ready(let a) = $0.status { a } else { nil } }
    }

    /// A photo: shrunk and converted, then uploaded.
    public func addImage(_ data: Data, filename: String) {
        guard room > 0 else { return }
        let preview = try? ImagePreparation.thumbnail(data, maxSide: 160)
        start(filename: filename, isImage: true, preview: preview) {
            let prepared = try await Task.detached(priority: .userInitiated) { try ImagePreparation.prepare(data, filename: filename) }.value
            return prepared
        }
    }

    /// A file from Files: a photo goes through addImage, anything else as it is (up to 10 MB).
    public func addFile(_ data: Data, filename: String) {
        guard room > 0 else { return }
        if let type = UTType(filenameExtension: (filename as NSString).pathExtension), type.conforms(to: .image) {
            addImage(data, filename: filename)
            return
        }
        start(filename: filename, isImage: false, preview: nil) {
            guard data.count <= AttachmentRules.maxDocumentBytes else { throw AttachmentError.tooLarge(limit: AttachmentRules.maxDocumentBytes) }
            return PreparedFile(data: data, filename: filename, mimeType: AttachmentRules.mimeType(forFilename: filename))
        }
    }

    public func remove(_ id: UUID) {
        items.removeAll { $0.id == id }
    }

    /// After sending: the box is empty again.
    public func clear() {
        items = []
    }

    private func start(filename: String, isImage: Bool, preview: Data?, prepare: @escaping @Sendable () async throws -> PreparedFile) {
        let id = UUID()
        items.append(Item(id: id, filename: filename, isImage: isImage, preview: preview, status: .uploading))
        let api = self.api
        Task {
            let status: Status
            do {
                let file = try await prepare()
                let attachment = try await api.uploadAttachment(data: file.data, filename: file.filename, mimeType: file.mimeType)
                status = .ready(attachment)
            } catch {
                status = .failed((error as? LocalizedError)?.errorDescription ?? "Não deu para enviar")
            }
            if let index = items.firstIndex(where: { $0.id == id }) { items[index].status = status }
        }
    }
}

extension ImagePreparation {
    /// A small JPEG for previews (the message box and the bubbles).
    public static func thumbnail(_ data: Data, maxSide: Int) throws -> Data {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { throw AttachmentError.unreadableImage }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maxSide,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { throw AttachmentError.unreadableImage }
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else { throw AttachmentError.unreadableImage }
        CGImageDestinationAddImage(destination, image, [kCGImageDestinationLossyCompressionQuality: 0.8] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw AttachmentError.unreadableImage }
        return out as Data
    }
}
