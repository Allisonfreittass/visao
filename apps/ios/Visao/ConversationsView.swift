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
    @Environment(Appearance.self) private var appearance
    @Environment(\.palette) private var palette
    @Environment(\.scenePhase) private var scenePhase
    @State private var path: [ChatRoute] = []
    @State private var confirmLogout = false

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    header
                    if let error = session.listError {
                        Label(error, systemImage: "wifi.exclamationmark")
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.tintaSuave)
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .glass(palette, cornerRadius: 18, strong: false, shadow: false)
                    }
                    if session.conversations.isEmpty && !session.loadingList && session.listError == nil {
                        empty
                    } else {
                        list
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }
            .refreshable { await session.loadHome() }
            .toolbar(.hidden, for: .navigationBar)
            .visaoBackground()
            .navigationDestination(for: ChatRoute.self) { route in
                switch route {
                case .existing(let id): ChatScreen(api: session.api, conversationId: id)
                case .new: ChatScreen(api: session.api, conversationId: nil)
                }
            }
            .confirmationDialog("Sair desta conta?", isPresented: $confirmLogout, titleVisibility: .visible) {
                Button("Sair", role: .destructive) { session.logout() }
            }
        }
        .task { await session.loadHome() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await session.loadHome() } }
        }
    }

    private var header: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text("V.I.S.A.O.")
                    .font(Typo.display(30, relativeTo: .largeTitle))
                    .accessibilityLabel("Visão")
                    .accessibilityAddTraits(.isHeader)
                Text(session.agentName.map { "Conversando com \($0)" } ?? "Sem nome ainda")
                    .font(Typo.mono(.caption2))
                    .textCase(.uppercase)
                    .tracking(0.6)
                    .foregroundStyle(palette.tintaFraca)
            }
            Spacer()
            accountMenu
            Button {
                path.append(.new(UUID()))
            } label: {
                Image(systemName: "plus")
                    .font(.body.weight(.medium))
                    .glassCircle(palette)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Nova conversa")
        }
        .padding(.top, 8)
    }

    private var accountMenu: some View {
        @Bindable var appearance = appearance
        return Menu {
            Picker("Aparência", selection: $appearance.mode) {
                ForEach(Appearance.Mode.allCases) { Text($0.label).tag($0) }
            }
            if appearance.mode == .neblina {
                Toggle("Neblina em movimento", isOn: $appearance.moving)
            }
            Section(session.serverAddress) {
                Button("Sair", systemImage: "rectangle.portrait.and.arrow.right", role: .destructive) {
                    confirmLogout = true
                }
            }
        } label: {
            Image(systemName: "person")
                .font(.body.weight(.medium))
                .glassCircle(palette)
        }
        .accessibilityLabel("Conta e aparência")
    }

    private var list: some View {
        VStack(alignment: .leading, spacing: 10) {
            Rotulo("Conversas").padding(.horizontal, 6)
            LazyVStack(spacing: 2) {
                ForEach(session.conversations) { conversation in
                    NavigationLink(value: ChatRoute.existing(conversation.id)) {
                        HStack(spacing: 12) {
                            Image(systemName: conversation.projectId == nil ? "bubble.left" : "folder")
                                .foregroundStyle(palette.estanho)
                                .frame(width: 22)
                            Text(DayLabel.text(for: conversation.createdAt))
                                .font(Typo.text(.body))
                            Spacer()
                            Image(systemName: "chevron.right")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(palette.tintaFraca)
                        }
                        .padding(.horizontal, 14)
                        .frame(minHeight: 52)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(RowButtonStyle())
                }
            }
            .padding(6)
            .glass(palette, cornerRadius: 22)
        }
    }

    private var empty: some View {
        VStack(spacing: 12) {
            Rotulo("Conversa nova")
            (Text("Por onde a gente ").font(Typo.display(30, relativeTo: .title))
                + Text("começa?").font(Typo.display(30, relativeTo: .title, italic: true)))
                .multilineTextAlignment(.center)
            Text("Um bug, uma ideia pela metade, um plano.")
                .font(Typo.text(.callout))
                .foregroundStyle(palette.tintaSuave)
                .multilineTextAlignment(.center)
            Button {
                path.append(.new(UUID()))
            } label: {
                Text("Começar uma conversa")
                    .font(Typo.text(.callout, weight: .medium))
                    .padding(.horizontal, 22)
                    .frame(minHeight: 46)
                    .foregroundStyle(palette.pilulaAtivaTinta)
                    .background(palette.pilulaAtiva, in: Capsule())
            }
            .buttonStyle(.plain)
            .padding(.top, 6)
        }
        .padding(28)
        .frame(maxWidth: .infinity)
        .glass(palette, cornerRadius: 32)
        .padding(.top, 40)
    }
}

/// A list row that lights up like the web's hover while pressed.
struct RowButtonStyle: ButtonStyle {
    @Environment(\.palette) private var palette

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(palette.tinta)
            .background(configuration.isPressed ? palette.fundoHover : .clear, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
