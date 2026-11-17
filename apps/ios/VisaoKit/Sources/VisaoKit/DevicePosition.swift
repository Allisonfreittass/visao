import CoreLocation
import Foundation

/// One position from the phone for a "perto de mim" message: `requestLocation()` at about 100 m,
/// waiting up to ~4 s. Nothing here writes it anywhere; it lives only until the message is sent.
public struct DevicePosition: PositionSource {
    public let timeout: Duration

    public init(timeout: Duration = .seconds(4)) {
        self.timeout = timeout
    }

    /// "Durante o uso" (or "Sempre") given in the iPhone's settings.
    public static func isAllowed(_ status: CLAuthorizationStatus) -> Bool {
        #if os(iOS)
        status == .authorizedWhenInUse || status == .authorizedAlways
        #else
        status == .authorizedAlways
        #endif
    }

    public func current() async -> SentLocation? {
        await OneShot.fetch(timeout: timeout)
    }

    @MainActor
    private final class OneShot: NSObject, CLLocationManagerDelegate {
        private let manager = CLLocationManager()
        private var continuation: CheckedContinuation<SentLocation?, Never>?
        private var keep: OneShot?

        static func fetch(timeout: Duration) async -> SentLocation? {
            let shot = OneShot()
            return await shot.run(timeout: timeout)
        }

        private func run(timeout: Duration) async -> SentLocation? {
            let status = manager.authorizationStatus
            guard DevicePosition.isAllowed(status) else { return nil }
            return await withCheckedContinuation { continuation in
                self.continuation = continuation
                keep = self
                manager.delegate = self
                manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
                manager.requestLocation()
                Task { [weak self] in
                    try? await Task.sleep(for: timeout)
                    self?.finish(nil)
                }
            }
        }

        private func finish(_ location: CLLocation?) {
            guard let continuation else { return }
            self.continuation = nil
            manager.stopUpdatingLocation()
            let sent = location.map {
                SentLocation(
                    lat: $0.coordinate.latitude, lon: $0.coordinate.longitude,
                    accuracyM: $0.horizontalAccuracy >= 0 ? $0.horizontalAccuracy : nil, at: $0.timestamp
                )
            }
            continuation.resume(returning: sent)
            keep = nil
        }

        nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
            let last = locations.last
            MainActor.assumeIsolated { finish(last) }
        }

        nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
            MainActor.assumeIsolated { finish(nil) }
        }
    }
}
