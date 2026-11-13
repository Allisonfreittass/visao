import SwiftUI
import VisaoKit

/// Where the chat opens: an existing conversation, or a new one that is only created on the
/// server with its first message (as on the web).
enum ChatRoute: Hashable {
    case existing(String)
    case new(UUID)
}

struct ConversationsView: View {
    @Environment(Session.self) private var session
    @Environment(\.scenePhase) private var scenePhase
    @State private var path: [ChatRoute] = []
    @State private var confirmLogout = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error = session.listError {
                    Label(error, systemImage: "wifi.exclamationmark")
                        .foregroundStyle(.secondary)
                }
                ForEach(session.conversations) { conversation in
                    NavigationLink(value: ChatRoute.existing(conversation.id)) {
                        Label {
                            Text(DayLabel.text(for: conversation.createdAt))
                        } icon: {
                            Image(systemName: conversation.projectId == nil ? "bubble.left" : "folder")
                        }
                    }
                }
            }
            .overlay {
                if session.conversations.isEmpty && !session.loadingList && session.listError == nil {
                    ContentUnavailableView {
                        Label("Nenhuma conversa ainda", systemImage: "bubble.left.and.bubble.right")
                    } description: {
                        Text("Um bug, uma ideia pela metade, um plano.")
                    } actions: {
                        Button("Começar uma conversa") { path.append(.new(UUID())) }
                            .buttonStyle(.borderedProminent)
                    }
                }
            }
            .navigationTitle(session.agentName ?? "Conversas")
            .refreshable { await session.loadHome() }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Text(session.serverAddress)
                        Button("Sair", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive) {
                            confirmLogout = true
                        }
                    } label: {
                        Image(systemName: "person.crop.circle")
                    }
                    .accessibilityLabel("Conta")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        path.append(.new(UUID()))
                    } label: {
                        Image(systemName: "square.and.pencil")
                    }
                    .accessibilityLabel("Nova conversa")
                }
            }
            .confirmationDialog("Sair desta conta?", isPresented: $confirmLogout, titleVisibility: .visible) {
                Button("Sair", role: .destructive) { session.logout() }
            }
            .navigationDestination(for: ChatRoute.self) { route in
                switch route {
                case .existing(let id): ChatScreen(api: session.api, conversationId: id)
                case .new: ChatScreen(api: session.api, conversationId: nil)
                }
            }
        }
        .task { await session.loadHome() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await session.loadHome() } }
        }
    }
}
