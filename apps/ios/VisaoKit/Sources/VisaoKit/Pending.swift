import Foundation
import Observation

/// An email to send or an event to schedule that it prepared, waiting for a yes
/// (docs/GOOGLE.md; apps/api/routes/google.py).
public struct GoogleAction: Codable, Sendable, Identifiable, Hashable {
    public struct Payload: Codable, Sendable, Hashable {
        public let to: String?
        public let subject: String?
        public let body: String?
        public let title: String?
        public let start: String?
        public let end: String?
        public let location: String?
        public let attendees: [String]?
    }

    public let id: String
    /// "send_email" or "create_event".
    public let kind: String
    /// Said by the server ("Email para fulano: assunto").
    public let summary: String
    public let payload: Payload
    public let status: String
    public let conversationId: String?
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, kind, summary, payload, status
        case conversationId = "conversation_id"
        case createdAt = "created_at"
    }
}

/// Work for the Mac (docs/BRACO.md). "proposed" ones were suggested by it and wait for a yes.
public struct ArmTask: Codable, Sendable, Identifiable, Hashable {
    public let id: String
    public let project: String
    public let prompt: String
    public let status: String
    public let requestedBy: String
    public let conversationId: String?
    public let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, project, prompt, status
        case requestedBy = "requested_by"
        case conversationId = "conversation_id"
        case createdAt = "created_at"
    }
}

/// How a decision was given; the server records it in the audit log.
public enum DecisionVia: String, Sendable {
    case toque
    case voz
}

extension APIClient {
    /// Only what still waits for a decision.
    public func googleActions() async throws -> [GoogleAction] {
        try await request("/google/actions")
    }

    public func decideGoogle(id: String, approve: Bool, via: DecisionVia = .toque) async throws {
        _ = try await raw(
            "/google/actions/\(id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? id)/\(approve ? "approve" : "reject")",
            method: "POST", query: [URLQueryItem(name: "via", value: via.rawValue)]
        )
    }

    public func armTasks() async throws -> [ArmTask] {
        try await request("/arm/tasks")
    }

    public func decideArm(id: String, approve: Bool, via: DecisionVia = .toque) async throws {
        _ = try await raw(
            "/arm/tasks/\(id.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? id)/\(approve ? "approve" : "reject")",
            method: "POST", query: [URLQueryItem(name: "via", value: via.rawValue)]
        )
    }
}

/// Something in a conversation waiting for one tap: Aprovar or Recusar. Nothing runs without it.
public struct PendingAsk: Identifiable, Hashable, Sendable {
    public enum Source: Hashable, Sendable {
        case google(GoogleAction)
        case arm(ArmTask)
    }

    public let source: Source

    public var id: String {
        switch source {
        case .google(let a): a.id
        case .arm(let t): t.id
        }
    }

    public var conversationId: String? {
        switch source {
        case .google(let a): a.conversationId
        case .arm(let t): t.conversationId
        }
    }

    /// "Email", "Agenda", "Mac · visao", as on the web.
    public var label: String {
        switch source {
        case .google(let a): a.kind == "send_email" ? "Email" : "Agenda"
        case .arm(let t): "Mac · \(t.project)"
        }
    }

    public var text: String {
        switch source {
        case .google(let a): a.summary
        case .arm(let t): t.prompt
        }
    }

    /// The email's body, so you approve exactly what will go out.
    public var detail: String? {
        guard case .google(let a) = source, a.kind == "send_email", let body = a.payload.body, !body.isEmpty else { return nil }
        return body
    }

    /// Approving this one posts a message in the conversation (what was sent or scheduled).
    var reportsInChat: Bool {
        if case .google = source { return true }
        return false
    }
}

/// Everything waiting for the owner, polled while the app is in front (as usePending on the web).
@MainActor
@Observable
public final class PendingStore {
    public private(set) var asks: [PendingAsk] = []
    /// Asks being decided right now: their buttons wait.
    public private(set) var deciding: Set<String> = []
    public var onError: ((Error) -> Void)?

    private let api: APIClient

    public init(api: APIClient) {
        self.api = api
    }

    public func asks(in conversationId: String?) -> [PendingAsk] {
        guard let conversationId else { return [] }
        return asks.filter { $0.conversationId == conversationId }
    }

    public func refresh() async {
        do {
            async let google = api.googleActions()
            async let arm = api.armTasks()
            let (actions, tasks) = try await (google, arm)
            asks = actions.map { PendingAsk(source: .google($0)) }
                + tasks.filter { $0.status == "proposed" }.map { PendingAsk(source: .arm($0)) }
        } catch {
            onError?(error)
        }
    }

    /// True only when the server accepted it: nothing is said to be done before that.
    @discardableResult
    public func decide(_ ask: PendingAsk, approve: Bool, via: DecisionVia = .toque) async -> Bool {
        guard !deciding.contains(ask.id) else { return false }
        deciding.insert(ask.id)
        defer { deciding.remove(ask.id) }
        do {
            switch ask.source {
            case .google(let action): try await api.decideGoogle(id: action.id, approve: approve, via: via)
            case .arm(let task): try await api.decideArm(id: task.id, approve: approve, via: via)
            }
            asks.removeAll { $0.id == ask.id }
            await refresh()
            return true
        } catch {
            onError?(error)
            await refresh()
            return false
        }
    }
}
