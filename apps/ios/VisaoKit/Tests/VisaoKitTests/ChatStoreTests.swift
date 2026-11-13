import XCTest
@testable import VisaoKit

/// The send rules from apps/web/src/App.tsx: optimistic, queued while answering, stoppable.
@MainActor
final class ChatStoreTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!
    private let path = "/api/conversations/c1/messages"

    func testMessageShowsAtOnceThenServerCopyReplacesIt() async throws {
        let gate = Gate()
        let transport = StubTransport()
        transport.on("POST", path) { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "oi", reply: "olá"))
        }
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("  oi  ")
        try await until { store.sending }
        XCTAssertEqual(store.messages.map(\.content), ["oi"])
        XCTAssertEqual(store.messages.first?.local, .sending)

        await gate.open()
        try await until { !store.sending }
        XCTAssertEqual(store.messages.map(\.id), ["u1", "a1"])
        XCTAssertNil(store.messages[0].local)
        XCTAssertEqual(store.messages[1].sources.count, 1, "the reply keeps the turn's sources")
    }

    func testWhatYouWriteMeanwhileGoesAsOneMessage() async throws {
        let gate = Gate()
        let transport = StubTransport()
        transport.on("POST", path) { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "primeira", reply: "r1"))
        }
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("primeira")
        try await until { store.sending }
        let earlier = Message(id: "old", role: .assistant, content: "algo que ele disse", createdAt: Date())
        store.send("segunda")
        store.send("terceira", replyTo: earlier)
        XCTAssertEqual(store.messages.map(\.local), [.sending, .queued, .queued])

        // The second turn: the batch, joined, answering the quoted message.
        transport.on("POST", path) { _ in (200, Fixture.turn(user: "segunda\n\nterceira", reply: "r2", userId: "u2", replyId: "a2")) }
        await gate.open()
        try await until { store.messages.map(\.id) == ["u1", "a1", "u2", "a2"] }
        try await until { !store.sending }

        XCTAssertEqual(transport.count("POST", path), 2, "two turns, not three")
        let second = try XCTUnwrap(transport.requests.last?.httpBody)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: second) as? [String: Any])
        XCTAssertEqual(body["content"] as? String, "segunda\n\nterceira")
        XCTAssertEqual(body["reply_to_id"] as? String, "old")
    }

    func testFailedMessageStaysVisible() async throws {
        let transport = StubTransport()
        transport.on("POST", path, status: 502, json: #"{"detail":"Falha no provedor de LLM (timeout); sem resposta"}"#)
        transport.on("GET", path, json: "[]")
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("oi")
        try await until { !store.sending && store.messages.first?.local == .failed }

        XCTAssertEqual(store.messages.map(\.content), ["oi"])
        XCTAssertEqual(store.error, "Falha no provedor de LLM (timeout); sem resposta")
    }

    func testFailedReplyButStoredMessageIsNotDuplicated() async throws {
        let transport = StubTransport()
        transport.on("POST", path, status: 502, json: #"{"detail":"x"}"#)
        let now = ISO8601DateFormatter().string(from: Date().addingTimeInterval(1))
        transport.on("GET", path, json: "[\(Fixture.message("u1", role: "user", content: "oi", at: now))]")
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("oi")
        try await until { !store.sending && store.messages.map(\.id) == ["u1"] }
        XCTAssertNil(store.messages[0].local)
    }

    func testStopCancelsOnServerAndMarksStopped() async throws {
        let transport = StubTransport()
        transport.on("POST", path) { _ in
            try await Task.sleep(for: .seconds(30))
            return (200, Fixture.turn(user: "oi", reply: "tarde"))
        }
        transport.on("POST", "/api/conversations/c1/cancel", json: #"{"cancelled":true}"#)
        transport.on("GET", path, json: "[]")
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("oi")
        try await until { store.canStop }
        store.stop()
        try await until { !store.sending }

        XCTAssertEqual(store.messages.first?.local, .stopped)
        XCTAssertNil(store.error, "stopping is not an error")
        try await until { transport.count("POST", "/api/conversations/c1/cancel") == 1 }
    }

    func testServerSideStopIsNotAnError() async throws {
        let transport = StubTransport()
        transport.on("POST", path, status: 409, json: #"{"detail":"Parado por você"}"#)
        transport.on("GET", path, json: "[]")
        let store = ChatStore(api: api(transport), conversationId: "c1")

        store.send("oi")
        try await until { !store.sending && store.messages.first?.local == .stopped }
        XCTAssertNil(store.error)
    }

    func testLiveStepComesFromProgressWhileVisible() async throws {
        let gate = Gate()
        let transport = StubTransport()
        transport.on("POST", path) { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "oi", reply: "olá"))
        }
        transport.on("GET", "/api/conversations/c1/progress", json: #"{"active":true,"elapsed_ms":10,"steps":[{"label":"Pensando"},{"label":"Abrindo github.com","detail":"github.com/x"}]}"#)
        let store = ChatStore(api: api(transport), conversationId: "c1", progressInterval: .milliseconds(20))

        store.send("oi")
        try await until { store.liveStep?.label == "Abrindo github.com" }
        XCTAssertEqual(store.liveSteps.count, 2)

        await gate.open()
        try await until { !store.sending }
        XCTAssertNil(store.liveStep)
    }

    func testProgressIsNotAskedWhileHidden() async throws {
        let gate = Gate()
        let transport = StubTransport()
        transport.on("POST", path) { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "oi", reply: "olá"))
        }
        transport.on("GET", "/api/conversations/c1/progress", json: #"{"active":true,"steps":[]}"#)
        let store = ChatStore(api: api(transport), conversationId: "c1", progressInterval: .milliseconds(10))
        store.isVisible = false

        store.send("oi")
        try await until { store.sending }
        try await Task.sleep(for: .milliseconds(80))
        XCTAssertEqual(transport.count("GET", "/api/conversations/c1/progress"), 0)
        await gate.open()
        try await until { !store.sending }
    }

    func testFirstMessageCreatesTheConversation() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations", json: #"{"id":"c1","created_at":"2026-11-13T10:00:00Z"}"#)
        transport.on("POST", path, json: Fixture.turn(user: "oi", reply: "olá"))
        let store = ChatStore(api: api(transport), conversationId: nil)
        var created: [String] = []
        store.onConversationCreated = { created.append($0.id) }

        store.send("oi")
        try await until { store.messages.count == 2 }

        XCTAssertEqual(store.conversationId, "c1")
        XCTAssertEqual(created, ["c1"])
    }

    func testRefreshKeepsUnsentAndPicksUpInitiative() async throws {
        let transport = StubTransport()
        transport.on("POST", path, status: 502, json: #"{"detail":"x"}"#)
        transport.on("GET", path, json: "[]")
        let store = ChatStore(api: api(transport), conversationId: "c1")
        store.send("não foi")
        try await until { !store.sending && store.messages.first?.local == .failed }

        transport.on("GET", path, json: "[\(Fixture.message("i1", role: "assistant", content: "Lembrei de uma coisa"))]")
        await store.refresh()

        XCTAssertEqual(store.messages.map(\.content), ["Lembrei de uma coisa", "não foi"])
    }

    func testBlankMessageIsIgnored() {
        let store = ChatStore(api: api(StubTransport()), conversationId: "c1")
        store.send("   \n ")
        XCTAssertTrue(store.messages.isEmpty)
        XCTAssertFalse(store.sending)
    }

    // MARK: helpers

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }

    private func until(timeout: Duration = .seconds(3), _ condition: () -> Bool) async throws {
        let clock = ContinuousClock()
        let deadline = clock.now + timeout
        while !condition() {
            if clock.now > deadline {
                XCTFail("condition never held")
                return
            }
            try await Task.sleep(for: .milliseconds(5))
        }
    }
}

/// Holds a stubbed request until the test lets it go.
actor Gate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
        isOpen = true
        waiters.forEach { $0.resume() }
        waiters = []
    }
}
