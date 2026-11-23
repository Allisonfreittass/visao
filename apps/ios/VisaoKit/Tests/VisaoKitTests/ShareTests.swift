import XCTest
@testable import VisaoKit

/// The share extension (docs/COMPARTILHAR.md, ADR-0018): files first, then POST /share, and the
/// token read from the group shared with the app.
@MainActor
final class ShareTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    func testTheBodyCarriesOnlyTheFieldsThereAre() throws {
        let only = try body(ShareRequest(note: "  ", url: "https://www.booking.com/hotel/cl/lastarria.html", title: nil, text: ""))
        XCTAssertEqual(only.keys.sorted(), ["url"], "empty comment, text and no files: left out")
        let full = try body(ShareRequest(note: "vale a pena?", url: "https://x.com", title: "Hotel", text: "café incluso", attachmentIds: ["a1"]))
        XCTAssertEqual(full.keys.sorted(), ["attachment_ids", "note", "text", "title", "url"])
        XCTAssertEqual(full["attachment_ids"] as? [String], ["a1"])
        XCTAssertEqual(full["note"] as? String, "vale a pena?")
    }

    func testFilesGoUpBeforeTheShareAnd202SaysSent() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments") { request in
            let id = request.httpBody?.contains(Data("b.pdf".utf8)) == true ? 2 : 1
            return (200, #"{"id":"att\#(id)","kind":"image","filename":"f.jpg","media_type":"image/jpeg","size_bytes":3}"#)
        }
        transport.on("POST", "/api/share", status: 202, json: #"{"conversation_id":"c1","content":"x"}"#)
        let sender = ShareSender(api: api(transport))
        let files = [PreparedFile(data: Data([1, 2, 3]), filename: "a.jpg", mimeType: "image/jpeg"),
                     PreparedFile(data: Data([4]), filename: "b.pdf", mimeType: "application/pdf")]

        await sender.send(ShareContent(url: URL(string: "https://x.com"), files: files), note: "cota isso")

        XCTAssertEqual(sender.state, .sent)
        XCTAssertEqual(transport.requests.map { $0.url!.path }, ["/api/attachments", "/api/attachments", "/api/share"])
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests.last!.httpBody!) as? [String: Any])
        XCTAssertEqual(sent["attachment_ids"] as? [String], ["att1", "att2"])
        XCTAssertEqual(sent["note"] as? String, "cota isso")
        XCTAssertNil(sent["text"])
        XCTAssertEqual(ShareSender.sentText, "Enviado. A resposta chega como aviso.")
    }

    func test422ShowsTheServersMessageAndRetryDoesNotUploadAgain() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments", json: #"{"id":"att1","kind":"image","filename":"f.jpg","media_type":"image/jpeg","size_bytes":3}"#)
        transport.on("POST", "/api/share", status: 422, json: #"{"detail":"Nada para compartilhar"}"#)
        let sender = ShareSender(api: api(transport))
        let content = ShareContent(files: [PreparedFile(data: Data([1]), filename: "a.jpg", mimeType: "image/jpeg")])

        await sender.send(content, note: "")
        XCTAssertEqual(sender.state, .failed("Nada para compartilhar"))

        transport.on("POST", "/api/share", status: 202, json: #"{"conversation_id":"c1","content":"x"}"#)
        await sender.send(content, note: "")
        XCTAssertEqual(sender.state, .sent)
        XCTAssertEqual(transport.count("POST", "/api/attachments"), 1, "the file that went up is not sent twice")
    }

    func test401AndNoTokenAskToSignInAgain() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/share", status: 401, json: #"{"detail":"Token inválido"}"#)
        let sender = ShareSender(api: api(transport))
        await sender.send(ShareContent(url: URL(string: "https://x.com")), note: "")
        XCTAssertEqual(sender.state, .signedOut)

        let none = StubTransport()
        let signedOut = ShareSender(api: APIClient(baseURL: base, transport: none, tokens: MemoryTokenStore()))
        await signedOut.send(ShareContent(url: URL(string: "https://x.com")), note: "")
        XCTAssertEqual(signedOut.state, .signedOut)
        XCTAssertTrue(none.requests.isEmpty, "nothing is sent without a token")
        XCTAssertEqual(ShareSender.signedOutText, "Abra o Visão e entre de novo")
    }

    // MARK: The token in the shared group

    func testTheExtensionReadsTheTokenFromTheGroup() {
        let keychain = FakeKeychain()
        let app = KeychainTokenStore(service: "visao.auth", accessGroup: "T.visao.shared", items: keychain)
        app.token = "abc"
        XCTAssertEqual(keychain.groupOf(service: "visao.auth"), "T.visao.shared")
        let extensionSide = KeychainTokenStore(service: "visao.auth", accessGroup: "T.visao.shared", items: keychain.visible(only: ["T.visao.shared"]))
        XCTAssertEqual(extensionSide.token, "abc")
    }

    func testTheOldItemMovesIntoTheGroupOnFirstOpen() {
        let keychain = FakeKeychain()
        _ = keychain.write(Data("old".utf8), service: "visao.auth", account: "access_token", group: nil)
        XCTAssertNil(keychain.groupOf(service: "visao.auth"))

        let store = KeychainTokenStore(service: "visao.auth", accessGroup: "T.visao.shared", items: keychain)
        store.migrateIfNeeded()

        XCTAssertEqual(keychain.groupOf(service: "visao.auth"), "T.visao.shared", "moved, so nobody signs in again")
        XCTAssertEqual(keychain.count, 1, "the old item is gone")
        XCTAssertEqual(store.token, "old")
        store.token = nil
        XCTAssertEqual(keychain.count, 0)
    }

    func testWithoutTheEntitlementItStillKeepsTheToken() {
        let keychain = FakeKeychain(allowed: [])
        let store = KeychainTokenStore(service: "visao.auth", accessGroup: "T.visao.shared", items: keychain)
        store.token = "abc"
        XCTAssertEqual(store.token, "abc")
        XCTAssertNil(keychain.groupOf(service: "visao.auth"))
    }

    func testSharedConfigReadsTheGroupsFromInfo() {
        let config = SharedConfig(info: [
            "VisaoAppGroup": "group.io.visao", "VisaoKeychainGroup": "T.io.visao.shared",
            "VisaoTokenService": "io.visao.auth", "VisaoAPIBaseURL": "https://h/api",
        ])
        XCTAssertEqual(config.appGroup, "group.io.visao")
        XCTAssertEqual(config.keychainGroup, "T.io.visao.shared")
        XCTAssertEqual(config.tokenService, "io.visao.auth")
        XCTAssertEqual(config.configuredServer.absoluteString, "https://h/api")
        let unfilled = SharedConfig(info: ["VisaoAppGroup": "$(VISAO_APP_GROUP)", "CFBundleIdentifier": "io.visao"])
        XCTAssertNil(unfilled.appGroup)
        XCTAssertEqual(unfilled.tokenService, "io.visao.auth", "the name the app used before")
    }

    private func body(_ request: ShareRequest) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any])
    }

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }
}

/// A Keychain with access groups: nil writes go to the default group (none here), nil reads see
/// every group this side can see.
final class FakeKeychain: KeychainItems, @unchecked Sendable {
    private final class Store: @unchecked Sendable {
        let lock = NSLock()
        var items: [(service: String, account: String, group: String?, data: Data)] = []
    }
    private let store: Store
    private let allowed: Set<String>?
    private let sees: Set<String>?

    init(allowed: Set<String>? = nil) {
        store = Store()
        self.allowed = allowed
        sees = nil
    }

    private init(store: Store, sees: Set<String>) {
        self.store = store
        allowed = sees
        self.sees = sees
    }

    func visible(only groups: Set<String>) -> FakeKeychain { FakeKeychain(store: store, sees: groups) }

    var count: Int { store.lock.withLock { store.items.count } }

    func groupOf(service: String) -> String? {
        store.lock.withLock { store.items.first { $0.service == service }?.group }
    }

    private func canSee(_ group: String?) -> Bool {
        guard let sees else { return true }
        return group.map(sees.contains) ?? false
    }

    func read(service: String, account: String, group: String?) -> Data? {
        store.lock.withLock {
            store.items.first { $0.service == service && $0.account == account && (group == nil ? canSee($0.group) : $0.group == group) }?.data
        }
    }

    func write(_ data: Data, service: String, account: String, group: String?) -> Bool {
        if let group, let allowed, !allowed.contains(group) { return false }
        store.lock.withLock { store.items.append((service, account, group, data)) }
        return true
    }

    func delete(service: String, account: String, group: String?) {
        store.lock.withLock {
            store.items.removeAll { $0.service == service && $0.account == account && (group == nil ? canSee($0.group) : $0.group == group) }
        }
    }
}
