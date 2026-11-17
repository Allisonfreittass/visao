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

    var body: some View {
        VStack(spacing: 0) {
            SkyNav(place: place, pendingCount: session.pending.count, agentName: session.agentName) {
                withAnimation(.spring(duration: 0.35)) { drawerOpen = true }
            } onPlace: { $0 == .chat ? openChat() : go($0) }
            GeometryReader { proxy in
                ZStack {
                    chat
                        .offset(x: place == .chat ? 0 : (place.rawValue < Place.chat.rawValue ? proxy.size.width : -proxy.size.width))
                        .opacity(place == .chat ? 1 : 0)
                        .allowsHitTesting(place == .chat)
                        .accessibilityHidden(place != .chat)
                    if place != .chat {
                        other
                            .id(place)
                            .transition(slide)
                            .simultaneousGesture(swipeBetweenTabs)
                    }
                }
                .frame(width: proxy.size.width, height: proxy.size.height)
                .clipped()
            }
        }
        .overlay {
            Drawer(open: $drawerOpen, place: place, onPlace: { go($0) })
        }
        .visaoBackground()
        .task {
            await session.loadHome()
            if target == nil {
                // The continuous conversation; if it did not load, sending creates it.
                target = .continuous(session.continuousId)
            }
            // The first run asks a few questions, once, always skippable.
            if let status = try? await session.api.onboarding(), !status.completed { onboarding = status }
        }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await session.loadHome() } }
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
                isActive: place == .chat,
                onCreated: { self.target?.conversationId = $0.id }
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
            ProjectsView(
                currentConversation: target?.conversationId,
                onOpen: { open(conversation: $0) },
                onNew: { newConversation(projectId: $0) }
            )
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
            return
        }
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

    private func newConversation(projectId: String?) {
        target = ChatTarget(conversationId: nil, projectId: projectId)
        go(.chat)
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

/// The web's top bar, the Apple way: the round drawer button, the three places in a glass pill
/// whose selection slides (and follows your finger if you drag it across), the avatar.
struct SkyNav: View {
    let place: Place
    let pendingCount: Int
    let agentName: String?
    let onMenu: () -> Void
    let onPlace: (Place) -> Void
    @Environment(\.palette) private var palette
    @Namespace private var glass
    /// Where the finger is while dragging the selection, in pill coordinates.
    @State private var dragX: CGFloat?
    @State private var hovered: Place?

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onMenu) {
                Image(systemName: "line.3.horizontal")
                    .font(.body.weight(.medium))
                    .foregroundStyle(palette.tinta)
                    .glassCircle(palette, size: 44)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Caderno, Mac e Ajustes")
            Spacer(minLength: 0)
            pill
            Spacer(minLength: 0)
            Button { onPlace(.ajustes) } label: {
                Text((agentName ?? "Visão").prefix(1).uppercased())
                    .font(Typo.text(.callout, weight: .medium))
                    .foregroundStyle(Color(rgb: 0xf4f7f8))
                    .frame(width: 44, height: 44)
                    .liquidGlass(palette, in: Circle(), tint: place == .ajustes ? palette.pilulaAtiva : palette.estanho.opacity(0.9))
                    .overlay {
                        if place == .ajustes { Circle().strokeBorder(palette.vidroForte, lineWidth: 2.5).padding(-3) }
                    }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Ajustes")
        }
        .padding(.horizontal, 12)
        .padding(.top, 6)
        .padding(.bottom, 6)
    }

    private var pill: some View {
        let width: CGFloat = 264
        let segment = (width - 8) / CGFloat(Place.tabs.count)
        let selectedIndex = Place.tabs.firstIndex(of: place)
        return ZStack(alignment: .leading) {
            // The selection: a dark glass drop that slides to the tab (and stretches a little
            // while you drag it, like the system tab bar).
            if selectedIndex != nil || dragX != nil {
                let x = thumbX(segment: segment, selected: selectedIndex ?? 1)
                Capsule()
                    .fill(palette.pilulaAtiva)
                    .frame(width: segment, height: 38)
                    .frame(height: 44)
                    .scaleEffect(dragX == nil ? 1 : 1.12)
                    .offset(x: x)
                    .shadow(color: .black.opacity(dragX == nil ? 0.12 : 0.22), radius: dragX == nil ? 4 : 10, y: 2)
                    .animation(.spring(response: 0.38, dampingFraction: 0.78), value: place)
                    .animation(.interactiveSpring(response: 0.25, dampingFraction: 0.86), value: dragX)
            }
            HStack(spacing: 0) {
                ForEach(Place.tabs, id: \.self) { tab in
                    let lit = (hovered ?? place) == tab
                    HStack(spacing: 5) {
                        Text(tab.tabLabel)
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
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
                    .font(Typo.text(.subheadline, weight: lit ? .medium : .regular))
                    .foregroundStyle(lit ? palette.pilulaAtivaTinta : palette.tintaFraca)
                    .frame(width: segment, height: 44) // touch target: 44 pt, the drop is drawn at 38
                    .contentShape(Rectangle())
                    .onTapGesture { onPlace(tab) }
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(place == tab ? [.isButton, .isSelected] : .isButton)
                    .accessibilityAction { onPlace(tab) }
                    .animation(.easeOut(duration: 0.18), value: lit)
                }
            }
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 1)
        .frame(width: width)
        .liquidGlass(palette, in: Capsule(), interactive: false)
        .gesture(
            DragGesture(minimumDistance: 6)
                .onChanged { value in
                    dragX = min(max(value.location.x - 4 - segment / 2, 0), segment * CGFloat(Place.tabs.count - 1))
                    let next = Place.tabs[min(Place.tabs.count - 1, max(0, Int(((dragX ?? 0) + segment / 2) / segment)))]
                    if next != hovered { hovered = next }
                }
                .onEnded { _ in
                    let chosen = hovered
                    dragX = nil
                    hovered = nil
                    if let chosen { onPlace(chosen) }
                }
        )
        .sensoryFeedback(.selection, trigger: hovered) { _, now in now != nil }
        .sensoryFeedback(.impact(weight: .light), trigger: place)
    }

    private func thumbX(segment: CGFloat, selected: Int) -> CGFloat {
        dragX ?? segment * CGFloat(selected)
    }
}

/// The drawer: the brand, what is not in the tabs on top (Caderno, Mac, Ajustes), and whether we
/// are connected. There is no list of conversations (docs/CONVERSA_CONTINUA.md). Drag it to the
/// left or tap outside to close.
struct Drawer: View {
    @Binding var open: Bool
    let place: Place
    let onPlace: (Place) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var drag: CGFloat = 0

    private let items: [(Place, String, String)] = [
        (.caderno, "Caderno", "book.closed"),
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
                        }
                        .font(Typo.text(.subheadline, weight: .medium))
                        .foregroundStyle(place == item ? palette.tinta : palette.tintaSuave)
                        .padding(.horizontal, 10)
                        .frame(minHeight: 44)
                        .background(place == item ? palette.fundoHover : .clear, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            Spacer(minLength: 0)
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
        .liquidGlass(palette, in: RoundedRectangle(cornerRadius: 30, style: .continuous), tint: palette.vidroForte.opacity(0.7), interactive: false)
        .padding(.leading, 12)
        .padding(.vertical, 12)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Navegação")
        .accessibilityAction(.escape) { close() }
    }
}
