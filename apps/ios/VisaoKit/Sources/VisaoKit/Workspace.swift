import Foundation

// The rest of the web's places: Projetos, Ajustes, the Mac, goals and notices
// (apps/web/src/api.ts; routes in apps/api/routes).

/// A subject with its own chat, notes, panels, pages and files (Projetos, ADR-0021).
public struct Project: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let name: String
    public let createdAt: Date
    public let conversations: Int
    public let pages: Int
    public let files: Int
    /// One fact per line, each starting with "- " (written by him, edited by you).
    public let notes: String
    public let notesUpdatedAt: Date?
    /// How many panels are in it.
    public let panels: Int

    enum CodingKeys: String, CodingKey {
        case id, name, conversations, pages, files, notes, panels
        case createdAt = "created_at"
        case notesUpdatedAt = "notes_updated_at"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        conversations = try c.decodeIfPresent(Int.self, forKey: .conversations) ?? 0
        pages = try c.decodeIfPresent(Int.self, forKey: .pages) ?? 0
        files = try c.decodeIfPresent(Int.self, forKey: .files) ?? 0
        notes = try c.decodeIfPresent(String.self, forKey: .notes) ?? ""
        notesUpdatedAt = try c.decodeIfPresent(Date.self, forKey: .notesUpdatedAt)
        panels = try c.decodeIfPresent(Int.self, forKey: .panels) ?? 0
    }

    /// "4 anotações · 1 painel · 2 páginas" (projectSummary in ProjectsView.tsx).
    public var summary: String {
        ProjectText.summary(notes: notes, panels: panels, pages: pages, files: files)
    }

    /// "3 conversas · 1 página", as the web's project card.
    public var countsLabel: String {
        var parts = ["\(conversations) \(conversations == 1 ? "conversa" : "conversas")"]
        if pages > 0 { parts.append("\(pages) \(pages == 1 ? "página" : "páginas")") }
        if files > 0 { parts.append("\(files) \(files == 1 ? "arquivo" : "arquivos")") }
        return parts.joined(separator: " · ")
    }
}

/// What the project card says, the same words as the web.
public enum ProjectText {
    public static func summary(notes: String, panels: Int, pages: Int, files: Int) -> String {
        let count = noteLines(notes).count
        let parts = [
            count > 0 ? "\(count) \(count == 1 ? "anotação" : "anotações")" : nil,
            panels > 0 ? "\(panels) \(panels == 1 ? "painel" : "painéis")" : nil,
            pages > 0 ? "\(pages) \(pages == 1 ? "página" : "páginas")" : nil,
            files > 0 ? "\(files) \(files == 1 ? "arquivo" : "arquivos")" : nil,
        ].compactMap { $0 }
        return parts.isEmpty ? "só o chat, por enquanto" : parts.joined(separator: " · ")
    }

    /// The notes as a list: one per non-empty line, without the leading "- ".
    public static func noteLines(_ notes: String) -> [String] {
        notes.split(separator: "\n", omittingEmptySubsequences: true)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .map { line in
                guard line.hasPrefix("-") else { return line }
                return line.dropFirst().trimmingCharacters(in: .whitespaces)
            }
    }
}

/// The body of PATCH /projects/{id}: only what changed goes.
public struct ProjectChange: Encodable, Sendable, Equatable {
    public var name: String?
    public var notes: String?

    public init(name: String? = nil, notes: String? = nil) {
        self.name = name
        self.notes = notes
    }

    enum CodingKeys: String, CodingKey { case name, notes }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(name, forKey: .name)
        try c.encodeIfPresent(notes, forKey: .notes)
    }
}

public struct ProjectDetail: Codable, Sendable, Identifiable {
    /// A panel in the project: enough to know it is there.
    public struct PanelRef: Codable, Sendable, Identifiable, Hashable {
        public let id: String
        public let title: String
        public let status: String
    }

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
    public let notes: String
    public let notesUpdatedAt: Date?
    public let panels: Int
    public let panelList: [PanelRef]

    enum CodingKeys: String, CodingKey {
        case id, name, notes, panels
        case notesUpdatedAt = "notes_updated_at"
        case panelList = "panel_list"
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
        notes = try c.decodeIfPresent(String.self, forKey: .notes) ?? ""
        notesUpdatedAt = try c.decodeIfPresent(Date.self, forKey: .notesUpdatedAt)
        panelList = try c.decodeIfPresent([PanelRef].self, forKey: .panelList) ?? []
        panels = try c.decodeIfPresent(Int.self, forKey: .panels) ?? panelList.count
    }

    public var summary: String {
        ProjectText.summary(notes: notes, panels: panels, pages: pageList.count, files: fileList.count)
    }

    public var noteLines: [String] { ProjectText.noteLines(notes) }
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
    /// The morning summary when the quiet hours end (docs/RESUMO_DA_MANHA.md); on by default.
    public var morningBriefing: Bool = true
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
        try await updateProject(id: projectId, ProjectChange(name: name))
    }

    /// "Editar anotações" and Renomear: only the field that changed goes.
    public func updateProject(id projectId: String, _ change: ProjectChange) async throws -> Project {
        try await json("/projects/\(id(projectId))", method: "PATCH", body: change)
    }

    /// The project's own chat, created the first time with an opening message (origin "project").
    public func projectConversation(projectId: String) async throws -> Conversation {
        try await request("/conversations/project/\(id(projectId))")
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
        return ServerSettings(
            memory: m["enabled"] ?? false, paused: a["paused"] ?? false, autoResearch: p["auto_research"] ?? false,
            morningBriefing: p["morning_briefing"] ?? true
        )
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

    /// Only this field goes: the PUT changes only what comes, so auto_research stays as it is.
    public func setMorningBriefing(_ enabled: Bool) async throws -> Bool {
        let result: [String: Bool] = try await json("/autonomy/permissions", method: "PUT", body: ["morning_briefing": enabled])
        return result["morning_briefing"] ?? enabled
    }

    /// "Mandar agora": a summary now, even with the daily one off. False: autonomy is paused.
    public func briefingNow() async throws -> Bool {
        let result: [String: Bool] = try await request("/autonomy/briefing", method: "POST")
        return result["queued"] ?? false
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

/// Which model the Visão thinks with (docs/MODELO_LOCAL.md): the cloud, the local model on the
/// Mac first, or the cloud with the Mac as a reserve.
public enum BrainMode: String, Codable, Sendable, CaseIterable, Identifiable {
    case nuvem, local, auto
    public var id: String { rawValue }
    public var label: String {
        switch self {
        case .nuvem: "Nuvem"
        case .local: "Local"
        case .auto: "Automático"
        }
    }
}

public struct BrainState: Codable, Sendable, Equatable {
    public let mode: BrainMode
    /// The model a Mac offers right now ("qwen3:4b"); nil: none online.
    public let localModel: String?
    public let macOnline: Bool

    public init(mode: BrainMode, localModel: String?, macOnline: Bool) {
        self.mode = mode
        self.localModel = localModel
        self.macOnline = macOnline
    }

    enum CodingKeys: String, CodingKey {
        case mode
        case localModel = "local_model"
        case macOnline = "mac_online"
    }

    /// One sentence on what the mode does with the Mac as it is now (BrainSettings.tsx).
    public var note: String {
        let mac: String
        if let localModel {
            mac = "O Mac oferece o \(localModel)."
        } else if macOnline {
            mac = "O Mac está ligado, mas sem modelo local configurado."
        } else {
            mac = "O Mac não está oferecendo modelo local agora."
        }
        switch mode {
        case .local:
            return "\(mac) Responde com o modelo do Mac e volta para a nuvem se ele dormir. O trabalho de fundo fica pausado."
        case .auto:
            return "\(mac) Usa a nuvem e passa para o modelo do Mac se ela falhar."
        case .nuvem:
            return "\(mac) Usa só a nuvem. Você também pode pedir no chat: “usa o modelo local”."
        }
    }
}

extension APIClient {
    public func brain() async throws -> BrainState { try await request("/arm/brain") }

    public func setBrain(_ mode: BrainMode) async throws -> BrainState {
        try await json("/arm/brain", method: "PUT", body: ["mode": mode.rawValue])
    }
}
