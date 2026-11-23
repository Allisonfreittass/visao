import XCTest
@testable import VisaoKit

/// The project is its chat (docs/ACOES.md, ADR-0021).
final class ProjectChatTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    func testProjectDecodesWithAndWithoutTheNewFields() throws {
        let new = try APIDate.decoder.decode(Project.self, from: Data(#"""
        {"id":"p1","name":"Viagem para o Chile","created_at":"2026-11-17T10:00:00Z","conversations":1,"pages":2,"files":0,
         "notes":"- Voo JetSMART, R$ 2.047\n- Hotel em Lastarria","notes_updated_at":"2026-11-17T11:00:00Z","panels":1}
        """#.utf8))
        XCTAssertEqual(new.panels, 1)
        XCTAssertNotNil(new.notesUpdatedAt)
        XCTAssertEqual(new.summary, "2 anotações · 1 painel · 2 páginas")

        let old = try APIDate.decoder.decode(Project.self, from: Data(#"{"id":"p2","name":"X","created_at":"2026-11-10T10:00:00Z"}"#.utf8))
        XCTAssertEqual(old.notes, "")
        XCTAssertEqual(old.panels, 0)
        XCTAssertNil(old.notesUpdatedAt)
        XCTAssertEqual(old.summary, "só o chat, por enquanto")
    }

    func testDetailDecodesItsPanelList() throws {
        let detail = try APIDate.decoder.decode(ProjectDetail.self, from: Data(#"""
        {"id":"p1","name":"Chile","notes":"- Voo","panels":1,"panel_list":[{"id":"x","title":"Combo Santiago","status":"active"}],
         "conversation_list":[],"page_list":[],"file_list":[]}
        """#.utf8))
        XCTAssertEqual(detail.panelList.map(\.title), ["Combo Santiago"])
        XCTAssertEqual(detail.summary, "1 anotação · 1 painel")
        XCTAssertEqual(detail.noteLines, ["Voo"])

        let old = try APIDate.decoder.decode(ProjectDetail.self, from: Data(#"{"id":"p1","name":"Chile"}"#.utf8))
        XCTAssertTrue(old.panelList.isEmpty)
        XCTAssertEqual(old.summary, "só o chat, por enquanto")
    }

    func testSummarySingularPluralAndEmpty() {
        XCTAssertEqual(ProjectText.summary(notes: "- a", panels: 1, pages: 1, files: 1), "1 anotação · 1 painel · 1 página · 1 arquivo")
        XCTAssertEqual(ProjectText.summary(notes: "- a\n- b\n- c\n- d", panels: 2, pages: 2, files: 3), "4 anotações · 2 painéis · 2 páginas · 3 arquivos")
        XCTAssertEqual(ProjectText.summary(notes: "\n  \n", panels: 0, pages: 0, files: 0), "só o chat, por enquanto")
    }

    func testNotesShowWithoutTheHyphen() {
        XCTAssertEqual(ProjectText.noteLines("- Voo JetSMART, R$ 2.047\n\n-Hotel\n  - Seguro viagem  \nsem hífen"), ["Voo JetSMART, R$ 2.047", "Hotel", "Seguro viagem", "sem hífen"])
    }

    func testPatchSendsOnlyTheFieldThatChanged() async throws {
        let transport = StubTransport()
        transport.on("PATCH", "/api/projects/p1", json: #"{"id":"p1","name":"Chile 2027","created_at":"2026-11-17T10:00:00Z","notes":"- a"}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))

        _ = try await api.updateProject(id: "p1", ProjectChange(notes: "- a"))
        XCTAssertEqual(try keys(transport.requests[0]), ["notes"])
        _ = try await api.renameProject(id: "p1", name: "Chile 2027")
        XCTAssertEqual(try keys(transport.requests[1]), ["name"])
    }

    func testTheProjectsChatRoute() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/conversations/project/p1", json: #"{"id":"c9","created_at":"2026-11-17T10:00:00Z","project_id":"p1","continuous":false}"#)
        let api = APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
        let chat = try await api.projectConversation(projectId: "p1")
        XCTAssertEqual(chat.id, "c9")
        XCTAssertEqual(chat.projectId, "p1")
    }

    func testMessagesAndPanelsCarryTheirProject() throws {
        let message = try APIDate.decoder.decode(Message.self, from: Data(#"{"id":"m","role":"assistant","content":"Anotei.","created_at":"2026-11-17T10:00:00Z","project_id":"p1"}"#.utf8))
        XCTAssertEqual(message.projectId, "p1")
        let plain = try APIDate.decoder.decode(Message.self, from: Data(#"{"id":"m","role":"assistant","content":"Oi","created_at":"2026-11-17T10:00:00Z"}"#.utf8))
        XCTAssertNil(plain.projectId)
        let panel = try APIDate.decoder.decode(LivePanel.self, from: Data(#"""
        {"id":"x","title":"T","status":"active","spec":{},"total":null,"goal":null,"goal_gap":null,"goal_words":null,"change":null,"items":[],"checked_at":null,"checked_today":false,"note":"","project_id":"p1"}
        """#.utf8))
        XCTAssertEqual(panel.projectId, "p1")
    }

    private func keys(_ request: URLRequest) throws -> [String] {
        let body = try XCTUnwrap(request.httpBody)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any]).keys.sorted()
    }
}
