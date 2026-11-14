import Foundation

// Tipos da API, conferidos com /openapi.json e apps/web/src/api.ts. Ids ficam como String: o
// servidor manda UUIDs minúsculos e devolve as mesmas strings nas rotas.

public enum Role: String, Codable, Sendable {
    case user
    case assistant
}

public struct TokenResponse: Codable, Sendable {
    public let accessToken: String
    public let tokenType: String?
    public let expiresIn: Int?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresIn = "expires_in"
    }
}

public struct UserInfo: Codable, Sendable, Equatable {
    public let id: String
    public let email: String
}

public struct SystemStatus: Codable, Sendable {
    public struct Identity: Codable, Sendable {
        public let internalId: String
        public let chosenName: String?

        enum CodingKeys: String, CodingKey {
            case internalId = "internal_id"
            case chosenName = "chosen_name"
        }
    }

    public let genesisCompleted: Bool
    public let identity: Identity?

    enum CodingKeys: String, CodingKey {
        case genesisCompleted = "genesis_completed"
        case identity
    }
}

public struct Conversation: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let createdAt: Date
    public let memoryStatus: String?
    public let projectId: String?

    public init(id: String, createdAt: Date, memoryStatus: String? = nil, projectId: String? = nil) {
        self.id = id
        self.createdAt = createdAt
        self.memoryStatus = memoryStatus
        self.projectId = projectId
    }

    /// The server could not prepare memory for it: you can talk, it may forget details.
    public var memoryUnavailable: Bool {
        memoryStatus == "failed" || memoryStatus == "unavailable"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case createdAt = "created_at"
        case memoryStatus = "memory_status"
        case projectId = "project_id"
    }
}

public struct Source: Codable, Sendable, Hashable {
    public let title: String
    public let url: String
    public let source: String
}

/// A photo or file sent with a message (docs/ANEXOS.md).
public struct Attachment: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let kind: String
    public let filename: String
    public let mediaType: String
    public let sizeBytes: Int
    public let readable: Bool?

    public var isImage: Bool { kind == "image" }

    enum CodingKeys: String, CodingKey {
        case id, kind, filename, readable
        case mediaType = "media_type"
        case sizeBytes = "size_bytes"
    }
}

/// A page it writes (docs/ARTEFATOS.md); "pending" while it is being written.
public struct Artifact: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let status: String
    /// Relative to the API ("/p/<token>").
    public let path: String?
    public let error: String?
    public let conversationId: String?
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, title, status, path, error
        case conversationId = "conversation_id"
        case createdAt = "created_at"
    }
}

/// The earlier message a message answers (Responder).
public struct Quoted: Codable, Sendable, Hashable {
    public let id: String
    public let role: Role
    public let excerpt: String

    public init(id: String, role: Role, excerpt: String) {
        self.id = id
        self.role = role
        self.excerpt = excerpt
    }
}

public struct Message: Codable, Sendable, Identifiable, Hashable {
    /// Shown before the server answered, only on this device.
    public enum LocalState: Sendable, Hashable {
        case sending
        /// Written while a reply was in flight: goes with the next turn.
        case queued
        case failed
        case stopped
    }

    public let id: String
    public let role: Role
    public let content: String
    public let createdAt: Date
    /// "turn", "initiative" (it spoke first), "arm" (the Mac), "google".
    public let origin: String
    public let attachments: [Attachment]
    public var artifact: Artifact?
    public let replyTo: Quoted?
    /// Only known for replies received in this session (the transcript does not keep them).
    public var sources: [Source]
    public var local: LocalState?

    public init(
        id: String, role: Role, content: String, createdAt: Date, origin: String = "turn",
        attachments: [Attachment] = [], artifact: Artifact? = nil, replyTo: Quoted? = nil,
        sources: [Source] = [], local: LocalState? = nil
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.origin = origin
        self.attachments = attachments
        self.artifact = artifact
        self.replyTo = replyTo
        self.sources = sources
        self.local = local
    }

    enum CodingKeys: String, CodingKey {
        case id, role, content, origin, attachments, artifact
        case createdAt = "created_at"
        case replyTo = "reply_to"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        role = try c.decode(Role.self, forKey: .role)
        content = try c.decode(String.self, forKey: .content)
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        origin = try c.decodeIfPresent(String.self, forKey: .origin) ?? "turn"
        attachments = try c.decodeIfPresent([Attachment].self, forKey: .attachments) ?? []
        artifact = try c.decodeIfPresent(Artifact.self, forKey: .artifact)
        replyTo = try c.decodeIfPresent(Quoted.self, forKey: .replyTo)
        sources = []
        local = nil
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(role, forKey: .role)
        try c.encode(content, forKey: .content)
        try c.encode(createdAt, forKey: .createdAt)
        try c.encode(origin, forKey: .origin)
        try c.encode(attachments, forKey: .attachments)
        try c.encodeIfPresent(artifact, forKey: .artifact)
        try c.encodeIfPresent(replyTo, forKey: .replyTo)
    }

    /// How a reply quotes this message: one line, as the web does (160 characters).
    public var quoted: Quoted {
        Quoted(id: id, role: role, excerpt: Message.oneLine(content, limit: 160))
    }

    public static func oneLine(_ text: String, limit: Int) -> String {
        let flat = text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return String(flat.prefix(limit))
    }
}

public struct Usage: Codable, Sendable {
    public let provider: String
    public let model: String
    public let latencyMs: Int?
    public let costUsd: String

    enum CodingKeys: String, CodingKey {
        case provider, model
        case latencyMs = "latency_ms"
        case costUsd = "cost_usd"
    }
}

public struct Turn: Codable, Sendable {
    public let userMessage: Message
    public let assistantMessage: Message
    public let usage: Usage
    public let sources: [Source]

    enum CodingKeys: String, CodingKey {
        case usage, sources
        case userMessage = "user_message"
        case assistantMessage = "assistant_message"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        userMessage = try c.decode(Message.self, forKey: .userMessage)
        assistantMessage = try c.decode(Message.self, forKey: .assistantMessage)
        usage = try c.decode(Usage.self, forKey: .usage)
        sources = try c.decodeIfPresent([Source].self, forKey: .sources) ?? []
    }
}

/// One thing the turn in flight is doing, said as it starts ("Pesquisando “voos”").
public struct ProgressStep: Codable, Sendable, Hashable {
    public let label: String
    public let detail: String?

    public init(label: String, detail: String? = nil) {
        self.label = label
        self.detail = detail
    }
}

public struct TurnProgress: Codable, Sendable {
    public let active: Bool
    public let elapsedMs: Int
    public let steps: [ProgressStep]
    /// In a voice call, the reply written so far (spoken sentence by sentence while it is written).
    public let draft: String?

    enum CodingKeys: String, CodingKey {
        case active, steps, draft
        case elapsedMs = "elapsed_ms"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        active = try c.decode(Bool.self, forKey: .active)
        elapsedMs = try c.decodeIfPresent(Int.self, forKey: .elapsedMs) ?? 0
        steps = try c.decodeIfPresent([ProgressStep].self, forKey: .steps) ?? []
        draft = try c.decodeIfPresent(String.self, forKey: .draft)
    }
}
