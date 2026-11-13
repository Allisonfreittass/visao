import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import VisaoKit

final class AttachmentAPITests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    func testUploadIsMultipartWithTheFile() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments", status: 201, json: #"{"id":"f1","kind":"document","filename":"notas.md","media_type":"text/markdown","size_bytes":5,"readable":true}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let attachment = try await api.uploadAttachment(data: Data("olá!".utf8), filename: "no\"tas.md", mimeType: "text/markdown")

        XCTAssertEqual(attachment.readable, true)
        let request = try XCTUnwrap(transport.requests.first)
        let type = try XCTUnwrap(request.value(forHTTPHeaderField: "Content-Type"))
        XCTAssertTrue(type.hasPrefix("multipart/form-data; boundary="))
        let boundary = String(type.dropFirst("multipart/form-data; boundary=".count))
        let body = String(decoding: request.httpBody ?? Data(), as: UTF8.self)
        XCTAssertTrue(body.hasPrefix("--\(boundary)\r\n"))
        XCTAssertTrue(body.contains("Content-Disposition: form-data; name=\"file\"; filename=\"no'tas.md\"\r\n"), "a quote never closes the header early")
        XCTAssertTrue(body.contains("Content-Type: text/markdown\r\n\r\nolá!\r\n--\(boundary)--\r\n"))
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer t")
    }

    func testTooLargeUploadSaysWhy() async {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments", status: 413, json: #"{"detail":"Arquivo grande demais (máximo 10 MB)."}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        await XCTAssertThrowsAPIError(try await api.uploadAttachment(data: Data(), filename: "x.pdf", mimeType: "application/pdf"), status: 413, message: "Arquivo grande demais (máximo 10 MB).")
    }

    func testDownloadAndPages() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/attachments/f1", json: "bytes")
        transport.on("GET", "/api/artifacts/p1", json: #"{"id":"p1","title":"Roteiro","status":"ready","path":"/p/tok","error":null,"conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"}"#)
        transport.on("DELETE", "/api/artifacts/p1") { _ in (204, "") }
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let bytes = try await api.attachmentData(id: "f1")
        XCTAssertEqual(String(decoding: bytes, as: UTF8.self), "bytes")
        let page = try await api.artifact(id: "p1")
        XCTAssertEqual(api.pageURL(path: try XCTUnwrap(page.path)).absoluteString, "https://visao.test/api/p/tok")
        try await api.deleteArtifact(id: "p1")
        XCTAssertEqual(transport.count("DELETE", "/api/artifacts/p1"), 1)
    }
}

final class ImagePreparationTests: XCTestCase {
    func testTargetSizeOnlyShrinks() {
        XCTAssertTrue(ImagePreparation.targetSize(width: 4032, height: 3024) == (1568, 1176))
        XCTAssertTrue(ImagePreparation.targetSize(width: 3024, height: 4032) == (1176, 1568))
        XCTAssertTrue(ImagePreparation.targetSize(width: 800, height: 600) == (800, 600))
    }

    func testBigPhotoBecomesSmallJPEG() throws {
        let png = try image(width: 3000, height: 2000, type: .png)
        let prepared = try ImagePreparation.prepare(png, filename: "IMG_0001.HEIC")

        XCTAssertEqual(prepared.mimeType, "image/jpeg")
        XCTAssertEqual(prepared.filename, "IMG_0001.jpg")
        let size = try dimensions(prepared.data)
        XCTAssertEqual(max(size.0, size.1), 1568)
        XCTAssertEqual(size.0, 1568)
    }

    func testSmallPNGGoesAsItIs() throws {
        let png = try image(width: 400, height: 300, type: .png)
        let prepared = try ImagePreparation.prepare(png, filename: "print.png")

        XCTAssertEqual(prepared, PreparedFile(data: png, filename: "print.png", mimeType: "image/png"))
    }

    func testHEICIsAlwaysConverted() throws {
        guard let heic = try? image(width: 400, height: 300, type: .heic) else { throw XCTSkip("no HEIC encoder here") }
        let prepared = try ImagePreparation.prepare(heic, filename: "IMG_0002.HEIC")
        XCTAssertEqual(prepared.mimeType, "image/jpeg", "the server does not take HEIC")
    }

    func testNotAnImage() {
        XCTAssertThrowsError(try ImagePreparation.prepare(Data("%PDF-1.7".utf8), filename: "a.jpg")) { error in
            XCTAssertEqual(error as? AttachmentError, .unreadableImage)
        }
    }

    func testSizesReadLikeTheWeb() {
        XCTAssertEqual(AttachmentRules.formatSize(512), "512 B")
        XCTAssertEqual(AttachmentRules.formatSize(120 * 1024), "120 KB")
        XCTAssertEqual(AttachmentRules.formatSize(Int(1.4 * 1024 * 1024)), "1,4 MB")
    }

    private func image(width: Int, height: Int, type: UTType) throws -> Data {
        let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.setFillColor(CGColor(red: 0.3, green: 0.4, blue: 0.4, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        let out = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(out, type.identifier as CFString, 1, nil) else { throw AttachmentError.unreadableImage }
        CGImageDestinationAddImage(destination, context.makeImage()!, nil)
        guard CGImageDestinationFinalize(destination) else { throw AttachmentError.unreadableImage }
        return out as Data
    }

    private func dimensions(_ data: Data) throws -> (Int, Int) {
        let source = try XCTUnwrap(CGImageSourceCreateWithData(data as CFData, nil))
        let props = try XCTUnwrap(CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any])
        return (props[kCGImagePropertyPixelWidth] as? Int ?? 0, props[kCGImagePropertyPixelHeight] as? Int ?? 0)
    }
}

@MainActor
final class DraftAndPagesTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    func testDraftUploadsAndKeepsTheLimit() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments", status: 201, json: #"{"id":"f1","kind":"document","filename":"a.md","media_type":"text/markdown","size_bytes":1}"#)
        let draft = AttachmentDraft(api: APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t")))

        for i in 0..<6 { draft.addFile(Data("x".utf8), filename: "a\(i).md") }
        XCTAssertEqual(draft.items.count, 4, "at most 4 per message")
        try await until { !draft.isUploading }
        XCTAssertEqual(draft.ready.count, 4)
        draft.clear()
        XCTAssertEqual(draft.room, 4)
    }

    func testDraftShowsWhyAFileFailed() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/attachments", status: 422, json: #"{"detail":"PDF com senha não dá para ler."}"#)
        let draft = AttachmentDraft(api: APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t")))

        draft.addFile(Data("%PDF".utf8), filename: "trancado.pdf")
        try await until { !draft.isUploading }
        XCTAssertEqual(draft.items.first?.status, .failed("PDF com senha não dá para ler."))
        XCTAssertTrue(draft.ready.isEmpty)
    }

    func testPhotoAloneIsAMessageAndQueuedFilesGoTogether() async throws {
        let gate = Gate()
        let transport = StubTransport()
        let path = "/api/conversations/c1/messages"
        transport.on("POST", path) { _ in
            await gate.wait()
            return (200, Fixture.turn(user: "", reply: "Vi a foto"))
        }
        let store = ChatStore(api: APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t")), conversationId: "c1")
        let photo = Attachment(id: "f1", kind: "image", filename: "a.jpg", mediaType: "image/jpeg", sizeBytes: 10, readable: nil)
        let doc = Attachment(id: "f2", kind: "document", filename: "b.pdf", mediaType: "application/pdf", sizeBytes: 10, readable: true)

        store.send("", attachments: [photo])
        try await until { store.sending }
        XCTAssertEqual(store.messages.first?.attachments, [photo])
        store.send("e este", attachments: [doc])
        transport.on("POST", path) { _ in (200, Fixture.turn(user: "e este", reply: "ok", userId: "u2", replyId: "a2")) }
        await gate.open()
        try await until { transport.count("POST", path) == 2 && !store.sending }

        let sends = transport.requests.filter { $0.httpMethod == "POST" && $0.url?.path == path }
        let first = try JSONSerialization.jsonObject(with: sends[0].httpBody ?? Data()) as? [String: Any]
        XCTAssertEqual(first?["content"] as? String, "")
        XCTAssertEqual(first?["attachment_ids"] as? [String], ["f1"])
        let second = try JSONSerialization.jsonObject(with: sends[1].httpBody ?? Data()) as? [String: Any]
        XCTAssertEqual(second?["attachment_ids"] as? [String], ["f2"])
    }

    func testPendingPageTurnsReady() async throws {
        let transport = StubTransport()
        let pending = #"{"id":"p1","title":"Roteiro","status":"pending","path":null,"error":null,"conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"}"#
        let reply = #"{"id":"a1","role":"assistant","content":"Vou montar","created_at":"2026-11-13T12:00:00Z","artifact":\#(pending)}"#
        transport.on("GET", "/api/conversations/c1/messages", json: "[\(reply)]")
        transport.on("GET", "/api/artifacts/p1", json: pending)
        let store = ChatStore(api: APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t")), conversationId: "c1", artifactInterval: .milliseconds(20))

        await store.load()
        XCTAssertEqual(store.messages.first?.artifact?.status, "pending")
        transport.on("GET", "/api/artifacts/p1", json: pending.replacingOccurrences(of: "\"pending\",\"path\":null", with: "\"ready\",\"path\":\"/p/tok\""))
        try await until { store.messages.first?.artifact?.status == "ready" }
        XCTAssertEqual(store.messages.first?.artifact?.path, "/p/tok")

        transport.on("DELETE", "/api/artifacts/p1") { _ in (204, "") }
        await store.deleteArtifact(try XCTUnwrap(store.messages.first?.artifact))
        XCTAssertNil(store.messages.first?.artifact)
    }

    private func until(timeout: Duration = .seconds(5), _ condition: () -> Bool) async throws {
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

final class SkyLookTests: XCTestCase {
    func testNightAtMidnightDayAtNoon() {
        XCTAssertEqual(SkyLook.at(hour: 0).night, 1)
        XCTAssertEqual(SkyLook.at(hour: 12).night, 0)
        XCTAssertGreaterThan(SkyLook.at(hour: 23.9).night, 0.9)
        XCTAssertTrue(SkyLook.at(hour: 22).isNight)
        XCTAssertFalse(SkyLook.at(hour: 10).isNight)
    }

    func testLightHighAtNoonLowAtDawn() {
        XCTAssertGreaterThan(SkyLook.at(hour: 12).sun.y, 0.85)
        XCTAssertLessThan(SkyLook.at(hour: 6.2).sun.y, 0.65)
    }

    func testNearestPinesStayDark() {
        for h in 0..<24 {
            XCTAssertLessThanOrEqual(SkyLook.at(hour: Double(h)).tree.max(), 0.21)
        }
    }

    func testBlendsWithoutJumpsAndWraps() {
        var h = 0.0
        while h < 24 {
            let a = SkyLook.at(hour: h), b = SkyLook.at(hour: h + 0.25)
            let d: SkyLook.RGB = a.top - b.top
            XCTAssertLessThan(max(abs(d.x), abs(d.y), abs(d.z)), 0.35)
            XCTAssertLessThan(abs(a.night - b.night), 0.5)
            h += 0.25
        }
        XCTAssertEqual(SkyLook.at(hour: 25), SkyLook.at(hour: 1))
        XCTAssertEqual(SkyLook.at(hour: -1), SkyLook.at(hour: 23))
    }

    func testSameColorsAsTheWebAtAKeyHour() {
        // 9h is a key hour in sky.ts: #e4e9eb at the top.
        let look = SkyLook.at(hour: 9)
        XCTAssertEqual(look.top.x, Double(0xe4) / 255, accuracy: 1e-9)
        XCTAssertEqual(look.cloud, 0.95, accuracy: 1e-9)
    }
}
