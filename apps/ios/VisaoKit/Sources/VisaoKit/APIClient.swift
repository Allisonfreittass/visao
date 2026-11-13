import Foundation

public struct APIError: Error, Sendable, Equatable, LocalizedError {
    /// 0 when the request never got an answer (no network, server down).
    public let status: Int
    public let message: String

    public init(status: Int, message: String) {
        self.status = status
        self.message = message
    }

    public var errorDescription: String? { message }

    /// The token expired or was revoked: the app goes back to the login screen.
    public var isUnauthorized: Bool { status == 401 }

    /// Parar reached the server before the reply was written.
    public var isStoppedByOwner: Bool { status == 409 && message == "Parado por você" }
}

/// What actually sends a request. URLSession in the app, a stub in the tests.
public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

extension URLSession: HTTPTransport {
    public func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(status: 0, message: "Resposta inválida do servidor")
        }
        return (data, http)
    }
}

/// Thin typed client for the VISÃO API (apps/web/src/api.ts is the behavior it follows).
/// `baseURL` already includes the API prefix: "https://host/api", or "http://mac.local:8000".
public final class APIClient: Sendable {
    public let baseURL: URL
    private let transport: HTTPTransport
    private let tokens: TokenStore

    public init(baseURL: URL, transport: HTTPTransport = URLSession.shared, tokens: TokenStore) {
        self.baseURL = baseURL
        self.transport = transport
        self.tokens = tokens
    }

    public var isAuthenticated: Bool { tokens.token != nil }

    // MARK: Auth

    /// OAuth2 password form: credentials go in the body, never in the URL.
    @discardableResult
    public func login(email: String, password: String) async throws -> String {
        let body = Self.formBody(["username": email, "password": password])
        let response: TokenResponse = try await request(
            "/auth/login", method: "POST", body: Data(body.utf8),
            contentType: "application/x-www-form-urlencoded", authenticated: false
        )
        tokens.token = response.accessToken
        return response.accessToken
    }

    public func logout() {
        tokens.token = nil
    }

    public func me() async throws -> UserInfo { try await request("/auth/me") }

    public func status() async throws -> SystemStatus { try await request("/system/status") }

    // MARK: Conversations

    public func conversations() async throws -> [Conversation] { try await request("/conversations") }

    public func createConversation(projectId: String? = nil) async throws -> Conversation {
        var query: [URLQueryItem] = []
        if let projectId { query.append(URLQueryItem(name: "project_id", value: projectId)) }
        return try await request("/conversations", method: "POST", query: query)
    }

    public func messages(conversationId: String) async throws -> [Message] {
        try await request("/conversations/\(segment(conversationId))/messages")
    }

    public func send(
        conversationId: String, content: String, modality: String = "text",
        attachmentIds: [String] = [], replyToId: String? = nil
    ) async throws -> Turn {
        let body = SendBody(content: content, modality: modality, attachmentIds: attachmentIds, replyToId: replyToId)
        return try await request(
            "/conversations/\(segment(conversationId))/messages", method: "POST",
            body: try JSONEncoder().encode(body), contentType: "application/json"
        )
    }

    public func progress(conversationId: String) async throws -> TurnProgress {
        try await request("/conversations/\(segment(conversationId))/progress")
    }

    /// Parar: the turn in flight stops at its next step.
    @discardableResult
    public func cancel(conversationId: String) async throws -> Bool {
        let result: [String: Bool] = try await request("/conversations/\(segment(conversationId))/cancel", method: "POST")
        return result["cancelled"] ?? false
    }

    /// A page's full address, to open or share: anyone with it can see the page.
    public func pageURL(path: String) -> URL {
        URL(string: baseURL.absoluteString.trimmingSuffix("/") + path) ?? baseURL
    }

    // MARK: Plumbing

    struct SendBody: Encodable {
        let content: String
        let modality: String
        let attachmentIds: [String]
        let replyToId: String?

        enum CodingKeys: String, CodingKey {
            case content, modality
            case attachmentIds = "attachment_ids"
            case replyToId = "reply_to_id"
        }

        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(content, forKey: .content)
            try c.encode(modality, forKey: .modality)
            try c.encode(attachmentIds, forKey: .attachmentIds)
            // null, not missing: the same body the web sends.
            try c.encode(replyToId, forKey: .replyToId)
        }
    }

    /// application/x-www-form-urlencoded with everything but unreserved characters escaped, so a
    /// password with "+", "&" or "=" arrives as typed. Keys in a fixed order.
    static func formBody(_ fields: [String: String]) -> String {
        let unreserved = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
        return fields.keys.sorted().map { key in
            let value = fields[key] ?? ""
            return "\(key)=\(value.addingPercentEncoding(withAllowedCharacters: unreserved) ?? "")"
        }.joined(separator: "&")
    }

    private func segment(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }

    func makeRequest(
        _ path: String, method: String = "GET", query: [URLQueryItem] = [], body: Data? = nil,
        contentType: String? = nil, authenticated: Bool = true
    ) -> URLRequest {
        var components = URLComponents(string: baseURL.absoluteString.trimmingSuffix("/") + path)!
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let contentType { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        if authenticated, let token = tokens.token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    func request<T: Decodable>(
        _ path: String, method: String = "GET", query: [URLQueryItem] = [], body: Data? = nil,
        contentType: String? = nil, authenticated: Bool = true
    ) async throws -> T {
        let data = try await raw(path, method: method, query: query, body: body, contentType: contentType, authenticated: authenticated)
        do {
            return try APIDate.decoder.decode(T.self, from: data)
        } catch {
            throw APIError(status: 0, message: "Resposta inesperada do servidor")
        }
    }

    func raw(
        _ path: String, method: String = "GET", query: [URLQueryItem] = [], body: Data? = nil,
        contentType: String? = nil, authenticated: Bool = true
    ) async throws -> Data {
        let request = makeRequest(path, method: method, query: query, body: body, contentType: contentType, authenticated: authenticated)
        let data: Data
        let response: HTTPURLResponse
        do {
            (data, response) = try await transport.send(request)
        } catch let error as APIError {
            throw error
        } catch {
            // Stopping (task cancelled) is not a network failure: let the caller tell them apart.
            if error is CancellationError || (error as? URLError)?.code == .cancelled { throw CancellationError() }
            throw APIError(status: 0, message: "Sem conexão com o servidor")
        }
        guard (200..<300).contains(response.statusCode) else {
            if response.statusCode == 401, authenticated { tokens.token = nil }
            throw APIError(status: response.statusCode, message: Self.detail(from: data, status: response.statusCode))
        }
        return data
    }

    /// FastAPI puts the reason in "detail"; validation errors send a list instead of a string.
    static func detail(from data: Data, status: Int) -> String {
        if let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let text = body["detail"] as? String { return text }
            if let list = body["detail"] as? [[String: Any]], let first = list.first?["msg"] as? String { return first }
        }
        return HTTPURLResponse.localizedString(forStatusCode: status)
    }
}

extension String {
    func trimmingSuffix(_ suffix: String) -> String {
        hasSuffix(suffix) ? String(dropLast(suffix.count)) : self
    }
}
