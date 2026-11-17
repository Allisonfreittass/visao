import Foundation
import Observation
import VisaoKit

/// Who is logged in, against which server, and which conversation Chat opens.
@MainActor
@Observable
final class Session {
    private(set) var api: APIClient {
        didSet {
            loader = AttachmentLoader(api: api)
            pending = Session.makePending(api)
        }
    }
    /// Emails, events and Mac work waiting for a yes (stage 3).
    private(set) var pending: PendingStore
    /// Photos and files of the messages, downloaded once per session.
    private(set) var loader: AttachmentLoader
    private(set) var loggedIn: Bool
    /// The name it chose, or nil while it has none: the app never calls it "VISÃO".
    private(set) var agentName: String?
    /// The continuous conversation (docs/CONVERSA_CONTINUA.md): Chat always opens it. There is no
    /// list of conversations; separate ones only live inside a project.
    private(set) var continuousId: String?
    private(set) var loadingList = false
    var listError: String?

    private let tokens: TokenStore
    /// The App Group and Keychain group shared with the share extension (docs/COMPARTILHAR.md).
    static let shared = SharedConfig.main

    init() {
        // The token saved before 17/11/2026 moves into the shared group on this first read.
        let store = Session.shared.tokens()
        store.migrateIfNeeded()
        tokens = store
        let url = Session.shared.server
        let client = APIClient(baseURL: url, tokens: tokens)
        api = client
        loader = AttachmentLoader(api: client)
        pending = Session.makePending(client)
        loggedIn = tokens.token != nil
        pending.onError = { [weak self] in self?.handle($0) }
    }

    private static func makePending(_ api: APIClient) -> PendingStore {
        PendingStore(api: api)
    }

    /// From Config/Local.xcconfig (VISAO_API_BASE_URL), through Info.plist.
    static var configuredServer: URL { shared.configuredServer }

    var serverAddress: String { api.baseURL.absoluteString }

    func login(server: String, email: String, password: String) async throws {
        let trimmed = server.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), let scheme = url.scheme, ["http", "https"].contains(scheme), url.host != nil else {
            throw APIError(status: 0, message: "Endereço do servidor inválido")
        }
        if url != api.baseURL {
            api = APIClient(baseURL: url, tokens: tokens)
        }
        try await api.login(email: email.trimmingCharacters(in: .whitespaces), password: password)
        // Not a secret: the group's defaults, so the share extension knows where to send.
        Session.shared.saveServer(url)
        loggedIn = true
    }

    func logout() {
        api.logout()
        loggedIn = false
        continuousId = nil
        agentName = nil
    }

    /// A 401 anywhere sends you back to the login screen.
    func handle(_ error: Error) {
        if (error as? APIError)?.isUnauthorized == true { logout() }
    }

    func loadHome() async {
        loadingList = true
        defer { loadingList = false }
        do {
            async let continuous = api.continuousConversation()
            async let status = api.status()
            continuousId = try await continuous.id
            agentName = (try? await status)?.identity?.chosenName
            listError = nil
            pending.onError = { [weak self] in self?.handle($0) }
            await pending.refresh()
        } catch {
            listError = (error as? LocalizedError)?.errorDescription
            handle(error)
        }
    }

    /// Text Início puts in the chat's message box (a suggestion, "Criar um novo painel").
    var chatDraft: String?

    /// The first message made the continuous conversation (it was not there yet).
    func added(_ conversation: Conversation) {
        if conversation.continuous || conversation.projectId == nil { continuousId = conversation.id }
    }

    var speakerName: String { agentName ?? "Ele" }
}
