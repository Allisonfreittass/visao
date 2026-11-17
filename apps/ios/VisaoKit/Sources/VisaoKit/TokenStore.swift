import Foundation
import Security

/// Where the access token lives. In the app it is the Keychain, never UserDefaults.
public protocol TokenStore: AnyObject, Sendable {
    var token: String? { get set }
}

/// The Keychain calls the token store makes, so the sharing between the app and the share
/// extension can be tested without a real Keychain. `group` nil reads or deletes in any group the
/// caller can see, and writes in the caller's default one.
public protocol KeychainItems: Sendable {
    func read(service: String, account: String, group: String?) -> Data?
    /// False when the group is not in this build's entitlements (errSecMissingEntitlement).
    func write(_ data: Data, service: String, account: String, group: String?) -> Bool
    func delete(service: String, account: String, group: String?)
}

/// The token in the Keychain, readable only on this device after the first unlock. With an access
/// group, the app and the share extension read the same item (docs/COMPARTILHAR.md).
public final class KeychainTokenStore: TokenStore, @unchecked Sendable {
    private let service: String
    private let account = "access_token"
    private let group: String?
    private let items: KeychainItems
    private let lock = NSLock()

    public init(service: String, accessGroup: String? = nil, items: KeychainItems = SystemKeychain()) {
        self.service = service
        self.group = accessGroup
        self.items = items
    }

    public var token: String? {
        get {
            lock.withLock {
                if let group, let data = items.read(service: service, account: account, group: group) {
                    return String(data: data, encoding: .utf8)
                }
                guard let data = items.read(service: service, account: account, group: nil) else { return nil }
                // Saved before the group existed (app up to 15/11/2026): it moves into the group,
                // so nobody has to sign in again and the extension can read it.
                if group != nil { store(data) }
                return String(data: data, encoding: .utf8)
            }
        }
        set {
            lock.withLock {
                guard let newValue else {
                    items.delete(service: service, account: account, group: nil)
                    return
                }
                store(Data(newValue.utf8))
            }
        }
    }

    /// The first open of the app after the update: the old item goes into the shared group.
    public func migrateIfNeeded() {
        _ = token
    }

    private func store(_ data: Data) {
        items.delete(service: service, account: account, group: nil)
        if let group, items.write(data, service: service, account: account, group: group) { return }
        // A build without the entitlement (or the group missing): keep working, unshared.
        _ = items.write(data, service: service, account: account, group: nil)
    }
}

/// The real Keychain.
public struct SystemKeychain: KeychainItems {
    public init() {}

    public func read(service: String, account: String, group: String?) -> Data? {
        var query = Self.query(service: service, account: account, group: group)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess else { return nil }
        return item as? Data
    }

    public func write(_ data: Data, service: String, account: String, group: String?) -> Bool {
        var attributes = Self.query(service: service, account: account, group: group)
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(attributes as CFDictionary, nil) == errSecSuccess
    }

    public func delete(service: String, account: String, group: String?) {
        SecItemDelete(Self.query(service: service, account: account, group: group) as CFDictionary)
    }

    private static func query(service: String, account: String, group: String?) -> [String: Any] {
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        if let group { query[kSecAttrAccessGroup as String] = group }
        return query
    }
}

/// For tests and previews.
public final class MemoryTokenStore: TokenStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: String?

    public init(token: String? = nil) {
        value = token
    }

    public var token: String? {
        get { lock.withLock { value } }
        set { lock.withLock { value = newValue } }
    }
}
