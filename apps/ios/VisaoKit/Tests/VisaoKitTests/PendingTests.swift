import XCTest
@testable import VisaoKit

@MainActor
final class PendingTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    private let email = #"{"id":"g1","kind":"send_email","summary":"Email para ana@exemplo.com: Reunião","payload":{"to":"ana@exemplo.com","subject":"Reunião","body":"Oi Ana, confirmo amanhã."},"status":"pending","result":"","conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"}"#
    private let event = #"{"id":"g2","kind":"create_event","summary":"Evento: Dentista, 14/11 09:00","payload":{"title":"Dentista","start":"2026-11-14T09:00:00","end":"2026-11-14T10:00:00","attendees":[]},"status":"pending","result":"","conversation_id":"c2","created_at":"2026-11-13T12:00:00Z"}"#
    private func task(_ id: String, status: String, conversation: String = "c1") -> String {
        #"{"id":"\#(id)","project":"visao","prompt":"rode os testes","status":"\#(status)","requested_by":"agent","result":"","error":"","cost_usd":"0.12","claude_session_id":null,"conversation_id":"\#(conversation)","created_at":"2026-11-13T12:00:00.123456","finished_at":null}"#
    }

    func testAsksComeFromGoogleAndProposedMacWork() async {
        let transport = StubTransport()
        transport.on("GET", "/api/google/actions", json: "[\(email),\(event)]")
        transport.on("GET", "/api/arm/tasks", json: "[\(task("t1", status: "proposed")),\(task("t2", status: "done")),\(task("t3", status: "approved"))]")
        let store = PendingStore(api: api(transport))

        await store.refresh()

        XCTAssertEqual(store.asks.map(\.id), ["g1", "g2", "t1"], "only proposed Mac work waits for a yes")
        let here = store.asks(in: "c1")
        XCTAssertEqual(here.map(\.label), ["Email", "Mac · visao"])
        XCTAssertEqual(here[0].text, "Email para ana@exemplo.com: Reunião")
        XCTAssertEqual(here[0].detail, "Oi Ana, confirmo amanhã.", "you see the body you approve")
        XCTAssertNil(here[1].detail)
        XCTAssertEqual(store.asks(in: "c2").first?.label, "Agenda")
        XCTAssertTrue(store.asks(in: nil).isEmpty)
    }

    func testApproveByTouchIsRecordedAndLeaves() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/google/actions", json: "[\(email)]")
        transport.on("GET", "/api/arm/tasks", json: "[]")
        transport.on("POST", "/api/google/actions/g1/approve", json: email)
        let store = PendingStore(api: api(transport))
        await store.refresh()

        transport.on("GET", "/api/google/actions", json: "[]")
        let ok = await store.decide(try XCTUnwrap(store.asks.first), approve: true)

        XCTAssertTrue(ok)
        XCTAssertTrue(store.asks.isEmpty)
        let decision = try XCTUnwrap(transport.requests.first { $0.httpMethod == "POST" })
        XCTAssertEqual(decision.url?.query, "via=toque")
    }

    func testRejectMacByVoiceSaysVoz() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/google/actions", json: "[]")
        transport.on("GET", "/api/arm/tasks", json: "[\(task("t1", status: "proposed"))]")
        transport.on("POST", "/api/arm/tasks/t1/reject", json: task("t1", status: "rejected"))
        let store = PendingStore(api: api(transport))
        await store.refresh()

        let ok = await store.decide(try XCTUnwrap(store.asks.first), approve: false, via: .voz)

        XCTAssertTrue(ok)
        XCTAssertEqual(transport.requests.first { $0.httpMethod == "POST" }?.url?.query, "via=voz")
    }

    func testFailedDecisionIsNotReportedAsDone() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/google/actions", json: "[\(email)]")
        transport.on("GET", "/api/arm/tasks", json: "[]")
        transport.on("POST", "/api/google/actions/g1/approve", status: 409, json: #"{"detail":"Essa ação já foi decidida"}"#)
        let store = PendingStore(api: api(transport))
        var errors: [String] = []
        store.onError = { errors.append(($0 as? APIError)?.message ?? "") }
        await store.refresh()

        let ok = await store.decide(try XCTUnwrap(store.asks.first), approve: true)

        XCTAssertFalse(ok, "a failure never reads as done")
        XCTAssertEqual(errors, ["Essa ação já foi decidida"])
        XCTAssertEqual(store.asks.map(\.id), ["g1"], "still waiting, as the server says")
        XCTAssertTrue(store.deciding.isEmpty)
    }

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }
}

@MainActor
final class WorkspaceTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }

    func testGoalsAndNoticesCountButOpeningsDoNot() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/google/actions", json: "[]")
        transport.on("GET", "/api/arm/tasks", json: "[]")
        transport.on("GET", "/api/approvals", json: #"[{"id":"goal1","origin":"curiosity","kind":"research","title":"Estudar Rust","rationale":"Você falou disso","success_criteria":"","required_permissions":["web"],"budget":{},"status":"proposed","evidence":{},"created_at":"2026-11-13T12:00:00Z","history":[]}]"#)
        transport.on("GET", "/api/notifications", json: #"[{"id":"n1","kind":"initiative","title":"Ele","body":"Oi","goal_id":null,"created_at":"2026-11-13T12:00:00Z","deliver_after":null,"read_at":null},{"id":"n2","kind":"study","title":"Estudei","body":"Achei isto","goal_id":null,"created_at":"2026-11-13T12:00:00Z","deliver_after":null,"read_at":null},{"id":"n3","kind":"study","title":"Lida","body":"","goal_id":null,"created_at":"2026-11-13T12:00:00Z","deliver_after":null,"read_at":"2026-11-13T12:01:00Z"}]"#)
        transport.on("POST", "/api/notifications/n1/read") { _ in (204, "") }
        let store = PendingStore(api: api(transport))

        await store.refresh()
        XCTAssertEqual(store.goals.first?.requiredPermissions, ["web"])
        XCTAssertEqual(store.notices.map(\.id), ["n2"], "openings and read notices stay out")
        XCTAssertEqual(store.count, 2)

        await store.markOpeningsRead()
        XCTAssertEqual(transport.count("POST", "/api/notifications/n1/read"), 1)
        XCTAssertTrue(store.openings.isEmpty)
    }

    func testReplyToNoticeOpensConversation() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/notifications/n2/reply", json: #"{"conversation_id":"c9"}"#)
        for path in ["/api/google/actions", "/api/arm/tasks", "/api/approvals", "/api/notifications"] { transport.on("GET", path, json: "[]") }
        let store = PendingStore(api: api(transport))
        let notice = try APIDate.decoder.decode(AppNotice.self, from: Data(#"{"id":"n2","kind":"study","title":"t","body":"b","created_at":"2026-11-13T12:00:00Z","read_at":null}"#.utf8))

        let opened = await store.reply(notice, from: nil)

        XCTAssertEqual(opened, "c9")
        let body = try XCTUnwrap(transport.requests.first?.httpBody)
        XCTAssertEqual(String(decoding: body, as: UTF8.self), #"{"conversation_id":null}"#)
    }

    func testProjectsAndSettings() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/projects", json: #"[{"id":"p1","name":"Viagem","created_at":"2026-11-13T12:00:00Z","conversations":1,"pages":2,"files":0}]"#)
        transport.on("POST", "/api/projects", status: 201, json: #"{"id":"p2","name":"Novo","created_at":"2026-11-13T12:00:00Z"}"#)
        transport.on("PUT", "/api/conversations/c1/project", json: #"{"id":"c1","created_at":"2026-11-13T12:00:00Z","project_id":"p1"}"#)
        transport.on("GET", "/api/memory/settings", json: #"{"enabled":true}"#)
        transport.on("GET", "/api/system/autonomy", json: #"{"paused":false}"#)
        transport.on("GET", "/api/autonomy/permissions", json: #"{"auto_research":true}"#)
        transport.on("PUT", "/api/system/autonomy", json: #"{"paused":true}"#)
        let client = api(transport)

        let list = try await client.projects()
        XCTAssertEqual(list.first?.countsLabel, "1 conversa · 2 páginas")
        let created = try await client.createProject(name: "Novo")
        XCTAssertEqual(created.conversations, 0)
        let moved = try await client.moveConversation("c1", toProject: "p1")
        XCTAssertEqual(moved.projectId, "p1")
        let settings = try await client.serverSettings()
        XCTAssertEqual(settings, ServerSettings(memory: true, paused: false, autoResearch: true))
        let paused = try await client.setAutonomy(paused: true)
        XCTAssertTrue(paused)
        let pause = try XCTUnwrap(transport.requests.last { $0.httpMethod == "PUT" }?.httpBody)
        XCTAssertTrue(String(decoding: pause, as: UTF8.self).contains(#""paused":true"#))
    }

    func testNewConversationFromProjectIsCreatedInIt() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations", json: #"{"id":"c5","created_at":"2026-11-13T10:00:00Z","project_id":"p1"}"#)
        transport.on("POST", "/api/conversations/c5/messages", json: Fixture.turn(user: "oi", reply: "olá"))
        let store = ChatStore(api: api(transport), conversationId: nil, projectId: "p1")

        store.send("oi")
        let clock = ContinuousClock()
        let deadline = clock.now + .seconds(3)
        while store.messages.count < 2, clock.now < deadline { try await Task.sleep(for: .milliseconds(5)) }

        XCTAssertEqual(transport.requests.first?.url?.query, "project_id=p1")
    }
}
