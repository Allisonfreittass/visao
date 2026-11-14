import Foundation

// The voice call's rules (docs/VOICE.md), as apps/web/src/voice/approval.ts and
// speech/speakable.ts decide them. Fixed rules, never a model: a misheard or mixed answer decides
// nothing and goes on as an ordinary message.

public enum Verdict: Equatable, Sendable {
    case approve
    case reject
}

public enum VoiceRules {
    /// How long after the question a spoken yes still counts.
    public static let answerWindow: TimeInterval = 3 * 60

    /// Lowercase, no accents, no punctuation, single spaces.
    static func fold(_ text: String) -> String {
        let plain = text.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "pt_BR")).lowercased()
        let letters = plain.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) && $0.isASCII ? Character($0) : " " }
        return String(letters).split(separator: " ").joined(separator: " ")
    }

    private static let approve = #"\b(pode (mandar|enviar|rodar|marcar|agendar|fazer|executar|seguir|criar)|(manda|envia|roda|marca|agenda) (sim|ai|ja|logo)|aprovo|aprovado|confirmo|confirmado|autorizo|autorizado|pode sim|sim pode)\b"#
    private static let reject = #"\b(nao|cancela|cancelar|cancele|recusa|recuso|recusado|deixa pra la|nem pensar|negativo|espera|espere|pera|para|pare)\b"#
    private static let shortYes = #"^(sim|claro|isso|ok|okay|beleza|pode|pode ser|com certeza|manda|envia|bora)( (sim|pode|por favor|obrigado))?$"#

    /// What a spoken answer to "posso fazer?" means; nil when it is not a clear yes or no.
    public static func verdict(_ text: String) -> Verdict? {
        let said = fold(text)
        guard !said.isEmpty else { return nil }
        let words = said.split(separator: " ").count
        let no = said.range(of: reject, options: .regularExpression) != nil
        let yes = said.range(of: approve, options: .regularExpression) != nil
            || (words <= 4 && said.range(of: shortYes, options: .regularExpression) != nil)
        if yes && no { return nil } // "não, pode mandar": mixed, decide nothing
        if yes { return .approve }
        if no && words <= 6 { return .reject }
        return nil
    }

    /// What a reply sounds like out loud: code, links and Markdown marks are for the screen.
    public static func speakable(_ text: String) -> String {
        var spoken = text.replacingOccurrences(of: #"```[\s\S]*?(```|$)"#, with: " Deixei o código na tela. ", options: .regularExpression)
        let steps: [(String, String)] = [
            (#"\[([^\]]+)\]\((https?://[^\s)]+)\)"#, "$1"),
            (#"https?://\S+"#, "o link na tela"),
            (#"`([^`]+)`"#, "$1"),
            (#"\*\*([^*]+)\*\*"#, "$1"),
        ]
        for (pattern, template) in steps {
            spoken = spoken.replacingOccurrences(of: pattern, with: template, options: .regularExpression)
        }
        spoken = spoken
            .replacingOccurrences(of: #"(?m)^#{1,6}\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^\s*[-*]\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"[ \t]+"#, with: " ", options: .regularExpression)
            .replacingOccurrences(of: #" *\n *"#, with: "\n", options: .regularExpression)
            .replacingOccurrences(of: #"\n{2,}"#, with: "\n", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        // Two code blocks in a row would say it twice.
        return spoken
            .replacingOccurrences(of: #"(Deixei o código na tela\.\s*)+"#, with: "Deixei o código na tela. ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func clip(_ text: String, _ limit: Int) -> String {
        text.count > limit ? String(text.prefix(limit - 1)).trimmingCharacters(in: .whitespaces) + "…" : text
    }

    /// Read aloud before asking: exactly what it is about to do and how to answer.
    public static func question(for ask: PendingAsk) -> String {
        switch ask.source {
        case .google(let action) where action.kind == "send_email":
            return "Preparei um email para \(action.payload.to ?? "o destinatário"), assunto: \(clip(action.payload.subject ?? action.summary, 90)). Para mandar, diga \"pode mandar\". Para cancelar, diga \"não\"."
        case .google(let action):
            return "Preparei um evento na sua agenda: \(clip(action.payload.title ?? action.summary, 90)). Para marcar, diga \"pode marcar\". Para cancelar, diga \"não\"."
        case .arm(let task):
            return "Montei um pedido para o Mac, no projeto \(task.project): \(clip(task.prompt, 140)). Para rodar, diga \"pode rodar\". Para cancelar, diga \"não\"."
        }
    }

    /// Said only after the server accepted it.
    public static func done(for ask: PendingAsk, verdict: Verdict, accepted: Bool) -> String {
        guard accepted else { return "Não consegui agora. Ficou esperando você na tela." }
        guard verdict == .approve else { return "Tudo bem, não fiz." }
        switch ask.source {
        case .google(let action) where action.kind == "send_email": return "Pronto, mandei o email."
        case .google: return "Pronto, marquei na agenda."
        case .arm: return "Pronto, mandei para o Mac. Aviso quando terminar."
        }
    }
}

/// Which asks were read aloud in this call and which one a spoken answer would decide.
public struct VoiceApprovalSession: Sendable {
    public private(set) var asked: (ask: PendingAsk, at: Date)?
    private var announced: Set<String> = []

    public init() {}

    /// The next ask to read aloud, once each per call; marks it as the one waiting for an answer.
    public mutating func nextToAnnounce(from asks: [PendingAsk], now: Date = Date()) -> PendingAsk? {
        guard let next = asks.first(where: { !announced.contains($0.id) }) else { return nil }
        announced.insert(next.id)
        asked = (next, now)
        return next
    }

    /// What a heard phrase decides, if anything: only for the ask just read, still waiting, within
    /// three minutes. Anything else (nil) goes on as a message.
    public mutating func interpret(_ heard: String, stillWaiting asks: [PendingAsk], now: Date = Date()) -> (PendingAsk, Verdict)? {
        guard let asked, asks.contains(where: { $0.id == asked.ask.id }),
              now.timeIntervalSince(asked.at) < VoiceRules.answerWindow,
              let verdict = VoiceRules.verdict(heard) else { return nil }
        self.asked = nil
        return (asked.ask, verdict)
    }
}

/// The server's own voice (Kokoro, docs/decisions/0004): there when the server has the model
/// installed and a voice approved.
public struct ServerVoiceStatus: Decodable, Sendable {
    public let enabled: Bool
    public let currentVoice: String?

    enum CodingKeys: String, CodingKey {
        case enabled
        case currentVoice = "current_voice"
    }
}

extension APIClient {
    public func voiceStatus() async throws -> ServerVoiceStatus { try await request("/voice/status") }

    /// A reply cut into speakable sentences, so the first plays while the rest is synthesized.
    public func sentences(_ text: String) async throws -> [String] {
        let body: [String: [String]] = try await json("/voice/sentences", method: "POST", body: ["text": text])
        return body["sentences"] ?? []
    }

    /// One sentence as WAV audio, in the voice it chose.
    public func tts(_ text: String) async throws -> Data {
        try await raw("/voice/tts", method: "POST", body: try JSONEncoder().encode(["text": text]), contentType: "application/json")
    }
}
