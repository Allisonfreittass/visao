import Foundation
import Security

/// Where the access token lives. In the app it is the Keychain, never UserDefaults.
public protocol TokenStore: AnyObject, Sendable {
    var token: String? { get set }
}

/// The token in the Keychain, readable only on this device after the first unlock.
public final class KeychainTokenStore: TokenStore, @unchecked Sendable {
    private let service: String
    private let account = "access_token"
    private let lock = NSLock()

    public init(service: String) {
        self.service = service
    }

    public var token: String? {
        get {
            lock.lock()
            defer { lock.unlock() }
            var query = baseQuery
            query[kSecReturnData as String] = true
            query[kSecMatchLimit as String] = kSecMatchLimitOne
            var item: CFTypeRef?
            guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
            return String(data: data, encoding: .utf8)
        }
        set {
            lock.lock()
            defer { lock.unlock() }
            SecItemDelete(baseQuery as CFDictionary)
            guard let newValue else { return }
            var attributes = baseQuery
            attributes[kSecValueData as String] = Data(newValue.utf8)
            attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(attributes as CFDictionary, nil)
        }
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
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
