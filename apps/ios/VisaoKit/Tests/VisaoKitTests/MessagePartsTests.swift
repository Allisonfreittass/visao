import XCTest
@testable import VisaoKit

/// A reply in 2 or 3 bubbles (ADR-0010): one message, one bubble per part.
final class MessagePartsTests: XCTestCase {
    private func decode(_ json: String) throws -> Message {
        try APIDate.decoder.decode(Message.self, from: Data(json.utf8))
    }

    func testAReplyInBubblesShowsEachPart() throws {
        let m = try decode(#"{"id":"m","role":"assistant","content":"Consigo ver.\n\nDe onde?","created_at":"2026-11-15T13:14:00Z","parts":["Consigo ver.","De onde?"]}"#)
        XCTAssertEqual(m.bubbles, ["Consigo ver.", "De onde?"])
        XCTAssertEqual(m.content, "Consigo ver.\n\nDe onde?")
    }

    func testWithoutPartsItIsOneBubble() throws {
        let m = try decode(#"{"id":"m","role":"assistant","content":"Só isso.","created_at":"2026-11-15T13:14:00Z"}"#)
        XCTAssertEqual(m.bubbles, ["Só isso."])
        XCTAssertNil(m.parts)
    }
}
