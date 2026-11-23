import XCTest
@testable import VisaoKit

final class HomeLinesTests: XCTestCase {
    func testStatusWithoutConnection() {
        XCTAssertEqual(HomeLines.status(online: false, macOnline: true, pendingCount: 1, panels: nil), "Sem conexão com o servidor.")
    }

    func testStatusFromData() {
        XCTAssertEqual(HomeLines.status(online: true, macOnline: true, pendingCount: 0, panels: []), "Sistemas prontos · Mac conectado")
        XCTAssertEqual(HomeLines.status(online: true, macOnline: false, pendingCount: 2, panels: nil), "Sistemas prontos · Sem conexão com o Mac · 2 pedidos esperando você")
        XCTAssertEqual(HomeLines.status(online: true, macOnline: nil, pendingCount: 0, panels: nil), "Sistemas prontos")
    }

    func testWatchCountIsNilWithoutPanels() {
        XCTAssertNil(HomeLines.watchCount(nil))
        XCTAssertNil(HomeLines.watchCount([]))
    }
}
