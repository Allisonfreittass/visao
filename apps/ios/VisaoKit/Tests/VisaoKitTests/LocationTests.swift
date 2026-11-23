import XCTest
@testable import VisaoKit

/// "Perto de mim" (docs/LOCALIZACAO.md, ADR-0020): the position leaves the phone only with the
/// switch on and a message about somewhere near.
@MainActor
final class LocationTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!
    private let path = "/api/conversations/c1/messages"
    private let here = SentLocation(lat: -23.5614, lon: -46.6559, accuracyM: 35, at: Date(timeIntervalSince1970: 1_794_859_200))

    /// The same cases as apps/web/src/location.test.ts.
    func testTheRuleMatchesQuestionsAboutSomewhereNear() {
        for text in ["tem farmácia aberta aqui perto?", "qual o posto mais perto?", "algum restaurante bom por aqui?", "onde tem caixa eletrônico perto de mim", "tem padaria perto?"] {
            XCTAssertTrue(Nearby.asks(text), text)
        }
        for text in ["estou perto de terminar o projeto", "já está perto do Natal", "daqui a pouco te respondo", "aqui está o link que te falei"] {
            XCTAssertFalse(Nearby.asks(text), text)
        }
        XCTAssertTrue(Nearby.asks("TEM FARMÁCIA NA MINHA REGIÃO?"), "without accents and in lower case")
        XCTAssertFalse(Nearby.asks(String(repeating: "a", count: 1000) + " aqui perto"), "a long text is not a question")
    }

    func testWithTheSwitchOffThePositionIsNeverAskedFor() async {
        let source = CountingSource(location: here)
        let off = await LocationPrefs.position(for: "tem farmácia aqui perto?", enabled: false, source: source)
        XCTAssertNil(off)
        let notNear = await LocationPrefs.position(for: "já está perto do Natal", enabled: true, source: source)
        XCTAssertNil(notNear)
        XCTAssertEqual(source.calls, 0)
        let on = await LocationPrefs.position(for: "tem farmácia aqui perto?", enabled: true, source: source)
        XCTAssertEqual(on, here)
        XCTAssertEqual(source.calls, 1)
    }

    func testTheSwitchIsOffByDefault() throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "visao-location-test-\(UUID())"))
        XCTAssertFalse(LocationPrefs.enabled(in: defaults))
        LocationPrefs.set(true, in: defaults)
        XCTAssertTrue(LocationPrefs.enabled(in: defaults))
    }

    func testTheMessageBodyWithAndWithoutLocation() async throws {
        let transport = StubTransport()
        transport.on("POST", path, json: Fixture.turn(user: "x", reply: "y"))
        let store = ChatStore(api: api(transport), conversationId: "c1")
        let here = self.here
        store.locate = { text in Nearby.asks(text) ? here : nil }

        store.send("tem farmácia aberta aqui perto?")
        try await until { !store.sending && transport.count("POST", path) == 1 }
        let with = try sentBody(transport, index: 0)
        let location = try XCTUnwrap(with["location"] as? [String: Any])
        XCTAssertEqual(location["lat"] as? Double, -23.5614)
        XCTAssertEqual(location["lon"] as? Double, -46.6559)
        XCTAssertEqual(location["accuracy_m"] as? Double, 35)
        XCTAssertEqual(location["at"] as? String, "2026-11-16T20:00:00Z", "ISO 8601 in UTC")

        store.send("e amanhã?")
        try await until { !store.sending && transport.count("POST", path) == 2 }
        let without = try sentBody(transport, index: 1)
        XCTAssertNil(without["location"], "never with another message")
        XCTAssertFalse(store.messages.contains { $0.content.contains("-23.56") }, "kept nowhere on screen")
    }

    func testTheShareCarriesItOnlyWhenTheCommentAsks() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/share", status: 202, json: #"{"conversation_id":"c1","content":"x"}"#)
        let sender = ShareSender(api: api(transport))
        let here = self.here
        let locate: (String) async -> SentLocation? = { text in Nearby.asks(text) ? here : nil }

        await sender.send(ShareContent(url: URL(string: "https://x.com")), note: "tem algo assim aqui perto?", locate: locate)
        let first = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests[0].httpBody!) as? [String: Any])
        XCTAssertNotNil(first["location"])

        await sender.send(ShareContent(url: URL(string: "https://x.com")), note: "vale a pena?", locate: locate)
        let second = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests[1].httpBody!) as? [String: Any])
        XCTAssertNil(second["location"])
    }

    private func sentBody(_ transport: StubTransport, index: Int) throws -> [String: Any] {
        let posts = transport.requests.filter { $0.httpMethod == "POST" }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(posts[index].httpBody)) as? [String: Any])
    }

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }

    private func until(timeout: Duration = .seconds(3), _ condition: () -> Bool) async throws {
        let clock = ContinuousClock()
        let deadline = clock.now + timeout
        while !condition() {
            if clock.now > deadline { return XCTFail("condition never held") }
            try await Task.sleep(for: .milliseconds(5))
        }
    }
}

private final class CountingSource: PositionSource, @unchecked Sendable {
    private let lock = NSLock()
    private var _calls = 0
    let location: SentLocation
    var calls: Int { lock.withLock { _calls } }

    init(location: SentLocation) { self.location = location }

    func current() async -> SentLocation? {
        lock.withLock { _calls += 1 }
        return location
    }
}
