import Foundation
import Observation

// The share sheet (docs/COMPARTILHAR.md, ADR-0018): files go first through POST /attachments,
// then POST /share answers 202 at once and the reply arrives as a notice and in the continuous
// conversation. The extension never waits for it.

/// The body of POST /share, with only the fields there are.
public struct ShareRequest: Encodable, Sendable, Equatable {
    public var note: String?
    public var url: String?
    public var title: String?
    public var text: String?
    public var attachmentIds: [String]
    public var location: SentLocation?

    public init(note: String? = nil, url: String? = nil, title: String? = nil, text: String? = nil, attachmentIds: [String] = [], location: SentLocation? = nil) {
        self.note = Self.clean(note)
        self.url = Self.clean(url)
        self.title = Self.clean(title)
        self.text = Self.clean(text)
        self.attachmentIds = attachmentIds
        self.location = location
    }

    enum CodingKeys: String, CodingKey {
        case note, url, title, text, location
        case attachmentIds = "attachment_ids"
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(note, forKey: .note)
        try c.encodeIfPresent(url, forKey: .url)
        try c.encodeIfPresent(title, forKey: .title)
        try c.encodeIfPresent(text, forKey: .text)
        if !attachmentIds.isEmpty { try c.encode(attachmentIds, forKey: .attachmentIds) }
        try c.encodeIfPresent(location, forKey: .location)
    }

    /// Nothing at all to send: the server would answer 422.
    public var isEmpty: Bool { note == nil && url == nil && text == nil && attachmentIds.isEmpty }

    private static func clean(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}

/// What POST /share answers (202): the conversation it went to and the message as written.
public struct ShareReceipt: Decodable, Sendable {
    public let conversationId: String
    public let content: String

    enum CodingKeys: String, CodingKey {
        case content
        case conversationId = "conversation_id"
    }
}

extension APIClient {
    public func share(_ body: ShareRequest) async throws -> ShareReceipt {
        try await json("/share", method: "POST", body: body)
    }
}

/// What the person picked in another app, before it is sent.
public struct ShareContent: Sendable, Equatable {
    public var url: URL?
    public var title: String?
    public var text: String?
    /// Photos already shrunk (ImagePreparation) and PDFs, up to 4.
    public var files: [PreparedFile]

    public init(url: URL? = nil, title: String? = nil, text: String? = nil, files: [PreparedFile] = []) {
        self.url = url
        self.title = title
        self.text = text
        self.files = Array(files.prefix(AttachmentRules.maxPerMessage))
    }

    /// The domain for the preview: "booking.com".
    public var domain: String? {
        guard let host = url?.host() else { return nil }
        return host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
    }
}

/// Sends what was shared: each file first, then POST /share. A retry keeps the files that already
/// went up, so it does not upload them twice.
@MainActor
@Observable
public final class ShareSender {
    public enum State: Equatable, Sendable {
        case idle
        case sending
        /// 202: the reply comes later, as a notice.
        case sent
        /// No token, or 401: "Abra o Visão e entre de novo".
        case signedOut
        /// 422 or anything else: the server's message, and the option to try again.
        case failed(String)
    }

    public private(set) var state: State = .idle
    private let api: APIClient
    private var uploaded: [Int: String] = [:]

    public init(api: APIClient) {
        self.api = api
    }

    public static let sentText = "Enviado. A resposta chega como aviso."
    public static let signedOutText = "Abra o Visão e entre de novo"

    /// `locate` gets the comment and the text; with the switch off it never asks for a position.
    public func send(_ content: ShareContent, note: String, locate: ((String) async -> SentLocation?)? = nil) async {
        guard api.isAuthenticated else {
            state = .signedOut
            return
        }
        state = .sending
        do {
            var ids: [String] = []
            for (index, file) in content.files.enumerated() {
                if let id = uploaded[index] {
                    ids.append(id)
                    continue
                }
                let attachment = try await api.uploadAttachment(data: file.data, filename: file.filename, mimeType: file.mimeType)
                uploaded[index] = attachment.id
                ids.append(attachment.id)
            }
            // The comment is the question; a shared text can be long, so only its start counts.
            let asked = Nearby.asks(note) ? note : String((content.text ?? "").prefix(1000))
            let location = await locate?(asked)
            let body = ShareRequest(
                note: note, url: content.url?.absoluteString, title: content.title, text: content.text,
                attachmentIds: ids, location: location
            )
            _ = try await api.share(body)
            state = .sent
        } catch let error as APIError where error.isUnauthorized {
            state = .signedOut
        } catch {
            state = .failed((error as? LocalizedError)?.errorDescription ?? "Não deu para enviar")
        }
    }
}
