import XCTest
@testable import VisaoKit

/// Ajustes > Autonomia > Resumo da manhã (docs/RESUMO_DA_MANHA.md).
final class MorningBriefingTests: XCTestCase {
    private let base = URL(string: "https://visao.test/api")!

    private func settings(permissions: String) async throws -> ServerSettings {
        let transport = StubTransport()
        transport.on("GET", "/api/memory/settings", json: #"{"enabled":true}"#)
        transport.on("GET", "/api/system/autonomy", json: #"{"paused":false}"#)
        transport.on("GET", "/api/autonomy/permissions", json: permissions)
        return try await api(transport).serverSettings()
    }

    func testTheSwitchReadsTheServerAndIsOnByDefault() async throws {
        let off = try await settings(permissions: #"{"auto_research":true,"morning_briefing":false}"#)
        XCTAssertFalse(off.morningBriefing)
        XCTAssertTrue(off.autoResearch)
        let older = try await settings(permissions: #"{"auto_research":false}"#)
        XCTAssertTrue(older.morningBriefing, "missing means the default, on")
    }

    func testSavingSendsOnlyThatField() async throws {
        let transport = StubTransport()
        transport.on("PUT", "/api/autonomy/permissions", json: #"{"auto_research":true,"morning_briefing":false}"#)
        let saved = try await api(transport).setMorningBriefing(false)
        XCTAssertFalse(saved)
        let body = try XCTUnwrap(transport.requests.last?.httpBody)
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
        XCTAssertEqual(sent.keys.sorted(), ["morning_briefing"], "auto_research is never sent, so it is never turned off by accident")
        XCTAssertEqual(sent["morning_briefing"] as? Bool, false)
    }

    func testSendNowSaysWhetherItWasQueued() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/autonomy/briefing", status: 202, json: #"{"queued":true}"#)
        let queued = try await api(transport).briefingNow()
        XCTAssertTrue(queued)
        transport.on("POST", "/api/autonomy/briefing", status: 202, json: #"{"queued":false}"#)
        let paused = try await api(transport).briefingNow()
        XCTAssertFalse(paused)
    }

    private func api(_ transport: StubTransport) -> APIClient {
        APIClient(baseURL: base, transport: transport, tokens: MemoryTokenStore(token: "t"))
    }
}
