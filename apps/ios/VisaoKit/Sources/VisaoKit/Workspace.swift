import Foundation

// The rest of the web's places: Projetos, Ajustes, the Mac, goals and notices
// (apps/web/src/api.ts; routes in apps/api/routes).

/// A subject with its conversations, pages and files (Projetos).
public struct Project: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let createdAt: Date
    public let conversations: Int
    public let pages: Int
    public let files: Int

    enum CodingKeys: String, CodingKey {
        case id, name, conversations, pages, files
        case createdAt = "created_at"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        conversations = try c.decodeIfPresent(Int.self, forKey: .conversations) ?? 0
        pages = try c.decodeIfPresent(Int.self, forKey: .pages) ?? 0
        files = try c.decodeIfPresent(Int.self, forKey: .files) ?? 0
    }

    /// "3 conversas · 1 página", as the web's project card.
    public var countsLabel: String {
        var parts = ["\(conversations) \(conversations == 1 ? "conversa" : "conversas")"]
        if pages > 0 { parts.append("\(pages) \(pages == 1 ? "página" : "páginas")") }
        if files > 0 { parts.append("\(files) \(files == 1 ? "arquivo" : "arquivos")") }
        return parts.joined(separator: " · ")
    }
}

public struct ProjectDetail: Codable, Sendable, Identifiable {
    public struct ConversationRow: Codable, Sendable, Identifiable, Hashable {
        public let id: String
        public let createdAt: Date
        public let title: String

        enum CodingKeys: String, CodingKey {
            case id, title
            case createdAt = "created_at"
        }
    }

    public let id: String
    public let name: String
    public let conversationList: [ConversationRow]
    public let pageList: [Artifact]
    public let fileList: [Attachment]

    enum CodingKeys: String, CodingKey {
        case id, name
        case conversationList = "conversation_list"
        case pageList = "page_list"
        case fileList = "file_list"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        conversationList = try c.decodeIfPresent([ConversationRow].self, forKey: .conversationList) ?? []
        pageList = try c.decodeIfPresent([Artifact].self, forKey: .pageList) ?? []
        fileList = try c.decodeIfPresent([Attachment].self, forKey: .fileList) ?? []
    }
}

/// A Mac paired to run work (docs/BRACO.md).
public struct ArmDevice: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let projects: [String]
    public let version: String
    public let online: Bool
    public let lastSeenAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, name, projects, version, online
        case lastSeenAt = "last_seen_at"
    }
}

/// Something it wants to pursue on its own, waiting for approval (docs/AUTONOMY.md).
public struct Goal: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let title: String
    public let rationale: String
    public let requiredPermissions: [String]
    public let status: String

    enum CodingKeys: String, CodingKey {
        case id, title, rationale, status
        case requiredPermissions = "required_permissions"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        rationale = try c.decodeIfPresent(String.self, forKey: .rationale) ?? ""
        requiredPermissions = try c.decodeIfPresent([String].self, forKey: .requiredPermissions) ?? []
        status = try c.decodeIfPresent(String.self, forKey: .status) ?? ""
    }
}

/// A notice. "initiative" is also a message in the chat; the rest only lives in Pendências.
public struct AppNotice: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let kind: String
    public let title: String
    public let body: String
    public let createdAt: Date
    public let readAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, kind, title, body
        case createdAt = "created_at"
        case readAt = "read_at"
    }
}

/// The switches the server keeps (Ajustes).
public struct ServerSettings: Equatable, Sendable {
    public var memory: Bool
    /// "Agir por conta própria" is the opposite of paused.
    public var paused: Bool
    public var autoResearch: Bool
}

extension APIClient {
    func json<T: Decodable>(_ path: String, method: String, body: some Encodable) async throws -> T {
        try await request(path, method: method, body: try JSONEncoder().encode(body), contentType: "application/json")
    }

    private func id(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-"))) ?? value
    }

    // MARK: Projects

    public func projects() async throws -> [Project] { try await request("/projects") }

    public func project(id projectId: String) async throws -> ProjectDetail {
        try await request("/projects/\(id(projectId))")
    }

    public func createProject(name: String) async throws -> Project {
        try await json("/projects", method: "POST", body: ["name": name])
    }

    public func renameProject(id projectId: String, name: String) async throws -> Project {
        try await json("/projects/\(id(projectId))", method: "PATCH", body: ["name": name])
    }

    /// Its conversations, pages and files stay; they only leave the project.
    public func deleteProject(id projectId: String) async throws {
        _ = try await raw("/projects/\(id(projectId))", method: "DELETE")
    }

    public func moveConversation(_ conversationId: String, toProject projectId: String?) async throws -> Conversation {
        struct Body: Encodable {
            let projectId: String?
            enum CodingKeys: String, CodingKey { case projectId = "project_id" }
            func encode(to encoder: Encoder) throws {
                var c = encoder.container(keyedBy: CodingKeys.self)
                try c.encode(projectId, forKey: .projectId)
            }
        }
        return try await json("/conversations/\(id(conversationId))/project", method: "PUT", body: Body(projectId: projectId))
    }

    // MARK: Settings

    public func serverSettings() async throws -> ServerSettings {
        async let memory: [String: Bool] = request("/memory/settings")
        async let autonomy: [String: Bool] = request("/system/autonomy")
        async let permissions: [String: Bool] = request("/autonomy/permissions")
        let (m, a, p) = try await (memory, autonomy, permissions)
        return ServerSettings(memory: m["enabled"] ?? false, paused: a["paused"] ?? false, autoResearch: p["auto_research"] ?? false)
    }

    public func setMemory(enabled: Bool) async throws -> Bool {
        let result: [String: Bool] = try await json("/memory/settings", method: "PUT", body: ["enabled": enabled])
        return result["enabled"] ?? enabled
    }

    public func setAutonomy(paused: Bool) async throws -> Bool {
        struct Body: Encodable { let paused: Bool; let reason: String }
        let result: [String: Bool] = try await json("/system/autonomy", method: "PUT", body: Body(paused: paused, reason: paused ? "pausa pelo app do iPhone" : "retomada"))
        return result["paused"] ?? paused
    }

    public func setAutoResearch(_ enabled: Bool) async throws -> Bool {
        let result: [String: Bool] = try await json("/autonomy/permissions", method: "PUT", body: ["auto_research": enabled])
        return result["auto_research"] ?? enabled
    }

    // MARK: Mac, goals, notices

    public func armDevices() async throws -> [ArmDevice] { try await request("/arm/devices") }

    public func approvals() async throws -> [Goal] { try await request("/approvals") }

    public func decideGoal(id goalId: String, approve: Bool) async throws {
        _ = try await raw(
            "/goals/\(id(goalId))/\(approve ? "approve" : "reject")", method: "POST",
            body: Data(#"{"reason":""}"#.utf8), contentType: "application/json"
        )
    }

    public func notices() async throws -> [AppNotice] { try await request("/notifications") }

    public func markRead(noticeId: String) async throws {
        _ = try await raw("/notifications/\(id(noticeId))/read", method: "POST")
    }

    /// Answering a notice opens (or continues) a conversation about it; returns which.
    public func reply(toNotice noticeId: String, conversationId: String?) async throws -> String {
        struct Body: Encodable {
            let conversationId: String?
            enum CodingKeys: String, CodingKey { case conversationId = "conversation_id" }
            func encode(to encoder: Encoder) throws {
                var c = encoder.container(keyedBy: CodingKeys.self)
                try c.encode(conversationId, forKey: .conversationId)
            }
        }
        let result: [String: String] = try await json("/notifications/\(id(noticeId))/reply", method: "POST", body: Body(conversationId: conversationId))
        guard let id = result["conversation_id"] else { throw APIError(status: 0, message: "Resposta inesperada do servidor") }
        return id
    }
}

/// The Google connection (docs/GOOGLE.md). Connecting happens on the site, where the sign-in is.
public struct GoogleState: Codable, Sendable, Equatable {
    public let connected: Bool
    public let email: String
    /// Reading the inbox and agenda between conversations, to bring up what matters.
    public let background: Bool
    public let problem: String

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        connected = try c.decode(Bool.self, forKey: .connected)
        email = try c.decodeIfPresent(String.self, forKey: .email) ?? ""
        background = try c.decodeIfPresent(Bool.self, forKey: .background) ?? false
        problem = try c.decodeIfPresent(String.self, forKey: .problem) ?? ""
    }

    enum CodingKeys: String, CodingKey { case connected, email, background, problem }
}

extension APIClient {
    public func google() async throws -> GoogleState { try await request("/google") }

    public func setGoogleBackground(_ enabled: Bool) async throws -> GoogleState {
        try await json("/google/background", method: "PUT", body: ["enabled": enabled])
    }
}
