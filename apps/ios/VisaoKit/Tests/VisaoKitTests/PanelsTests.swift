import XCTest
@testable import VisaoKit

/// Live panels on Início (docs/PAINEIS.md): the card reads what the server computed.
final class PanelsTests: XCTestCase {
    private let json = #"""
    [{"id":"p","kind":"travel_quote","title":"Combo Santiago","status":"active","spec":{"travelers":2,"destination":"Santiago"},
      "total":"5945.00","goal":"6000.00","goal_gap":"-55.00","goal_words":"R$ 55 abaixo da meta de R$ 6.000","change":"-610.00",
      "items":[{"kind":"flight","provider":"LATAM","where":"CNF → SCL","dates":"14–21 ago","connections":1,"price":"4390","price_basis":"total","cost":"4390","currency":"BRL","site":"google.com","url":"https://www.google.com/travel/flights","read_at":"2026-11-15T13:14:00Z"}],
      "checked_at":"2026-11-15T13:14:00Z","checked_today":false,"next_check_at":null,"note":"","conversation_id":null,"created_at":"2026-11-15T13:00:00Z"}]
    """#

    func testACardDecodesWithTheServersNumbers() throws {
        let panels = try APIDate.decoder.decode([LivePanel].self, from: Data(json.utf8))
        let panel = try XCTUnwrap(panels.first)
        XCTAssertTrue(panel.isBelowGoal)
        XCTAssertEqual(panel.changeValue, -610)
        XCTAssertEqual(panel.items.first?.connections, 1)
        XCTAssertEqual(PanelText.brl(panel.total), "R$ 5.945")
        XCTAssertEqual(PanelText.brl("4250.50"), "R$ 4.250,50")
        XCTAssertTrue(PanelText.checked(panel).hasSuffix("· não conferido hoje"))
    }
}
