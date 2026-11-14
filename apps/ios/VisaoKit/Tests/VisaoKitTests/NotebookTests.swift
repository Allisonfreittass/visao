import XCTest
@testable import VisaoKit

@MainActor
final class NotebookTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    private func api(_ transport: StubTransport, token: String = "t") -> (APIClient, MemoryTokenStore) {
        let tokens = MemoryTokenStore(token: token)
        return (APIClient(baseURL: base, transport: transport, tokens: tokens), tokens)
    }

    func testMacCommandParsesLikeTheWeb() {
        XCTAssertEqual(MacCommand.parse("/mac visao rode os testes"), .ask(project: "visao", prompt: "rode os testes"))
        XCTAssertEqual(MacCommand.parse("  /MAC api conserte\no build  "), .ask(project: "api", prompt: "conserte\no build"))
        XCTAssertEqual(MacCommand.parse("/mac"), .usage)
        XCTAssertEqual(MacCommand.parse("/mac visao"), .usage)
        XCTAssertNil(MacCommand.parse("/macaco"))
        XCTAssertNil(MacCommand.parse("olha o /mac visao"))
    }

    func testMacCommandInChatAsksTheArmInsteadOfSending() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/arm/tasks", status: 201, json: #"{"id":"t1","project":"visao","prompt":"rode os testes","status":"approved","requested_by":"owner","result":"","error":"","cost_usd":null,"claude_session_id":null,"conversation_id":"c1","created_at":"2026-11-13T12:00:00Z","finished_at":null}"#)
        transport.on("GET", "/api/conversations/c1/messages", json: "[\(Fixture.message("m1", role: "assistant", content: "Mandei para o Mac"))]")
        let store = ChatStore(api: api(transport).0, conversationId: "c1")

        store.send("/mac visao rode os testes")
        let clock = ContinuousClock()
        let deadline = clock.now + .seconds(3)
        while store.messages.isEmpty, clock.now < deadline { try await Task.sleep(for: .milliseconds(5)) }

        XCTAssertEqual(transport.count("POST", "/api/conversations/c1/messages"), 0, "not a message to him")
        let body = try XCTUnwrap(transport.requests.first?.httpBody)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: String])
        XCTAssertEqual(json, ["project": "visao", "prompt": "rode os testes", "conversation_id": "c1"])
        XCTAssertEqual(store.messages.map(\.content), ["Mandei para o Mac"])

        store.send("/mac")
        XCTAssertEqual(store.error, MacCommand.usageText)
    }

    func testMindDecodesAndNotesCanBeUndone() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/mind", json: #"{"enabled":true,"temperament":{"states":[{"name":"curiosidade","value":0.7,"level":"alta","why":"muitas perguntas"}],"traits":[],"avoids":[{"name":"insistir","value":0.2,"level":"baixa","why":"você não respondeu"}]},"questions":[{"question":"Você ainda usa Rust?","status":"waiting","answer":""}],"self_text":"Sou curioso.","interests":[{"topic":"Rust","why":"você falou","strength":0.5}],"thoughts":[{"content":"Pensei em X","created_at":"2026-11-13T12:00:00","ask_owner":"","wanted_to_say":"Oi","delivery":"quiet_hours"}],"self_history":[{"version":2,"content":"Sou curioso.","reason":"conversas","created_at":"2026-11-13T12:00:00Z"}],"profile":{"content":"Mora em SP","reason":"disse","limit":800,"updated_at":null},"rules":{"content":"","reason":"","limit":800,"updated_at":null}}"#)
        transport.on("POST", "/api/mind/notes/profile/undo") { _ in (204, "") }
        transport.on("POST", "/api/mind/self/revert") { _ in (204, "") }
        let client = api(transport).0

        let mind = try await client.mind()
        XCTAssertEqual(mind.temperament.states.first?.level, "alta")
        XCTAssertEqual(mind.profile.content, "Mora em SP")
        XCTAssertEqual(Mind.deliveryLabel(mind.thoughts.first?.delivery), "guardou: horário silencioso")
        XCTAssertEqual(Mind.questionLabel("waiting"), "quero perguntar")
        try await client.undoNote("profile")
        try await client.revertSelf(to: nil)
        XCTAssertEqual(String(decoding: transport.requests.last?.httpBody ?? Data(), as: UTF8.self), #"{"version":null}"#)
    }

    func testStudyNotebookToleratesMissingParts() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/study", json: #"{"enabled":true,"paused":false,"interval_hours":6,"next_eligible_at":null,"source":"wikipedia","entries":[{"id":"e1","previous_entry_id":null,"status":"READY","topic":"rust","question":"Por que Rust é seguro?","rationale":"","outcome_reason":"evidence_recorded","created_at":"2026-11-13T12:00:00Z","evidence":{"findings":[{"claim":"Tem ownership","sources":[1]}],"sources":[{"id":1,"url":"https://pt.wikipedia.org/wiki/Rust","title":"Rust","retrieved_at":"x"}]}},{"id":"e2","previous_entry_id":null,"status":"SKIPPED","topic":"","question":"","rationale":"","outcome_reason":"no_sources","created_at":"2026-11-13T12:00:00Z","evidence":{}}]}"#)
        let notebook = try await api(transport).0.study()

        XCTAssertEqual(notebook.entries.first?.evidence.findings.first?.sources, [1])
        XCTAssertEqual(StudyNotebook.statusLabel("READY"), "Achados registrados")
        XCTAssertNil(StudyNotebook.reasonText(notebook.entries[0].outcomeReason))
        XCTAssertEqual(StudyNotebook.reasonText(notebook.entries[1].outcomeReason), "A busca não retornou trechos aproveitáveis.")
    }

    func testFeedbackSendsRatingAndTags() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/messages/m1/feedback", json: #"{"state_version":3,"state_changed":true}"#)
        let changed = try await api(transport).0.feedback(messageId: "m1", positive: false, tags: ["muito longo"])

        XCTAssertTrue(changed)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests[0].httpBody ?? Data()) as? [String: Any])
        XCTAssertEqual(body["rating"] as? Int, -1)
        XCTAssertEqual(body["tags"] as? [String], ["muito longo"])
    }

    func testChangingPasswordKeepsThisDeviceSignedIn() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/auth/password", json: #"{"access_token":"novo","token_type":"bearer","expires_in":3600}"#)
        let (client, tokens) = api(transport, token: "velho")

        try await client.changePassword(current: "a", new: "b")

        XCTAssertEqual(tokens.token, "novo")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests[0].httpBody ?? Data()) as? [String: String])
        XCTAssertEqual(body, ["current_password": "a", "new_password": "b"])
    }

    func testOnboardingBodies() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/onboarding", json: #"{"completed":true,"skipped":false,"saved":["profile"],"discarded":false}"#)
        let client = api(transport).0
        var answers = OnboardingAnswers()
        answers.who = "Allison"

        let result = try await client.finishOnboarding(answers)
        XCTAssertNotNil(result.closingNotice)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests[0].httpBody ?? Data()) as? [String: [String: String]])
        XCTAssertEqual(body["answers"]?["who"], "Allison")
        _ = try await client.skipOnboarding()
        XCTAssertEqual(String(decoding: transport.requests[1].httpBody ?? Data(), as: UTF8.self), #"{"skip":true}"#)
    }

    func testBenchAndPairing() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations/c1/bench", json: #"{"deeds":[{"at":"2026-11-13T12:00:00Z","text":"Leu github.com"}],"pages":[],"visits":[{"title":"Voos","url":"https://google.com/travel","at":"2026-11-13T12:00:00Z"}]}"#)
        transport.on("POST", "/api/arm/devices", status: 201, json: #"{"id":"d1","name":"Mac","projects":[],"version":"","online":false,"last_seen_at":null,"token":"segredo"}"#)
        let client = api(transport).0

        let bench = try await client.bench(conversationId: "c1")
        XCTAssertEqual(bench.deeds.first?.text, "Leu github.com")
        XCTAssertEqual(bench.visits.count, 1)
        let paired = try await client.pairArm(name: "Mac")
        XCTAssertEqual(paired.token, "segredo")
    }
}
