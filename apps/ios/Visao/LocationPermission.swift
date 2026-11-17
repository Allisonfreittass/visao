import CoreLocation
import Observation
import VisaoKit

/// "Usar minha localização" in Ajustes (docs/LOCALIZACAO.md): turning it on asks the system for
/// "Durante o uso" right then, never in the middle of a question. Denied, the switch goes back off.
@MainActor
@Observable
final class LocationPermission: NSObject, CLLocationManagerDelegate {
    private(set) var on = LocationPrefs.enabled()
    /// Why it went back off, and how to allow it in the iPhone's settings.
    private(set) var note: String?
    private let manager = CLLocationManager()

    static let deniedNote = "O iPhone não deixou. Para liberar: Ajustes do iPhone > Privacidade e Segurança > Serviços de Localização > V.I.S.A.O. > Durante o Uso."

    override init() {
        super.init()
        manager.delegate = self
        // Taken away in the iPhone's settings since the last time: off here too.
        if on, isDenied(manager.authorizationStatus) { turnOff(explaining: true) }
    }

    func set(_ value: Bool) {
        note = nil
        guard value else {
            turnOff(explaining: false)
            return
        }
        switch manager.authorizationStatus {
        case .notDetermined:
            on = true
            LocationPrefs.set(true)
            manager.requestWhenInUseAuthorization()
        case let status where DevicePosition.isAllowed(status):
            on = true
            LocationPrefs.set(true)
        default:
            turnOff(explaining: true)
        }
    }

    private func turnOff(explaining: Bool) {
        on = false
        LocationPrefs.set(false)
        if explaining { note = Self.deniedNote }
    }

    private func isDenied(_ status: CLAuthorizationStatus) -> Bool {
        status == .denied || status == .restricted
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        MainActor.assumeIsolated {
            if on, isDenied(status) { turnOff(explaining: true) }
        }
    }
}
