import Foundation

// The Caderno (mind and study), rating a reply, the account, the welcome questions, the Bancada
// and the Mac command: the web's remaining features (apps/web/src/api.ts).

private extension KeyedDecodingContainer {
    func value<T: Decodable>(_ key: Key, _ fallback: T) -> T {
        (try? decodeIfPresent(T.self, forKey: key)) ?? fallback
    }
}

/// What it thinks, cares about and how it describes itself (GET /mind, docs/MIND.md).
public struct Mind: Decodable, Sendable {
    public struct Tendency: Decodable, Sendable, Hashable {
        public let name: String
        public let value: Double
        public let level: String
        public let why: String
    }

    public struct Question: Decodable, Sendable, Hashable {
        public let question: String
        /// "waiting", "asked", "answered".
        public let status: String
        public let answer: String
    }

    public struct Interest: Decodable, Sendable, Hashable {
        public let topic: String
        public let why: String
    }

    public struct Thought: Decodable, Sendable, Hashable {
        public let content: String
        public let createdAt: Date
        public let askOwner: String
        public let wantedToSay: String
        public let delivery: String?

        enum CodingKeys: String, CodingKey {
            case content, delivery
            case createdAt = "created_at"
            case askOwner = "ask_owner"
            case wantedToSay = "wanted_to_say"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            content = c.value(.content, "")
            createdAt = try c.decode(Date.self, forKey: .createdAt)
            askOwner = c.value(.askOwner, "")
            wantedToSay = c.value(.wantedToSay, "")
            delivery = c.value(.delivery, nil as String?)
        }
    }

    public struct SelfVersion: Decodable, Sendable, Hashable {
        public let version: Int
        public let content: String
        public let reason: String
    }

    /// A permanent note (what it knows about you, what it learned from your corrections).
    public struct Note: Decodable, Sendable, Hashable {
        public let content: String
        public let reason: String
    }

    public struct Temperament: Decodable, Sendable {
        public let states: [Tendency]
        public let traits: [Tendency]
        public let avoids: [Tendency]
    }

    public let enabled: Bool
    public let temperament: Temperament
    public let questions: [Question]
    public let selfText: String
    public let interests: [Interest]
    public let thoughts: [Thought]
    public let selfHistory: [SelfVersion]
    public let profile: Note
    public let rules: Note

    enum CodingKeys: String, CodingKey {
        case enabled, temperament, questions, interests, thoughts, profile, rules
        case selfText = "self_text"
        case selfHistory = "self_history"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = c.value(.enabled, false)
        temperament = c.value(.temperament, Temperament(states: [], traits: [], avoids: []))
        questions = c.value(.questions, [])
        selfText = c.value(.selfText, "")
        interests = c.value(.interests, [])
        thoughts = c.value(.thoughts, [])
        selfHistory = c.value(.selfHistory, [])
        profile = c.value(.profile, Note(content: "", reason: ""))
        rules = c.value(.rules, Note(content: "", reason: ""))
    }

    /// "mandou", "guardou: horário silencioso"…
    public static func deliveryLabel(_ delivery: String?) -> String {
        let labels = [
            "sent": "mandou", "quiet_hours": "guardou: horário silencioso",
            "owner_active": "guardou: você estava falando", "waiting_for_reply": "guardou: esperando você responder",
            "daily_limit": "guardou: limite do dia", "paused": "guardou: autonomia pausada",
        ]
        return delivery.flatMap { labels[$0] ?? $0 } ?? ""
    }

    public static func questionLabel(_ status: String) -> String {
        ["waiting": "quero perguntar", "asked": "perguntei", "answered": "respondida"][status] ?? status
    }
}

extension Mind.Temperament {
    init(states: [Mind.Tendency], traits: [Mind.Tendency], avoids: [Mind.Tendency], _: Void = ()) {
        self.states = states
        self.traits = traits
        self.avoids = avoids
    }
}

extension Mind.Note {
    init(content: String, reason: String, _: Void = ()) {
        self.content = content
        self.reason = reason
    }
}

/// The study notebook (GET /study, docs/STUDY.md).
public struct StudyNotebook: Decodable, Sendable {
    public struct Finding: Decodable, Sendable, Hashable {
        public let claim: String
        public let sources: [Int]
    }

    public struct SourceRef: Decodable, Sendable, Hashable {
        public let id: Int
        public let url: String
        public let title: String
    }

    public struct Evidence: Decodable, Sendable {
        public let findings: [Finding]
        public let sources: [SourceRef]
        public let uncertain: String
        public let nextQuestion: String

        enum CodingKeys: String, CodingKey {
            case findings, sources, uncertain
            case nextQuestion = "next_question"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            findings = c.value(.findings, [])
            sources = c.value(.sources, [])
            uncertain = c.value(.uncertain, "")
            nextQuestion = c.value(.nextQuestion, "")
        }

        init() {
            findings = []
            sources = []
            uncertain = ""
            nextQuestion = ""
        }
    }

    public struct Entry: Decodable, Sendable, Identifiable {
        public let id: String
        public let status: String
        public let question: String
        public let rationale: String
        public let outcomeReason: String
        public let createdAt: Date
        public let evidence: Evidence

        enum CodingKeys: String, CodingKey {
            case id, status, question, rationale, evidence
            case outcomeReason = "outcome_reason"
            case createdAt = "created_at"
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id)
            status = c.value(.status, "")
            question = c.value(.question, "")
            rationale = c.value(.rationale, "")
            outcomeReason = c.value(.outcomeReason, "")
            createdAt = try c.decode(Date.self, forKey: .createdAt)
            evidence = c.value(.evidence, Evidence())
        }
    }

    public let enabled: Bool
    public let paused: Bool
    public let nextEligibleAt: Date?
    public let entries: [Entry]

    enum CodingKeys: String, CodingKey {
        case enabled, paused, entries
        case nextEligibleAt = "next_eligible_at"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = c.value(.enabled, false)
        paused = c.value(.paused, false)
        nextEligibleAt = c.value(.nextEligibleAt, nil as Date?)
        entries = c.value(.entries, [])
    }

    public static func statusLabel(_ status: String) -> String {
        [
            "PLANNING": "Escolhendo uma pergunta", "READING": "Lendo fontes", "READY": "Achados registrados",
            "INCONCLUSIVE": "Ainda sem resposta suficiente", "SKIPPED": "Rodada adiada", "FAILED": "Rodada interrompida",
        ][status] ?? status
    }

    /// Why a round ended without findings; nil when it recorded evidence.
    public static func reasonText(_ reason: String) -> String? {
        if reason.isEmpty || reason == "evidence_recorded" || reason == "sources_do_not_answer" { return nil }
        return [
            "no_useful_question": "Não identifiquei uma pergunta útil nesta rodada.",
            "not_public_topic": "O tema não passou pelos critérios de pesquisa pública.",
            "no_sources": "A busca não retornou trechos aproveitáveis.",
            "repeated_query": "A retomada não propôs uma busca diferente das anteriores.",
            "repeated_question": "A pergunta já estava no caderno; evitei repetir a investigação.",
            "invalid_seed_reference": "Não consegui ligar o tema às evidências disponíveis.",
            "cycle_budget": "O limite desta rodada foi atingido.",
            "permission_revoked": "O estudo foi desligado ou a autonomia foi pausada.",
            "unsafe_review": "A revisão não passou pelos critérios de conteúdo público.",
            "invalid_model_output": "A resposta do modelo não pôde ser validada.",
        ][reason] ?? "Houve uma falha na consulta ao provedor. Uma nova oportunidade ocorrerá em outro ciclo."
    }
}

/// The Bancada: what it really did in a conversation, its pages and the sites it read live.
public struct Bench: Decodable, Sendable {
    public struct Deed: Decodable, Sendable, Hashable {
        public let at: Date
        public let text: String
    }

    public struct Visit: Decodable, Sendable, Hashable {
        public let title: String
        public let url: String
        public let at: Date
    }

    public let deeds: [Deed]
    public let pages: [Artifact]
    public let visits: [Visit]

    enum CodingKeys: String, CodingKey { case deeds, pages, visits }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        deeds = c.value(.deeds, [])
        pages = c.value(.pages, [])
        visits = c.value(.visits, [])
    }
}

public struct OnboardingStatus: Decodable, Sendable {
    public struct Room: Decodable, Sendable {
        public let profile: Int
        public let rules: Int
    }

    public let completed: Bool
    public let mindEnabled: Bool
    /// Characters still free in each permanent note.
    public let room: Room

    enum CodingKeys: String, CodingKey {
        case completed, room
        case mindEnabled = "mind_enabled"
    }
}

public struct OnboardingAnswers: Encodable, Sendable, Equatable {
    public var who = ""
    public var work = ""
    public var goal = ""
    public var tone = ""

    public init() {}

    public var wroteSomething: Bool { [who, work, goal, tone].contains { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } }
}

public struct OnboardingResult: Decodable, Sendable {
    public let saved: [String]
    /// The person wrote something and it was not kept (memory was off).
    public let discarded: Bool

    public var closingNotice: String? {
        if !saved.isEmpty { return "Suas respostas foram para as anotações dele. No Caderno você vê, desfaz ou apaga." }
        if discarded { return "Nada do que você escreveu foi guardado: a memória estava desligada." }
        return nil
    }
}

/// A Mac just paired: the token shows only now.
public struct PairedDevice: Decodable, Sendable {
    public let id: String
    public let name: String
    public let token: String
}

/// `/mac <projeto> <pedido>` in the chat: work for the arm on the owner's Mac (docs/BRACO.md).
public enum MacCommand: Equatable, Sendable {
    case ask(project: String, prompt: String)
    case usage

    public static let usageText = "Use assim: /mac projeto o que fazer (ex.: /mac visao rode os testes)."

    public static func parse(_ text: String) -> MacCommand? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.lowercased() == "/mac" || trimmed.lowercased().hasPrefix("/mac ") || trimmed.lowercased().hasPrefix("/mac\n") else { return nil }
        let rest = trimmed.dropFirst(4).trimmingCharacters(in: .whitespacesAndNewlines)
        guard let split = rest.firstIndex(where: { $0.isWhitespace }) else { return .usage }
        let project = String(rest[..<split])
        let prompt = rest[split...].trimmingCharacters(in: .whitespacesAndNewlines)
        return prompt.isEmpty ? .usage : .ask(project: project, prompt: prompt)
    }
}

extension APIClient {
    private func seg(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .alphanumerics.union(CharacterSet(charactersIn: "-"))) ?? value
    }

    // MARK: Caderno

    public func mind() async throws -> Mind { try await request("/mind") }

    /// kind: "profile" (what it knows about you) or "rules" (what it learned from corrections).
    public func undoNote(_ kind: String) async throws { _ = try await raw("/mind/notes/\(seg(kind))/undo", method: "POST") }

    public func eraseNote(_ kind: String) async throws { _ = try await raw("/mind/notes/\(seg(kind))", method: "DELETE") }

    /// Back to a previous self-description (nil: the original one).
    public func revertSelf(to version: Int?) async throws {
        let body = version.map { #"{"version":\#($0)}"# } ?? #"{"version":null}"#
        _ = try await raw("/mind/self/revert", method: "POST", body: Data(body.utf8), contentType: "application/json")
    }

    public func study() async throws -> StudyNotebook { try await request("/study") }

    public func setStudy(enabled: Bool) async throws -> Bool {
        let result: [String: Bool] = try await json("/study/settings", method: "PUT", body: ["enabled": enabled])
        return result["enabled"] ?? enabled
    }

    // MARK: Rating a reply

    /// Returns whether its way of answering changed (a new behavior version).
    public func feedback(messageId: String, positive: Bool, tags: [String]) async throws -> Bool {
        struct Body: Encodable { let rating: Int; let tags: [String]; let comment: String }
        struct Out: Decodable {
            let stateChanged: Bool
            enum CodingKeys: String, CodingKey { case stateChanged = "state_changed" }
        }
        let out: Out = try await json("/messages/\(seg(messageId))/feedback", method: "POST", body: Body(rating: positive ? 1 : -1, tags: Array(tags.prefix(6)), comment: ""))
        return out.stateChanged
    }

    // MARK: Account

    /// Every other device is signed out; this one keeps going with the new token.
    public func changePassword(current: String, new: String) async throws {
        struct Body: Encodable {
            let current: String, new: String
            enum CodingKeys: String, CodingKey { case current = "current_password", new = "new_password" }
        }
        let token: TokenResponse = try await json("/auth/password", method: "POST", body: Body(current: current, new: new))
        replaceToken(token.accessToken)
    }

    public func changeEmail(current: String, newEmail: String) async throws {
        struct Body: Encodable {
            let current: String, email: String
            enum CodingKeys: String, CodingKey { case current = "current_password", email = "new_email" }
        }
        let token: TokenResponse = try await json("/auth/email", method: "POST", body: Body(current: current, email: newEmail))
        replaceToken(token.accessToken)
    }

    // MARK: Welcome

    public func onboarding() async throws -> OnboardingStatus { try await request("/onboarding") }

    public func finishOnboarding(_ answers: OnboardingAnswers) async throws -> OnboardingResult {
        try await json("/onboarding", method: "POST", body: ["answers": answers])
    }

    public func skipOnboarding() async throws -> OnboardingResult {
        try await json("/onboarding", method: "POST", body: ["skip": true])
    }

    public func restartOnboarding() async throws { _ = try await raw("/onboarding", method: "DELETE") }

    // MARK: Mac, Google, Bancada

    public func pairArm(name: String) async throws -> PairedDevice {
        try await json("/arm/devices", method: "POST", body: ["name": name])
    }

    public func unpairArm(id deviceId: String) async throws { _ = try await raw("/arm/devices/\(seg(deviceId))", method: "DELETE") }

    public func askArm(project: String, prompt: String, conversationId: String?) async throws -> ArmTask {
        struct Body: Encodable {
            let project: String, prompt: String, conversationId: String?
            enum CodingKeys: String, CodingKey { case project, prompt, conversationId = "conversation_id" }
        }
        return try await json("/arm/tasks", method: "POST", body: Body(project: project, prompt: prompt, conversationId: conversationId))
    }

    public func disconnectGoogle() async throws { _ = try await raw("/google", method: "DELETE") }

    public func bench(conversationId: String) async throws -> Bench {
        try await request("/conversations/\(seg(conversationId))/bench")
    }
}
