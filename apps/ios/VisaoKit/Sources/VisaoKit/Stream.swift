import Foundation

// The reply as it is written (docs/decisions/0011): server-sent events from
// GET /conversations/{id}/stream, read with URLSession.bytes. A dropped connection resumes after
// the last event seen (Last-Event-ID); if the stream cannot be had, ChatStore polls /progress.
// Same rules as apps/web/src/stream.ts.

public struct SSEEvent: Sendable, Equatable {
    public let id: Int?
    public let kind: String
    public let data: String
}

/// text/event-stream, a chunk of bytes at a time. Works on bytes so a line ending is never
/// confused with a character ("\r\n" is one Character in Swift) and a chunk may end anywhere.
public struct SSEParser: Sendable {
    private var line: [UInt8] = []
    private var pendingCR = false
    private var id: Int?
    private var kind = ""
    private var data: [String] = []
    public private(set) var lastId: Int?

    public init() {}

    public mutating func push(_ bytes: some Sequence<UInt8>) -> [SSEEvent] {
        var out: [SSEEvent] = []
        for byte in bytes {
            if pendingCR {
                pendingCR = false
                if byte == 0x0A { continue } // "\r\n" is one line ending
            }
            if byte == 0x0D || byte == 0x0A {
                pendingCR = byte == 0x0D
                if let event = take(String(decoding: line, as: UTF8.self)) { out.append(event) }
                line.removeAll(keepingCapacity: true)
            } else {
                line.append(byte)
            }
        }
        return out
    }

    private mutating func take(_ text: String) -> SSEEvent? {
        if text.isEmpty {
            defer { id = nil; kind = ""; data = [] }
            guard !data.isEmpty else { return nil }
            if let id { lastId = id }
            return SSEEvent(id: id, kind: kind.isEmpty ? "message" : kind, data: data.joined(separator: "\n"))
        }
        if text.hasPrefix(":") { return nil } // a comment keeps the connection alive
        let field: Substring
        var value: Substring
        if let colon = text.firstIndex(of: ":") {
            field = text[..<colon]
            value = text[text.index(after: colon)...]
            if value.hasPrefix(" ") { value = value.dropFirst() }
        } else {
            field = Substring(text)
            value = ""
        }
        switch field {
        case "data": data.append(String(value))
        case "event": kind = String(value)
        case "id": if let number = Int(value) { id = number }
        default: break
        }
        return nil
    }
}

/// What the stream says about the turn, decoded.
public enum TurnEvent: Sendable {
    case step(ProgressStep)
    /// More of the reply's text.
    case delta(String)
    /// The whole text so far, when it changed instead of growing (the rule check rewrote it).
    case replace(String)
    /// Something now waits for a tap (Mac, email, a panel).
    case action
    case done(Turn)
    case failed(APIError)

    init?(_ event: SSEEvent) {
        let data = Data(event.data.utf8)
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        switch event.kind {
        case "step":
            guard let label = object["label"] as? String else { return nil }
            self = .step(ProgressStep(label: label, detail: object["detail"] as? String))
        case "delta":
            guard let text = object["text"] as? String else { return nil }
            self = .delta(text)
        case "replace":
            guard let text = object["text"] as? String else { return nil }
            self = .replace(text)
        case "action":
            self = .action
        case "done":
            guard let turn = try? APIDate.decoder.decode(Turn.self, from: data) else { return nil }
            self = .done(turn)
        case "error":
            self = .failed(APIError(status: object["status"] as? Int ?? 0, message: object["message"] as? String ?? "Algo deu errado"))
        default:
            return nil
        }
    }
}

public enum StreamEnd: Sendable, Equatable {
    case done
    case failed
    /// The server had no turn to show (it ended before the stream opened, say).
    case empty
}

/// A transport that can hand the body over as it arrives. URLSession can; a stub in the tests.
public protocol HTTPStreamTransport: Sendable {
    func stream(_ request: URLRequest) async throws -> (HTTPURLResponse, AsyncThrowingStream<[UInt8], Error>)
}

extension URLSession: HTTPStreamTransport {
    public func stream(_ request: URLRequest) async throws -> (HTTPURLResponse, AsyncThrowingStream<[UInt8], Error>) {
        let (bytes, response) = try await bytes(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(status: 0, message: "Resposta inválida do servidor")
        }
        let chunks = AsyncThrowingStream<[UInt8], Error> { continuation in
            let task = Task {
                var chunk: [UInt8] = []
                do {
                    for try await byte in bytes {
                        chunk.append(byte)
                        // A whole line at a time: an event goes out as soon as it ends.
                        if byte == 0x0A || chunk.count >= 1024 {
                            continuation.yield(chunk)
                            chunk.removeAll(keepingCapacity: true)
                        }
                    }
                    if !chunk.isEmpty { continuation.yield(chunk) }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
        return (http, chunks)
    }
}

extension APIClient {
    static let streamRetries = 3

    /// Follows the turn until `done` or `error`, resuming up to 3 times after a drop. Throws when
    /// it could not be read at all (the caller then polls /progress).
    public func followTurn(
        conversationId: String, retryDelay: Duration = .milliseconds(800),
        onEvent: @MainActor @Sendable (TurnEvent) -> Void
    ) async throws -> StreamEnd {
        var parser = SSEParser()
        var failures = 0
        var seen = 0
        while true {
            let chunks: AsyncThrowingStream<[UInt8], Error>
            do {
                chunks = try await openStream(conversationId: conversationId, lastEventId: parser.lastId)
            } catch {
                failures += 1
                if error is CancellationError || seen == 0 || failures > Self.streamRetries { throw error }
                try await Task.sleep(for: retryDelay)
                continue
            }
            var ended: StreamEnd?
            var dropped = false
            do {
                reading: for try await chunk in chunks {
                    for event in parser.push(chunk) {
                        seen += 1
                        guard let decoded = TurnEvent(event) else { continue }
                        await onEvent(decoded)
                        if case .done = decoded { ended = .done }
                        if case .failed = decoded { ended = .failed }
                    }
                    if ended != nil { break reading }
                }
            } catch {
                if error is CancellationError || Task.isCancelled { throw CancellationError() }
                dropped = true // resume after the last event seen
            }
            if let ended { return ended }
            if seen == 0 && !dropped { return .empty }
            failures += 1
            if Task.isCancelled { throw CancellationError() }
            if failures > Self.streamRetries { throw APIError(status: 0, message: "O stream caiu") }
            try await Task.sleep(for: retryDelay)
        }
    }

    func openStream(conversationId: String, lastEventId: Int?) async throws -> AsyncThrowingStream<[UInt8], Error> {
        guard let streaming = transport as? HTTPStreamTransport else {
            throw APIError(status: 0, message: "Sem stream neste transporte")
        }
        var request = makeRequest("/conversations/\(conversationId)/stream", method: "GET", query: [], body: nil, contentType: nil, authenticated: true)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let lastEventId { request.setValue(String(lastEventId), forHTTPHeaderField: "Last-Event-ID") }
        // A turn can take a while to start writing; the server sends a comment every 15 s.
        request.timeoutInterval = 60
        let (response, chunks): (HTTPURLResponse, AsyncThrowingStream<[UInt8], Error>)
        do {
            (response, chunks) = try await streaming.stream(request)
        } catch let error as APIError {
            throw error
        } catch {
            if error is CancellationError || (error as? URLError)?.code == .cancelled { throw CancellationError() }
            throw APIError(status: 0, message: "Sem conexão com o servidor")
        }
        guard response.statusCode == 200 else {
            throw APIError(status: response.statusCode, message: HTTPURLResponse.localizedString(forStatusCode: response.statusCode))
        }
        return chunks
    }
}

/// The text that came in bursts, let out at a steady pace: about 45 characters a second, faster
/// when it falls behind, never more than about a second behind (stream.ts on the web).
public enum Reveal {
    public static let charactersPerSecond: Double = 45
    public static let maxLagSeconds: Double = 1

    public static func step(shown: Double, target: Int, dt: Double) -> Double {
        let total = Double(target)
        guard shown < total else { return total }
        let rate = max(charactersPerSecond, (total - shown) / maxLagSeconds)
        return min(total, shown + max(1, rate * dt))
    }

    /// Where two texts stop agreeing (a `replace` keeps what was already right), in Characters.
    public static func commonPrefix(_ a: String, _ b: String) -> Int {
        var count = 0
        for (x, y) in zip(a, b) {
            guard x == y else { break }
            count += 1
        }
        return count
    }
}
