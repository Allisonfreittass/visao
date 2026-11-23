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

/// The panel offer card after a live quote (docs/PAINEIS.md).
final class PanelOfferTests: XCTestCase {
    func testAnOfferBecomesACardInItsConversation() throws {
        let json = #"{"id":"o","conversation_id":"c","message_id":"m","title":"Combo Santiago","goal_amount":"6000.00","currency":"BRL","status":"proposed","summary":"Deixar “Combo Santiago” no Início","created_at":"2026-11-15T13:14:00Z"}"#
        let offer = try APIDate.decoder.decode(PanelOffer.self, from: Data(json.utf8))
        let ask = PendingAsk(source: .panel(offer))
        XCTAssertEqual(ask.label, "Painel no Início")
        XCTAssertEqual(ask.conversationId, "c")
        XCTAssertTrue(ask.reportsInChat)
        XCTAssertTrue(VoiceRules.question(for: ask).contains("pode criar"))
    }

    func testTagsByOrigin() {
        func tag(_ origin: String) -> String? {
            Message(id: "m", role: .user, content: "x", createdAt: Date(), origin: origin).originTag
        }
        XCTAssertEqual(tag("share"), "compartilhado do iPhone")
        XCTAssertEqual(tag("initiative"), "puxou conversa")
        XCTAssertNil(tag("turn"))
        XCTAssertNil(tag("project"))
    }
}
