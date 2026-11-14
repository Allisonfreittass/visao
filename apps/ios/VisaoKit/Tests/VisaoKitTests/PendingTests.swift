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
