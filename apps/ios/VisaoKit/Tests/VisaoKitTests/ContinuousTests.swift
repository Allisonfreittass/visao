import XCTest
@testable import VisaoKit

/// The continuous conversation (docs/CONVERSA_CONTINUA.md): Chat opens it, and it loads by pages.
@MainActor
final class ContinuousTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!
    private let path = "/api/conversations/c1/messages"

    func testConversationDecodesWithAndWithoutContinuous() throws {
        let with = try APIDate.decoder.decode(Conversation.self, from: Data(#"{"id":"c1","created_at":"2026-11-16T10:00:00Z","title":null,"project_id":null,"continuous":true}"#.utf8))
        XCTAssertTrue(with.continuous)
        let without = try APIDate.decoder.decode(Conversation.self, from: Data(#"{"id":"c2","created_at":"2026-11-13T10:00:00Z"}"#.utf8))
        XCTAssertFalse(without.continuous, "an older server has no field: not the continuous one")
    }

    func testContinuousConversationRoute() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations/continuous", json: #"{"id":"c1","created_at":"2026-11-16T10:00:00Z","continuous":true}"#)
        let conversation = try await api(transport).continuousConversation()
        XCTAssertEqual(conversation.id, "c1")
        XCTAssertEqual(transport.count("GET", "/api/conversations/continuous"), 1)
    }

    func testPagedLoadsTheLastHundredThenOlderBeforeTheFirst() async throws {
        let transport = StubTransport()
        let full = (0..<100).map { Fixture.message("m\($0 + 100)", role: $0 % 2 == 0 ? "user" : "assistant", content: "x\($0)") }
        transport.on("GET", path) { request in
            let query = request.url?.query ?? ""
            if query.contains("before=m100") {
                return (200, "[\(Fixture.message("m99", role: "assistant", content: "antiga"))]")
            }
            return (200, "[\(full.joined(separator: ","))]")
        }
        let store = ChatStore(api: api(transport), conversationId: "c1", paged: true)

        await store.load()
        XCTAssertEqual(store.messages.count, 100)
        XCTAssertTrue(store.olderLeft, "a full page: there may be more")
        XCTAssertEqual(transport.requests.first?.url?.query, "limit=100")

        await store.loadOlder()
        XCTAssertEqual(store.messages.first?.id, "m99")
        XCTAssertEqual(store.messages.count, 101)
        XCTAssertFalse(store.olderLeft, "less than a page: nothing older")
        XCTAssertEqual(transport.requests.last?.url?.query, "limit=100&before=m100")

        // A refresh asks for as many as are on screen, so the older ones stay.
        await store.refresh()
        XCTAssertEqual(transport.requests.last?.url?.query, "limit=101")
    }

    func testAProjectChatLoadsWhole() async throws {
        let transport = StubTransport()
        transport.on("GET", path, json: "[]")
        let store = ChatStore(api: api(transport), conversationId: "c1", projectId: "p1")
        await store.load()
        XCTAssertNil(transport.requests.first?.url?.query)
        XCTAssertFalse(store.olderLeft)
    }

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }
}
