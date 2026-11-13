import Foundation
@testable import VisaoKit

/// Answers requests from a script and records what was sent.
final class StubTransport: HTTPTransport, @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) async throws -> (Int, String)

    private let lock = NSLock()
    private var handlers: [(method: String, path: String, handler: Handler)] = []
    private var _requests: [URLRequest] = []

    var requests: [URLRequest] { lock.withLock { _requests } }

    func on(_ method: String, _ path: String, status: Int = 200, json: String) {
        on(method, path) { _ in (status, json) }
    }

    func on(_ method: String, _ path: String, handler: @escaping Handler) {
        lock.withLock { handlers.append((method, path, handler)) }
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let path = request.url!.path
        let method = request.httpMethod ?? "GET"
        let match: Handler? = lock.withLock {
            _requests.append(request)
            // The latest registration wins, so a test can change an answer midway.
            return handlers.last(where: { $0.method == method && $0.path == path })?.handler
        }
        guard let match else {
            return (Data(#"{"detail":"Not Found"}"#.utf8), HTTPURLResponse(url: request.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!)
        }
        let (status, body) = try await match(request)
        return (Data(body.utf8), HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }

    func count(_ method: String, _ path: String) -> Int {
        requests.filter { $0.httpMethod == method && $0.url?.path == path }.count
    }
}

enum Fixture {
    static let conversationId = "6b1f7c2e-0a3d-4d0b-9c6e-2f2a1d7e9b10"

    static func message(_ id: String, role: String, content: String, at: String = "2026-11-13T12:00:00.123456") -> String {
        let escaped = content.replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: "\\n")
        return #"{"id":"\#(id)","role":"\#(role)","content":"\#(escaped)","created_at":"\#(at)","origin":"turn","attachments":[],"artifact":null,"reply_to":null}"#
    }

    static func turn(user: String, reply: String, userId: String = "u1", replyId: String = "a1") -> String {
        #"{"user_message":\#(message(userId, role: "user", content: user)),"assistant_message":\#(message(replyId, role: "assistant", content: reply)),"usage":{"provider":"fake","model":"m","input_tokens":1,"output_tokens":1,"cost_usd":"0.00","latency_ms":12},"curiosity":null,"sources":[{"title":"Wikipédia","url":"https://pt.wikipedia.org/wiki/X","source":"wikipedia"}]}"#
    }
}
