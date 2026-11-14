import SwiftUI

@main
struct VisaoApp: App {
    @State private var session = Session()
    @State private var appearance = Appearance()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if session.loggedIn {
                    Shell()
                } else {
                    LoginView()
                }
            }
            .environment(session)
            .environment(appearance)
            .environment(\.palette, appearance.palette)
            // Glass is light by day and dark at night, as on the web: the keyboard and the
            // system sheets follow it.
            .preferredColorScheme(appearance.isDark ? .dark : .light)
            .task {
                // A Kokoro model already on the iPhone opens in the background, no network.
                Task { await KokoroVoice.shared.loadIfDownloaded() }
                while !Task.isCancelled {
                    appearance.tick()
                    try? await Task.sleep(for: .seconds(60))
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { appearance.tick() }
            }
        }
    }
}
