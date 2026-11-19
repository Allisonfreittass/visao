import XCTest
@testable import VisaoKit

/// Ajustes > Modelo (docs/MODELO_LOCAL.md).
final class BrainTests: XCTestCase {
    func testDecodesWhatTheServerSends() throws {
        let raw = #"{"mode":"auto","local_model":"qwen3:4b","mac_online":true}"#
        let state = try JSONDecoder().decode(BrainState.self, from: Data(raw.utf8))
        XCTAssertEqual(state, BrainState(mode: .auto, localModel: "qwen3:4b", macOnline: true))
    }

    func testSaysWhatTheModeDoesWithTheMac() {
        XCTAssertTrue(BrainState(mode: .local, localModel: "qwen3:4b", macOnline: true).note.hasPrefix("O Mac oferece o qwen3:4b. Responde com o modelo do Mac"))
        XCTAssertTrue(BrainState(mode: .auto, localModel: nil, macOnline: true).note.contains("sem modelo local configurado"))
        XCTAssertTrue(BrainState(mode: .nuvem, localModel: nil, macOnline: false).note.contains("usa o modelo local"))
    }
}
