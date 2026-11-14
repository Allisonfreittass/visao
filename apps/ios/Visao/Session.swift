import Foundation
import Observation
import VisaoKit

/// Who is logged in, against which server, and the conversation list.
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
    private(set) var conversations: [Conversation] = []
    private(set) var loadingList = false
    var listError: String?

    private let tokens: TokenStore
    private static let serverKey = "serverURL"

    init() {
        tokens = KeychainTokenStore(service: (Bundle.main.bundleIdentifier ?? "visao") + ".auth")
        let url = Session.savedServer ?? Session.configuredServer
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
    static var configuredServer: URL {
        let raw = Bundle.main.object(forInfoDictionaryKey: "VisaoAPIBaseURL") as? String ?? ""
        return URL(string: raw) ?? URL(string: "https://visao.example.com/api")!
    }

    /// The address typed on the login screen, when it differs from the configured one. It is not
    /// a secret, so UserDefaults is fine; the token stays in the Keychain.
    static var savedServer: URL? {
        UserDefaults.standard.string(forKey: serverKey).flatMap(URL.init(string:))
    }

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
        UserDefaults.standard.set(url == Session.configuredServer ? nil : url.absoluteString, forKey: Session.serverKey)
        loggedIn = true
    }

    func logout() {
        api.logout()
        loggedIn = false
        conversations = []
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
            async let list = api.conversations()
            async let status = api.status()
            conversations = try await list
            agentName = (try? await status)?.identity?.chosenName
            listError = nil
            pending.onError = { [weak self] in self?.handle($0) }
            await pending.refresh()
        } catch {
            listError = (error as? LocalizedError)?.errorDescription
            handle(error)
        }
    }

    func added(_ conversation: Conversation) {
        conversations.removeAll { $0.id == conversation.id }
        conversations.insert(conversation, at: 0)
    }

    var speakerName: String { agentName ?? "Ele" }
}
