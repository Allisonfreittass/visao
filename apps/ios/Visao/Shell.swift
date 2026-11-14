import SwiftUI
import VisaoKit

/// The places of the web (Rail.tsx / SkyNav.tsx): Chat is home, Início holds Pendências, the
/// avatar opens Ajustes, the drawer has the rest and the conversations.
enum Place: Hashable {
    case inicio, chat, projetos, mac, ajustes
}

/// Which conversation the chat shows. `key` changes only when you pick another one, so a
/// conversation created by its first message keeps its screen (and the reply in flight).
struct ChatTarget: Equatable {
    var key = UUID()
    var conversationId: String?
    var projectId: String?
}

/// Logged in: the top bar over the forest, the place under it, the drawer over everything.
struct Shell: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.scenePhase) private var scenePhase
    @State private var place: Place = .chat
    @State private var target: ChatTarget?
    @State private var drawerOpen = false

    var body: some View {
        VStack(spacing: 0) {
            SkyNav(place: place, pendingCount: session.pending.count, agentName: session.agentName, menuOpen: drawerOpen) {
                withAnimation(.spring(duration: 0.35)) { drawerOpen = true }
            } onPlace: { go($0) }
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .overlay {
            Drawer(
                open: $drawerOpen,
                place: place,
                current: target?.conversationId,
                onPlace: { go($0) },
                onConversation: { open(conversation: $0) },
                onNew: { newConversation(projectId: nil) }
            )
        }
        .visaoBackground()
        .task {
            await session.loadHome()
            if target == nil {
                // As on the web: the most recent conversation, or a new one.
                target = ChatTarget(conversationId: session.conversations.first?.id)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await session.loadHome() } }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch place {
        case .chat:
            if let target {
                ChatScreen(
                    api: session.api, conversationId: target.conversationId, projectId: target.projectId,
                    onCreated: { self.target?.conversationId = $0.id }
                )
                .id(target.key)
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        case .inicio:
            InicioView(currentConversation: target?.conversationId) { open(conversation: $0) }
        case .projetos:
            ProjectsView(
                currentConversation: target?.conversationId,
                onOpen: { open(conversation: $0) },
                onNew: { newConversation(projectId: $0) }
            )
        case .mac:
            MacView()
        case .ajustes:
            SettingsView()
        }
    }

    private func go(_ next: Place) {
        withAnimation(.spring(duration: 0.35)) { drawerOpen = false }
        withAnimation(.easeInOut(duration: 0.2)) { place = next }
    }

    private func open(conversation id: String) {
        if target?.conversationId != id { target = ChatTarget(conversationId: id) }
        go(.chat)
    }

    private func newConversation(projectId: String?) {
        target = ChatTarget(conversationId: nil, projectId: projectId)
        go(.chat)
    }
}

/// The web's top bar: the round drawer button, the three places in a glass pill, the avatar
/// (settings) with his initial.
struct SkyNav: View {
    let place: Place
    let pendingCount: Int
    let agentName: String?
    let menuOpen: Bool
    let onMenu: () -> Void
    let onPlace: (Place) -> Void
    @Environment(\.palette) private var palette

    private let tabs: [(Place, String)] = [(.inicio, "Início"), (.chat, "Chat"), (.projetos, "Projetos")]

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onMenu) {
                Image(systemName: "line.3.horizontal")
                    .font(.body.weight(.medium))
                    .foregroundStyle(palette.tinta)
                    .glassCircle(palette, size: 42)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Conversas, Mac e mais")
            Spacer(minLength: 0)
            HStack(spacing: 2) {
                ForEach(tabs, id: \.0) { tab, label in
                    Button { onPlace(tab) } label: {
                        HStack(spacing: 6) {
                            Text(label)
                            if tab == .inicio && pendingCount > 0 {
                                Text("\(pendingCount)")
                                    .font(Typo.text(.caption2, weight: .medium))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 5)
                                    .frame(minWidth: 18, minHeight: 18)
                                    .background(palette.lanterna, in: Capsule())
                                    .accessibilityLabel("\(pendingCount) esperando você")
                            }
                        }
                        .font(Typo.text(.subheadline))
                        .foregroundStyle(place == tab ? palette.pilulaAtivaTinta : palette.tintaFraca)
                        .padding(.horizontal, 14)
                        .frame(minHeight: 38)
                        .background(place == tab ? palette.pilulaAtiva : .clear, in: Capsule())
                        .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(place == tab ? .isSelected : [])
                }
            }
            .padding(4)
            .glass(palette, cornerRadius: 999, strong: false, shadow: false)
            .animation(.easeInOut(duration: 0.24), value: place)
            Spacer(minLength: 0)
            Button { onPlace(.ajustes) } label: {
                Text((agentName ?? "Visão").prefix(1).uppercased())
                    .font(Typo.text(.callout, weight: .medium))
                    .foregroundStyle(Color(rgb: 0xf4f7f8))
                    .frame(width: 42, height: 42)
                    .background(place == .ajustes ? palette.pilulaAtiva : palette.estanho, in: Circle())
                    .overlay {
                        if place == .ajustes { Circle().strokeBorder(palette.vidroForte, lineWidth: 3).padding(-3) }
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Ajustes")
        }
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .padding(.bottom, 4)
    }
}

/// The drawer: the brand, the places, the conversations, and whether we are connected. Drag it
/// to the left or tap outside to close.
struct Drawer: View {
    @Binding var open: Bool
    let place: Place
    let current: String?
    let onPlace: (Place) -> Void
    let onConversation: (String) -> Void
    let onNew: () -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var drag: CGFloat = 0

    private let items: [(Place, String, String)] = [
        (.chat, "Conversa", "bubble.left"),
        (.inicio, "Pendências", "tray"),
        (.projetos, "Projetos", "folder"),
        (.mac, "Mac", "laptopcomputer"),
        (.ajustes, "Ajustes", "slider.horizontal.3"),
    ]

    var body: some View {
        ZStack(alignment: .leading) {
            if open {
                Rectangle()
                    .fill(Color(rgb: 0x1d1d1f, opacity: 0.18))
                    .background(.ultraThinMaterial.opacity(0.6))
                    .ignoresSafeArea()
                    .onTapGesture { close() }
                    .transition(.opacity)
                    .accessibilityLabel("Fechar")
                    .accessibilityAddTraits(.isButton)
                panel
                    .offset(x: min(0, drag))
                    .gesture(
                        DragGesture(minimumDistance: 10)
                            .onChanged { drag = $0.translation.width }
                            .onEnded { value in
                                if value.translation.width < -70 || value.predictedEndTranslation.width < -160 { close() }
                                withAnimation(.spring(duration: 0.3)) { drag = 0 }
                            }
                    )
                    .transition(.move(edge: .leading))
            }
        }
        .animation(.spring(duration: 0.35), value: open)
    }

    private func close() {
        withAnimation(.spring(duration: 0.35)) { open = false }
    }

    private var panel: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("V.I.S.A.O.")
                .font(Typo.display(30, relativeTo: .largeTitle))
                .padding(.leading, 10)
                .accessibilityLabel("Visão")
            VStack(spacing: 2) {
                ForEach(items, id: \.0) { item, label, icon in
                    Button { onPlace(item) } label: {
                        HStack(spacing: 12) {
                            Image(systemName: icon)
                                .frame(width: 20)
                                .foregroundStyle(place == item ? palette.estanho : palette.tintaFraca)
                            Text(label)
                            Spacer()
                            if item == .inicio && session.pending.count > 0 {
                                Text("\(session.pending.count)")
                                    .font(Typo.mono(.caption2))
                                    .padding(.horizontal, 6)
                                    .frame(minWidth: 20, minHeight: 20)
                                    .overlay(Capsule().strokeBorder(palette.estanho.opacity(0.4)))
                            }
                        }
                        .font(Typo.text(.subheadline, weight: .medium))
                        .foregroundStyle(place == item ? palette.tinta : palette.tintaSuave)
                        .padding(.horizontal, 10)
                        .frame(minHeight: 40)
                        .background(place == item ? palette.fundoHover : .clear, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            Rectangle().fill(palette.linha).frame(height: 1)
            HStack {
                Rotulo("Conversas")
                Spacer()
                Button(action: onNew) {
                    Image(systemName: "plus")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(palette.tintaSuave)
                        .frame(width: 28, height: 28)
                        .overlay(Circle().strokeBorder(palette.linhaForte))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Nova conversa")
            }
            .padding(.leading, 10)
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(session.conversations) { conversation in
                        Button { onConversation(conversation.id) } label: {
                            HStack {
                                Text(DayLabel.text(for: conversation.createdAt))
                                if conversation.projectId != nil {
                                    Image(systemName: "folder").font(.caption).foregroundStyle(palette.tintaFraca)
                                }
                                Spacer()
                            }
                            .font(Typo.text(.subheadline))
                            .foregroundStyle(conversation.id == current && place == .chat ? palette.tinta : palette.tintaSuave)
                            .padding(.horizontal, 10)
                            .frame(minHeight: 38)
                            .background(conversation.id == current && place == .chat ? palette.fundoHover : .clear, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                    if session.conversations.isEmpty {
                        Text("Nenhuma ainda.")
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.tintaFraca)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.leading, 10)
                    }
                }
            }
            .scrollIndicators(.hidden)
            Text(session.listError == nil ? "CONECTADO" : "SEM CONEXÃO")
                .font(Typo.mono(.caption2))
                .tracking(0.8)
                .foregroundStyle(session.listError == nil ? palette.sucesso : palette.erro)
                .padding(.leading, 10)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 22)
        .frame(width: 300)
        .frame(maxHeight: .infinity)
        .glass(palette, cornerRadius: 28)
        .padding(.leading, 12)
        .padding(.vertical, 12)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Navegação")
        .accessibilityAction(.escape) { close() }
    }
}
