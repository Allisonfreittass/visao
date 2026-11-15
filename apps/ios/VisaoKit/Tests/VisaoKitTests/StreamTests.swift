import XCTest
@testable import VisaoKit

/// The reply as it is written (docs/decisions/0011): the SSE parser, resuming after a drop, the
/// steady reveal, and ChatStore following the stream or falling back to /progress.
final class SSEParserTests: XCTestCase {
    private func bytes(_ text: String) -> [UInt8] { Array(text.utf8) }

    func testEventsSplitAcrossChunksWithIdsAndJSON() {
        var parser = SSEParser()
        XCTAssertEqual(parser.push(bytes("retry: 2000\n\nid: 7\nevent: delta\nda")), [])
        XCTAssertEqual(parser.push(bytes("ta: {\"text\":\"Oi\"}\n\n")), [SSEEvent(id: 7, kind: "delta", data: #"{"text":"Oi"}"#)])
        XCTAssertEqual(parser.lastId, 7)
    }

    func testCRLFEvenWhenSplitAndSeveralDataLines() {
        var parser = SSEParser()
        XCTAssertEqual(parser.push(bytes(": aqui\r\nevent: x\r\ndata: um\r")), [])
        XCTAssertEqual(parser.push(bytes("\ndata: dois\r\n\r\n")), [SSEEvent(id: nil, kind: "x", data: "um\ndois")])
    }

    func testAccentsSurviveAChunkCutInTheMiddleOfALetter() {
        var parser = SSEParser()
        let all = bytes("event: delta\ndata: {\"text\":\"ação\"}\n\n")
        let cut = all.firstIndex(of: 0xC3)! + 1 // inside "ç"
        XCTAssertEqual(parser.push(all[..<cut]), [])
        let events = parser.push(all[cut...])
        guard case .delta(let text)? = events.first.flatMap(TurnEvent.init) else { return XCTFail("no delta") }
        XCTAssertEqual(text, "ação")
    }

    func testTurnEventsDecode() {
        guard case .step(let step)? = TurnEvent(SSEEvent(id: 1, kind: "step", data: #"{"label":"Cotando voos","detail":"google.com"}"#)) else { return XCTFail() }
        XCTAssertEqual(step, ProgressStep(label: "Cotando voos", detail: "google.com"))
        guard case .failed(let error)? = TurnEvent(SSEEvent(id: 2, kind: "error", data: #"{"status":409,"message":"Parado por você"}"#)) else { return XCTFail() }
        XCTAssertTrue(error.isStoppedByOwner)
        guard case .done(let turn)? = TurnEvent(SSEEvent(id: 3, kind: "done", data: Fixture.turn(user: "oi", reply: "olá"))) else { return XCTFail() }
        XCTAssertEqual(turn.assistantMessage.content, "olá")
    }

    func testRevealGoesSteadilyAndCatchesUp() {
        XCTAssertEqual(Reveal.step(shown: 0, target: 100, dt: 0.1), 10, accuracy: 0.01)
        XCTAssertEqual(Reveal.step(shown: 0, target: 20, dt: 0.1), 4.5, accuracy: 0.01)
        XCTAssertEqual(Reveal.step(shown: 18, target: 20, dt: 1), 20)
        XCTAssertEqual(Reveal.commonPrefix("Fica em Camberra. Quer?", "Fica em Camberra."), 17)
    }
}

/// A transport that also streams: scripted bodies, one per stream opened, and plain requests
/// answered by a StubTransport.
final class StreamingStub: HTTPTransport, HTTPStreamTransport, @unchecked Sendable {
    let plain = StubTransport()
    private let lock = NSLock()
    /// Each: the chunks, and whether the connection drops after them.
    private var bodies: [(chunks: [String], drop: Bool, status: Int)] = []
    private(set) var lastEventIds: [String?] = []

    func script(_ chunks: [String], drop: Bool = false, status: Int = 200) {
        lock.withLock { bodies.append((chunks, drop, status)) }
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        try await plain.send(request)
    }

    func stream(_ request: URLRequest) async throws -> (HTTPURLResponse, AsyncThrowingStream<[UInt8], Error>) {
        let next: (chunks: [String], drop: Bool, status: Int)? = lock.withLock {
            lastEventIds.append(request.value(forHTTPHeaderField: "Last-Event-ID"))
            return bodies.isEmpty ? nil : bodies.removeFirst()
        }
        let body = next ?? ([], false, 404)
        let response = HTTPURLResponse(url: request.url!, statusCode: body.status, httpVersion: nil, headerFields: nil)!
        let chunks = AsyncThrowingStream<[UInt8], Error> { continuation in
            for chunk in body.chunks { continuation.yield(Array(chunk.utf8)) }
            if body.drop { continuation.finish(throwing: URLError(.networkConnectionLost)) } else { continuation.finish() }
        }
        return (response, chunks)
    }
}

@MainActor
final class StreamFollowTests: XCTestCase {
    private func api(_ transport: some HTTPTransport) -> APIClient {
        APIClient(baseURL: URL(string: "https://visao.test/api")!, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }

    func testItResumesAfterADropWithTheLastIdSeen() async throws {
        let stub = StreamingStub()
        stub.script(["id: 1\nevent: delta\ndata: {\"text\":\"Cam\"}\n\n"], drop: true)
        stub.script(["id: 2\nevent: delta\ndata: {\"text\":\"berra\"}\n\n", "id: 3\nevent: done\ndata: \(Fixture.turn(user: "oi", reply: "Camberra"))\n\n"])
        var text = ""
        let end = try await api(stub).followTurn(conversationId: "c1", retryDelay: .milliseconds(1)) { event in
            if case .delta(let piece) = event { text += piece }
        }
        XCTAssertEqual(end, .done)
        XCTAssertEqual(text, "Camberra")
        XCTAssertEqual(stub.lastEventIds, [nil, "1"])
    }

    func testWithoutAStreamItThrowsAndAnEmptyOneIsEmpty() async throws {
        let stub = StreamingStub()
        stub.script(["retry: 2000\n\n"])
        let empty = try await api(stub).followTurn(conversationId: "c1") { _ in }
        XCTAssertEqual(empty, .empty)
        do {
            _ = try await api(StubTransport()).followTurn(conversationId: "c1") { _ in }
            XCTFail("a transport without streams cannot follow")
        } catch {}
    }

    func testChatStoreShowsTheTextAsItComesThenSettlesIntoTheMessage() async throws {
        let stub = StreamingStub()
        let gate = Gate()
        stub.plain.on("POST", "/api/conversations/c1/messages") { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "oi", reply: "Camberra é a capital."))
        }
        stub.script([
            "id: 1\nevent: step\ndata: {\"label\":\"Escrevendo a resposta\",\"detail\":null}\n\n",
            "id: 2\nevent: delta\ndata: {\"text\":\"Camberra \"}\n\n",
        ])
        let store = ChatStore(api: api(stub), conversationId: "c1")
        store.send("oi")
        try await until { store.liveText == "Camberra " }
        XCTAssertEqual(store.liveStep?.label, "Escrevendo a resposta")

        await gate.open()
        try await until { !store.sending }
        XCTAssertEqual(store.settlingId, "a1", "the live bubble finishes showing the reply")
        XCTAssertEqual(store.liveText, "Camberra é a capital.")
        store.finishSettling()
        XCTAssertNil(store.settlingId)
        XCTAssertNil(store.liveText)
        XCTAssertEqual(store.messages.last?.content, "Camberra é a capital.")
    }

    func testWithoutTheStreamItAsksProgressAsBefore() async throws {
        let stub = StreamingStub() // no script: the stream answers 404
        let gate = Gate()
        stub.plain.on("POST", "/api/conversations/c1/messages") { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "oi", reply: "olá"))
        }
        stub.plain.on("GET", "/api/conversations/c1/progress", json: #"{"active":true,"elapsed_ms":10,"steps":[{"label":"Pensando","detail":null}],"draft":null}"#)
        let store = ChatStore(api: api(stub), conversationId: "c1", progressInterval: .milliseconds(10))
        store.send("oi")
        try await until { store.liveStep?.label == "Pensando" }
        await gate.open()
        try await until { !store.sending }
        XCTAssertGreaterThan(stub.plain.count("GET", "/api/conversations/c1/progress"), 0)
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
