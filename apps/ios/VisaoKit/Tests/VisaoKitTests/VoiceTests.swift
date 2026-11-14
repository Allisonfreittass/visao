import XCTest
@testable import VisaoKit

/// The same cases as apps/web/src/voice/approval.test.ts and speech/speakable.test.ts.
final class VoiceVerdictTests: XCTestCase {
    func testClearYesApproves() {
        for said in ["Pode mandar", "pode mandar sim", "Sim, pode.", "sim", "Aprovo.", "confirmo", "pode rodar", "Manda aí", "Pode marcar na agenda", "Ok", "Beleza, pode"] {
            XCTAssertEqual(VoiceRules.verdict(said), .approve, said)
        }
    }

    func testClearNoRejects() {
        for said in ["não", "Não, cancela", "cancela isso", "espera", "deixa pra lá", "Recuso", "Negativo"] {
            XCTAssertEqual(VoiceRules.verdict(said), .reject, said)
        }
    }

    func testUnclearDecidesNothing() {
        for said in [
            "não, pode mandar", // mixed
            "sim mas antes muda o assunto para reunião de sexta", // long: a request, not a yes
            "qual é o assunto mesmo?",
            "manda o email pro João também e copia a Maria e depois me lembra amanhã cedo",
            "",
            "hmm",
            "não sei se eu quero que você mande isso agora para ele", // a long no is a message
        ] {
            XCTAssertNil(VoiceRules.verdict(said), said)
        }
    }

    func testAccentsAndPunctuationDoNotMatter() {
        XCTAssertEqual(VoiceRules.verdict("NÃO!!!"), .reject)
        XCTAssertEqual(VoiceRules.verdict("pode... mandar"), .approve)
        XCTAssertEqual(VoiceRules.fold("Olá, Mundo! É isso."), "ola mundo e isso")
    }
}

final class SpeakableTests: XCTestCase {
    func testCodeIsOnScreenNotRead() {
        let text = "Assim:\n\n```ts\nconst a = 1;\n```\n\n```py\nb = 2\n```\n\nPronto."
        XCTAssertEqual(VoiceRules.speakable(text), "Assim:\nDeixei o código na tela. Pronto.")
    }

    func testLinksAndMarks() {
        XCTAssertEqual(VoiceRules.speakable("Veja **isto** em [MDN](https://developer.mozilla.org) e `fetch`."), "Veja isto em MDN e fetch.")
        XCTAssertEqual(VoiceRules.speakable("Fonte: https://pt.wikipedia.org/wiki/X"), "Fonte: o link na tela")
        XCTAssertEqual(VoiceRules.speakable("# Título\n- um\n- dois"), "Título\num\ndois")
    }

    func testUnclosedCodeStillHidden() {
        XCTAssertEqual(VoiceRules.speakable("Olha:\n```swift\nlet x = 1"), "Olha:\nDeixei o código na tela.")
    }
}

final class VoiceApprovalTests: XCTestCase {
    private func email() throws -> PendingAsk {
        let json = #"{"id":"g1","kind":"send_email","summary":"Email para joao@exemplo.com: Reunião","payload":{"to":"joao@exemplo.com","subject":"Reunião"},"status":"pending","conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"}"#
        return PendingAsk(source: .google(try APIDate.decoder.decode(GoogleAction.self, from: Data(json.utf8))))
    }

    private func mac() throws -> PendingAsk {
        let json = #"{"id":"t1","project":"visao","prompt":"rode os testes","status":"proposed","requested_by":"agent","conversation_id":"c1","created_at":"2026-11-13T12:00:00Z"}"#
        return PendingAsk(source: .arm(try APIDate.decoder.decode(ArmTask.self, from: Data(json.utf8))))
    }

    func testReadsWhoWhatAndHowToAnswer() throws {
        let question = VoiceRules.question(for: try email())
        XCTAssertTrue(question.contains("joao@exemplo.com"))
        XCTAssertTrue(question.contains("\"pode mandar\""))
        XCTAssertTrue(VoiceRules.question(for: try mac()).contains("projeto visao: rode os testes"))
    }

    func testDoneOnlyAfterTheServerAccepted() throws {
        let ask = try email()
        XCTAssertEqual(VoiceRules.done(for: ask, verdict: .approve, accepted: true), "Pronto, mandei o email.")
        XCTAssertEqual(VoiceRules.done(for: ask, verdict: .approve, accepted: false), "Não consegui agora. Ficou esperando você na tela.")
        XCTAssertEqual(VoiceRules.done(for: ask, verdict: .reject, accepted: true), "Tudo bem, não fiz.")
    }

    func testEachAskIsReadOnceAndAnsweredOnce() throws {
        var session = VoiceApprovalSession()
        let asks = [try email(), try mac()]
        let start = Date()

        XCTAssertEqual(session.nextToAnnounce(from: asks, now: start)?.id, "g1")
        XCTAssertNil(session.interpret("qual o assunto?", stillWaiting: asks, now: start), "not an answer: goes as a message")
        let decided = session.interpret("pode mandar", stillWaiting: asks, now: start.addingTimeInterval(10))
        XCTAssertEqual(decided?.0.id, "g1")
        XCTAssertEqual(decided?.1, .approve)
        XCTAssertNil(session.interpret("sim", stillWaiting: asks, now: start.addingTimeInterval(11)), "already decided")

        XCTAssertEqual(session.nextToAnnounce(from: asks, now: start)?.id, "t1")
        XCTAssertNil(session.nextToAnnounce(from: asks, now: start), "never read twice")
    }

    func testAnswerExpiresAfterThreeMinutesOrWhenDecidedElsewhere() throws {
        var session = VoiceApprovalSession()
        let asks = [try email()]
        let start = Date()
        _ = session.nextToAnnounce(from: asks, now: start)
        XCTAssertNil(session.interpret("pode mandar", stillWaiting: asks, now: start.addingTimeInterval(181)))

        var other = VoiceApprovalSession()
        _ = other.nextToAnnounce(from: asks, now: start)
        XCTAssertNil(other.interpret("pode mandar", stillWaiting: [], now: start.addingTimeInterval(5)), "tapped on screen meanwhile")
    }
}

@MainActor
final class SpokenMessageTests: XCTestCase {
    func testWhatIsSaidInACallGoesAsVoice() async throws {
        let transport = StubTransport()
        transport.on("POST", "/api/conversations/c1/messages", json: Fixture.turn(user: "oi", reply: "olá"))
        let store = ChatStore(api: APIClient(baseURL: URL(string: "https://visao.test/api")!, transport: transport, tokens: MemoryTokenStore(token: "t")), conversationId: "c1")

        store.send("oi", spoken: true)
        let clock = ContinuousClock()
        let deadline = clock.now + .seconds(3)
        while store.messages.count < 2, clock.now < deadline { try await Task.sleep(for: .milliseconds(5)) }

        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: transport.requests.first { $0.httpMethod == "POST" }?.httpBody ?? Data()) as? [String: Any])
        XCTAssertEqual(body["modality"] as? String, "voice")
    }
}

final class ServerVoiceTests: XCTestCase {
    func testStatusSentencesAndAudio() async throws {
        let transport = StubTransport()
        transport.on("GET", "/api/voice/status", json: #"{"enabled":true,"listening":false,"current_voice":"kokoro-dora","source":"chosen","approved":[],"history":[]}"#)
        transport.on("POST", "/api/voice/sentences", json: #"{"sentences":["Oi.","Tudo bem?"]}"#)
        transport.on("POST", "/api/voice/tts", json: "RIFF")
        let api = APIClient(baseURL: URL(string: "https://visao.test/api")!, transport: transport, tokens: MemoryTokenStore(token: "t"))

        let status = try await api.voiceStatus()
        XCTAssertTrue(status.enabled)
        XCTAssertEqual(status.currentVoice, "kokoro-dora")
        let parts = try await api.sentences("Oi. Tudo bem?")
        XCTAssertEqual(parts, ["Oi.", "Tudo bem?"])
        let audio = try await api.tts("Oi.")
        XCTAssertEqual(String(decoding: audio, as: UTF8.self), "RIFF")
        let body = try XCTUnwrap(transport.requests.last?.httpBody)
        XCTAssertEqual(String(decoding: body, as: UTF8.self), #"{"text":"Oi."}"#)
    }
}
