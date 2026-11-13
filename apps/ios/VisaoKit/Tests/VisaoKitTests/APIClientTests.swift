import XCTest
@testable import VisaoKit

final class APIClientTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    func testLoginSendsOAuth2FormAndKeepsToken() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/auth/login", json: #"{"access_token":"tok-1","token_type":"bearer","expires_in":3600}"#)
        let tokens = MemoryTokenStore()
        let api = APIClient(baseURL: base, transport: transport, tokens: tokens)

        let token = try await api.login(email: "eu+teste@exemplo.com", password: "a&b=c d+é")

        XCTAssertEqual(token, "tok-1")
        XCTAssertEqual(tokens.token, "tok-1")
        let request = try XCTUnwrap(transport.requests.first)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/x-www-form-urlencoded")
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(request.url?.query, "credentials never go in the URL")
        let body = String(decoding: request.httpBody ?? Data(), as: UTF8.self)
        XCTAssertEqual(body, "password=a%26b%3Dc%20d%2B%C3%A9&username=eu%2Bteste%40exemplo.com")
    }

    func testAuthenticatedCallsCarryBearerToken() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations", json: #"[{"id":"c1","created_at":"2026-11-13T10:00:00Z","memory_status":null,"project_id":null}]"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "tok-9"))

        let list = try await api.conversations()

        XCTAssertEqual(list.map(\.id), ["c1"])
        XCTAssertEqual(transport.requests.first?.value(forHTTPHeaderField: "Authorization"), "Bearer tok-9")
    }

    func testUnauthorizedClearsTokenAndSaysWhy() async {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations", status: 401, json: #"{"detail":"Token inválido"}"#)
        let tokens = MemoryTokenStore(token: "velho")
        let api = APIClient(baseURL: base, transport: transport, tokens: tokens)

        do {
            _ = try await api.conversations()
            XCTFail("should throw")
        } catch let error as APIError {
            XCTAssertTrue(error.isUnauthorized)
            XCTAssertEqual(error.message, "Token inválido")
        } catch {
            XCTFail("unexpected \(error)")
        }
        XCTAssertNil(tokens.token)
    }

    func testWrongPasswordDoesNotDropAnotherSession() async {
        let transport = StubTransport()
        transport.on("POST", "/api/auth/login", status: 401, json: #"{"detail":"Credenciais inválidas"}"#)
        let tokens = MemoryTokenStore(token: "atual")
        let api = APIClient(baseURL: base, transport: transport, tokens: tokens)

        await XCTAssertThrowsAPIError(try await api.login(email: "a@b.c", password: "x"), status: 401, message: "Credenciais inválidas")
        XCTAssertEqual(tokens.token, "atual")
    }

    func testValidationErrorListBecomesMessage() async {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations/c1/messages", status: 422, json: #"{"detail":[{"loc":["body","content"],"msg":"String should have at most 8000 characters","type":"string_too_long"}]}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        await XCTAssertThrowsAPIError(try await api.send(conversationId: "c1", content: "x"), status: 422, message: "String should have at most 8000 characters")
    }

    func testSendBodyMatchesTheWeb() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations/c1/messages", json: Fixture.turn(user: "oi", reply: "olá"))
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let turn = try await api.send(conversationId: "c1", content: "oi")

        XCTAssertEqual(turn.assistantMessage.content, "olá")
        XCTAssertEqual(turn.sources.first?.source, "wikipedia")
        let request = try XCTUnwrap(transport.requests.first)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any])
        XCTAssertEqual(body["content"] as? String, "oi")
        XCTAssertEqual(body["modality"] as? String, "text")
        XCTAssertEqual(body["attachment_ids"] as? [String], [])
        XCTAssertTrue(body["reply_to_id"] is NSNull, "reply_to_id goes as null")
    }

    func testCreateConversationInProjectUsesQuery() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations", json: #"{"id":"c2","created_at":"2026-11-13T10:00:00","memory_status":"failed","project_id":"p1"}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let created = try await api.createConversation(projectId: "p1")

        XCTAssertTrue(created.memoryUnavailable)
        XCTAssertEqual(transport.requests.first?.url?.query, "project_id=p1")
    }

    func testMessageDecodesOptionalFieldsAndReplyTo() throws {
        let json = #"[{"id":"m1","role":"assistant","content":"x","created_at":"2026-11-13T12:00:00.5+00:00","origin":"initiative","attachments":[{"id":"f1","kind":"image","filename":"a.jpg","media_type":"image/jpeg","size_bytes":10,"readable":null}],"artifact":{"id":"p1","title":"Plano","status":"ready","path":"/p/abc","error":null,"conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"},"reply_to":{"id":"m0","role":"user","excerpt":"antes"}},{"id":"m2","role":"user","content":"y","created_at":"2026-11-13T12:01:00"}]"#
        let list = try APIDate.decoder.decode([Message].self, from: Data(json.utf8))

        XCTAssertEqual(list[0].origin, "initiative")
        XCTAssertTrue(list[0].attachments[0].isImage)
        XCTAssertEqual(list[0].artifact?.path, "/p/abc")
        XCTAssertEqual(list[0].replyTo, Quoted(id: "m0", role: .user, excerpt: "antes"))
        XCTAssertEqual(list[1].origin, "turn", "origin defaults to turn")
        XCTAssertEqual(list[1].attachments, [])
    }

    func testProgressAndCancel() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations/c1/progress", json: #"{"active":true,"elapsed_ms":1200,"steps":[{"label":"Pensando","detail":null},{"label":"Pesquisando “voos”","detail":"na web"}]}"#)
        transport.on("POST", "/api/conversations/c1/cancel", json: #"{"cancelled":true}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let progress = try await api.progress(conversationId: "c1")
        XCTAssertEqual(progress.steps.last, ProgressStep(label: "Pesquisando “voos”", detail: "na web"))
        let cancelled = try await api.cancel(conversationId: "c1")
        XCTAssertTrue(cancelled)
    }

    func testNetworkFailureIsStatusZero() async {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations") { _ in throw URLError(.notConnectedToInternet) }
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        await XCTAssertThrowsAPIError(try await api.conversations(), status: 0, message: "Sem conexão com o servidor")
    }

    func testPageURLJoinsBase() {
        let api = APIClient(baseURL: URL(string: "https://visao.test/api/")!, transport: StubTransport(), tokens: MemoryTokenStore())
        XCTAssertEqual(api.pageURL(path: "/p/abc").absoluteString, "https://visao.test/api/p/abc")
    }
}

func XCTAssertThrowsAPIError<T>(
    _ expression: @autoclosure () async throws -> T, status: Int, message: String,
    file: StaticString = #filePath, line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail("should throw", file: file, line: line)
    } catch let error as APIError {
        XCTAssertEqual(error, APIError(status: status, message: message), file: file, line: line)
    } catch {
        XCTFail("unexpected \(error)", file: file, line: line)
    }
}
