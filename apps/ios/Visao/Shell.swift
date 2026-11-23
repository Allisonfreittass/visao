import SwiftUI
import VisaoKit

/// The places of the web (Rail.tsx / SkyNav.tsx): Início, Chat and Projetos on top (Chat is the
/// continuous conversation), the avatar opens Ajustes, the drawer has what is not on top.
enum Place: Int, Hashable, CaseIterable {
    case inicio, chat, projetos, caderno, mac, ajustes

    /// The three in the pill, in order: swiping moves between them.
    static let tabs: [Place] = [.inicio, .chat, .projetos]

    var tabLabel: String {
        switch self {
        case .inicio: "Início"
        case .chat: "Chat"
        case .projetos: "Projetos"
        default: ""
        }
    }
}

/// Which conversation the chat shows. `key` changes only when you pick another one, so a
/// conversation created by its first message keeps its screen (and the reply in flight).
struct ChatTarget: Equatable {
    var key = UUID()
    var conversationId: String?
    var projectId: String?
    /// The continuous conversation (docs/CONVERSA_CONTINUA.md), which the Chat tab always opens.
    var continuous = false

    static func continuous(_ id: String?) -> ChatTarget {
        ChatTarget(conversationId: id, continuous: true)
    }
}

/// Logged in: the top bar over the forest, the place under it, the drawer over everything.
/// The chat stays mounted while you visit the other places, so a reply in flight keeps going and
/// you come back to where you were; the others slide in from the side of their tab.
struct Shell: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var place: Place = .chat
    @State private var forward = true
    @State private var target: ChatTarget?
    @State private var drawerOpen = false
    @State private var onboarding: OnboardingStatus?
    /// A project's chat is in front, under the Projetos tab (ADR-0021).
    @State private var projectChat = false
    @State private var openingProject = false
    /// The 4-second opening, once a day, when the app is ready (not on the first-run questions).
    @State private var intro = false

    /// What the mascot shows outside a chat: asleep without a connection, at rest otherwise.
    private var mascotState: CiclopeState { session.listError == nil ? .idle : .offline }

    /// The chat shows on Chat, and on Projetos while a project's chat is open.
    private var chatInFront: Bool { place == .chat || (place == .projetos && projectChat) }

    var body: some View {
        VStack(spacing: 0) {
            TopBar(place: place, state: mascotState) { drawerOpen = true }
            GeometryReader { proxy in
                ZStack {
                    chat
                        .offset(x: chatInFront ? 0 : (place.rawValue < Place.chat.rawValue ? proxy.size.width : -proxy.size.width))
                        .opacity(chatInFront ? 1 : 0)
                        .allowsHitTesting(chatInFront)
                        .accessibilityHidden(!chatInFront)
                    if !chatInFront {
                        other
                            .id(place)
                            .transition(slide)
                            .simultaneousGesture(swipeBetweenTabs)
                    }
                }
                .frame(width: proxy.size.width, height: proxy.size.height)
                .clipped()
            }
            TabBar(place: place, pendingCount: session.pending.count, state: mascotState) { $0 == .chat ? openChat() : go($0) }
        }
        .sheet(isPresented: $drawerOpen) {
            MenuSheet(place: place) { next in
                drawerOpen = false
                go(next)
            }
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
            .visaoBackground()
        }
        .visaoBackground()
        .overlay {
            if intro {
                IntroView { withAnimation(.easeOut(duration: 0.25)) { intro = false } }
                    .transition(.opacity)
            }
        }
        .task {
            async let home: Void = session.loadHome()
            // The first run asks a few questions, once, always skippable; the opening waits for it.
            let status = try? await session.api.onboarding()
            if let status, !status.completed {
                onboarding = status
            } else if Opening.takeTurn(reduceMotion: UIAccessibility.isReduceMotionEnabled) {
                intro = true
            }
            await home
            if target == nil {
                // The continuous conversation; if it did not load, sending creates it.
                target = .continuous(session.continuousId)
            }
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task { await session.loadHome() }
            // Back the next day without having closed the app: the opening plays once.
            if onboarding == nil, target != nil, Opening.takeTurn(reduceMotion: UIAccessibility.isReduceMotionEnabled) {
                intro = true
            }
        }
        .fullScreenCover(item: Binding(get: { onboarding.map(OnboardingBox.init) }, set: { onboarding = $0?.status })) { box in
            OnboardingView(status: box.status) { onboarding = nil }
        }
        .onReceive(NotificationCenter.default.publisher(for: .visaoRestartOnboarding)) { _ in
            Task { if let status = try? await session.api.onboarding() { onboarding = status } }
        }
    }

    private var slide: AnyTransition {
        guard !reduceMotion else { return .opacity }
        return .asymmetric(
            insertion: .move(edge: forward ? .trailing : .leading).combined(with: .opacity),
            removal: .move(edge: forward ? .leading : .trailing).combined(with: .opacity)
        )
    }

    @ViewBuilder
    private var chat: some View {
        if let target {
            ChatScreen(
                api: session.api, conversationId: target.conversationId, projectId: target.projectId,
                continuous: target.continuous,
                isActive: chatInFront,
                onCreated: { self.target?.conversationId = $0.id },
                onOpenProject: { openProject($0) },
                onBackToProjects: { withAnimation(.spring(response: 0.42, dampingFraction: 0.86)) { projectChat = false } },
                onProjectDeleted: { openChat() }
            )
            .id(target.key)
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private var other: some View {
        switch place {
        case .inicio:
            InicioView(
                currentConversation: target?.conversationId,
                onOpenConversation: { open(conversation: $0) },
                onDraft: { text in
                    session.chatDraft = text
                    openChat()
                }
            )
        case .projetos:
            ProjectsView(onOpenProject: { openProject($0) })
                .overlay {
                    if openingProject { ProgressView().controlSize(.large) }
                }
        case .caderno:
            CadernoView()
        case .mac:
            MacView()
        case .ajustes:
            SettingsView()
        case .chat:
            EmptyView()
        }
    }

    /// Início ⇄ Chat ⇄ Projetos with a sideways swipe on the pages (the chat keeps its own swipe,
    /// which answers a message).
    private var swipeBetweenTabs: some Gesture {
        DragGesture(minimumDistance: 30)
            .onEnded { value in
                let dx = value.translation.width
                guard abs(dx) > 80, abs(dx) > abs(value.translation.height) * 2,
                      let index = Place.tabs.firstIndex(of: place) else { return }
                let next = dx < 0 ? index + 1 : index - 1
                if Place.tabs.indices.contains(next) {
                    Place.tabs[next] == .chat ? openChat() : go(Place.tabs[next])
                }
            }
    }

    private func go(_ next: Place) {
        guard next != place else {
            withAnimation(.spring(duration: 0.35)) { drawerOpen = false }
            // Projetos again, from a project's chat: back to the list.
            if next == .projetos && projectChat {
                withAnimation(.spring(response: 0.42, dampingFraction: 0.86)) { projectChat = false }
            }
            return
        }
        projectChat = false
        forward = next.rawValue > place.rawValue
        withAnimation(.spring(duration: 0.35)) { drawerOpen = false }
        withAnimation(.spring(response: 0.42, dampingFraction: 0.86)) { place = next }
    }

    /// Chat: always the continuous conversation, also from inside a project's chat.
    private func openChat() {
        if target?.continuous != true || target?.conversationId != session.continuousId && session.continuousId != nil {
            target = .continuous(session.continuousId)
        }
        go(.chat)
    }

    private func open(conversation id: String) {
        if id == session.continuousId {
            openChat()
            return
        }
        if target?.conversationId != id { target = ChatTarget(conversationId: id) }
        go(.chat)
    }

    /// The project's own chat (GET /conversations/project/{id}), under the Projetos tab.
    private func openProject(_ id: String) {
        guard !openingProject else { return }
        openingProject = true
        Task {
            defer { openingProject = false }
            do {
                let conversation = try await session.api.projectConversation(projectId: id)
                if target?.conversationId != conversation.id {
                    target = ChatTarget(conversationId: conversation.id, projectId: id)
                }
                if place != .projetos { go(.projetos) }
                withAnimation(.spring(response: 0.42, dampingFraction: 0.86)) { projectChat = true }
            } catch {
                session.handle(error)
            }
        }
    }
}

private struct OnboardingBox: Identifiable {
    let status: OnboardingStatus
    var id: Int { 0 }
}

extension Notification.Name {
    /// Ajustes → Perguntas iniciais → Refazer.
    static let visaoRestartOnboarding = Notification.Name("visaoRestartOnboarding")
}

/// The top bar: the lockup on the left, the avatar on the right (it opens Caderno, Integrações
/// and Ajustes). No drawer button and no pill: the places are in the tab bar.
struct TopBar: View {
    let place: Place
    let state: CiclopeState
    let onMenu: () -> Void
    @Environment(\.palette) private var palette

    var body: some View {
        HStack(spacing: 10) {
            SentinelaView(state: state, size: 26)
            Wordmark(size: 18)
            Spacer(minLength: 0)
            Button(action: onMenu) {
                Text(String(OwnerName.value.prefix(1)))
                    .font(Typo.text(.callout, weight: .medium))
                    .foregroundStyle(palette.bg)
                    .frame(width: 44, height: 44)
                    .background(palette.text, in: Circle())
                    .overlay {
                        if [.caderno, .mac, .ajustes].contains(place) { Circle().strokeBorder(palette.borderStrong, lineWidth: 2).padding(-4) }
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Caderno, Integrações e Ajustes")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }
}

/// The owner's first name (the API keeps only an e-mail), as on the web (brand/copy.ts).
enum OwnerName {
    static let value = "Allison"
}

/// "V.I.S.A.O." in Space Grotesk: the dots gray, only the last one red.
struct Wordmark: View {
    var size: CGFloat = 18
    @Environment(\.palette) private var palette

    var body: some View {
        let letters = Array("V.I.S.A.O.")
        letters.indices.reduce(Text("")) { text, i in
            let c = letters[i]
            let color = c == "." ? (i == letters.count - 1 ? palette.red : palette.textMuted) : palette.text
            return text + Text(String(c)).foregroundColor(color)
        }
        .font(Typo.display(size, relativeTo: .headline))
        .tracking(size * 0.04)
        .accessibilityLabel("Visão")
    }
}

/// The tab bar at the bottom: Início (the mascot is its icon), Chat, Projetos. The active tab
/// has a small red bar on top.
struct TabBar: View {
    let place: Place
    let pendingCount: Int
    let state: CiclopeState
    let onPlace: (Place) -> Void
    @Environment(\.palette) private var palette

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Place.tabs, id: \.self) { tab in
                let active = place == tab
                Button { onPlace(tab) } label: {
                    VStack(spacing: 4) {
                        ZStack(alignment: .topTrailing) {
                            icon(tab, active: active)
                                .frame(width: 26, height: 26)
                            if tab == .inicio && pendingCount > 0 {
                                Text("\(pendingCount)")
                                    .font(Typo.text(.caption2, weight: .medium))
                                    .foregroundStyle(palette.onRed)
                                    .padding(.horizontal, 5)
                                    .frame(minWidth: 18, minHeight: 18)
                                    .background(palette.amber, in: Capsule())
                                    .offset(x: 10, y: -6)
                                    .accessibilityLabel("\(pendingCount) esperando você")
                            }
                        }
                        Text(tab.tabLabel)
                            .font(Typo.text(.caption2, weight: active ? .medium : .regular))
                            .foregroundStyle(active ? palette.text : palette.textMuted)
                    }
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .overlay(alignment: .top) {
                        Capsule()
                            .fill(palette.red)
                            .frame(width: 28, height: 3)
                            .opacity(active ? 1 : 0)
                            .offset(y: -6)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(active ? [.isSelected] : [])
            }
        }
        .padding(.top, 6)
        .background(palette.bg.opacity(0.92))
        .overlay(alignment: .top) { Rectangle().fill(palette.border).frame(height: 1) }
        .sensoryFeedback(.selection, trigger: place)
        .animation(.timingCurve(0.2, 0.8, 0.2, 1, duration: 0.22), value: place)
    }

    @ViewBuilder
    private func icon(_ tab: Place, active: Bool) -> some View {
        switch tab {
        case .inicio: SentinelaView(state: state, size: 24, animated: active)
        case .chat: Image(systemName: "bubble.left").font(.system(size: 19, weight: .medium)).foregroundStyle(active ? palette.text : palette.textMuted)
        default: Image(systemName: "folder").font(.system(size: 19, weight: .medium)).foregroundStyle(active ? palette.text : palette.textMuted)
        }
    }
}

/// The avatar's sheet: Caderno, the integrations with their real status, and Ajustes.
struct MenuSheet: View {
    let place: Place
    let onPlace: (Place) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var macOnline: Bool?
    @State private var googleConnected: Bool?

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                Text(String(OwnerName.value.prefix(1)))
                    .font(Typo.text(.headline, weight: .medium))
                    .foregroundStyle(palette.bg)
                    .frame(width: 40, height: 40)
                    .background(palette.text, in: Circle())
                Text(OwnerName.value).font(Typo.text(.headline, weight: .medium))
            }
            row(.caderno, label: "Caderno") { SensorView(kind: .caderno, size: 28) }
            VStack(alignment: .leading, spacing: 4) {
                Text("Integrações").font(Typo.text(.footnote, weight: .medium)).foregroundStyle(palette.textMuted)
                row(.mac, label: "Mac", status: status(macOnline)) { SensorView(kind: .mac, size: 28, asleep: macOnline != true) }
                row(.ajustes, label: "E-mail", status: status(googleConnected)) { SensorView(kind: .email, size: 28, asleep: googleConnected != true) }
            }
            row(.ajustes, label: "Ajustes") {
                Image(systemName: "gearshape").font(.system(size: 18, weight: .medium)).frame(width: 28, height: 28).foregroundStyle(palette.text2)
            }
            Spacer(minLength: 0)
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .task {
            macOnline = (try? await session.api.armDevices()).flatMap { list in list.isEmpty ? nil : list.contains { $0.online } }
            googleConnected = (try? await session.api.google())?.connected
        }
    }

    private func status(_ on: Bool?) -> (String, Color) {
        if session.listError != nil { return ("Sem conexão", palette.textMuted) }
        switch on {
        case true?: return ("● Conectado", palette.green)
        case false?: return ("Desconectado", palette.textMuted)
        case nil: return ("Não pareado", palette.textMuted)
        }
    }

    private func row<Icon: View>(_ target: Place, label: String, status: (String, Color)? = nil, @ViewBuilder icon: () -> Icon) -> some View {
        Button { onPlace(target) } label: {
            HStack(spacing: 12) {
                icon()
                VStack(alignment: .leading, spacing: 2) {
                    Text(label).font(Typo.text(.subheadline, weight: .medium)).foregroundStyle(palette.text)
                    if let status {
                        Text(status.0).font(Typo.text(.caption, weight: .medium)).foregroundStyle(status.1)
                    }
                }
                Spacer()
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(palette.textMuted)
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 52)
            .background(place == target ? palette.surface2 : palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(palette.border))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
