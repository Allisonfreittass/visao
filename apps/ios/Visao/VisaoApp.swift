import SwiftUI

@main
struct VisaoApp: App {
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            Group {
                if session.loggedIn {
                    ConversationsView()
                } else {
                    LoginView()
                }
            }
            .environment(session)
            .tint(.accentColor)
        }
    }
}
