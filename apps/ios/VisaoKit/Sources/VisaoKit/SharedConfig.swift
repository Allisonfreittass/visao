import Foundation

/// What the app and the share extension have in common (docs/COMPARTILHAR.md): the App Group,
/// whose defaults hold the server address, and the Keychain group that holds the token. The
/// names come from each target's Info.plist, filled from the build settings.
public struct SharedConfig: Sendable {
    public let appGroup: String?
    public let keychainGroup: String?
    /// The Keychain service of the token; the same name the app used before the group existed.
    public let tokenService: String
    public let configuredServer: URL

    static let serverKey = "serverURL"

    public init(info: [String: Any]) {
        appGroup = Self.value(info["VisaoAppGroup"])
        keychainGroup = Self.value(info["VisaoKeychainGroup"])
        tokenService = Self.value(info["VisaoTokenService"]) ?? ((Self.value(info["CFBundleIdentifier"]) ?? "visao") + ".auth")
        configuredServer = Self.value(info["VisaoAPIBaseURL"]).flatMap(URL.init(string:)) ?? URL(string: "https://visao.example.com/api")!
    }

    public static var main: SharedConfig { SharedConfig(info: Bundle.main.infoDictionary ?? [:]) }

    /// The App Group's defaults, or the app's own when the group is not there (an old build).
    public var defaults: UserDefaults {
        appGroup.flatMap(UserDefaults.init(suiteName:)) ?? .standard
    }

    public func tokens(items: KeychainItems = SystemKeychain()) -> KeychainTokenStore {
        KeychainTokenStore(service: tokenService, accessGroup: keychainGroup, items: items)
    }

    /// The address typed on the login screen, when it differs from the configured one. Read from
    /// the group first, then from where the app kept it before (and moved into the group).
    public func savedServer(legacy: UserDefaults = .standard) -> URL? {
        let shared = defaults
        if let raw = shared.string(forKey: Self.serverKey) { return URL(string: raw) }
        guard let raw = legacy.string(forKey: Self.serverKey) else { return nil }
        if shared !== legacy { shared.set(raw, forKey: Self.serverKey) }
        return URL(string: raw)
    }

    public func saveServer(_ url: URL?) {
        let value = url == configuredServer ? nil : url?.absoluteString
        defaults.set(value, forKey: Self.serverKey)
        if defaults !== UserDefaults.standard { UserDefaults.standard.set(value, forKey: Self.serverKey) }
    }

    /// Where the API is for this device: the saved address, or the configured one.
    public var server: URL { savedServer() ?? configuredServer }

    /// Empty, or a build setting that was never filled ("$(…)"), is no value.
    private static func value(_ any: Any?) -> String? {
        guard let text = (any as? String)?.trimmingCharacters(in: .whitespaces), !text.isEmpty, !text.contains("$(") else { return nil }
        return text
    }
}
