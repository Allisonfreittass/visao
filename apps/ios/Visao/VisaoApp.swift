import SwiftUI

@main
struct VisaoApp: App {
    @State private var session = Session()
    @State private var appearance = Appearance()

    var body: some Scene {
        WindowGroup {
            Root()
                .environment(session)
                .environment(appearance)
                .environment(\.palette, appearance.palette)
                // Claro, Escuro, or nil ("Sistema"): the keyboard and the system sheets follow it.
                .preferredColorScheme(appearance.preferredScheme)
        }
    }
}

/// Logged in or not; and, while "Sistema" lets the iPhone decide, which way it is set.
private struct Root: View {
    @Environment(Session.self) private var session
    @Environment(Appearance.self) private var appearance
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Group {
            if session.loggedIn {
                Shell()
            } else {
                LoginView()
            }
        }
        .onChange(of: scheme, initial: true) { _, now in
            if appearance.mode == .sistema { appearance.systemDark = now == .dark }
        }
    }
}
