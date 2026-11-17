import PhotosUI
import SwiftUI
import VisaoKit

struct ChatScreen: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.scenePhase) private var scenePhase
    @State private var store: ChatStore
    @State private var draft: AttachmentDraft
    @State private var text = ""
    @State private var replyTo: Message?
    @State private var viewing: Artifact?
    @State private var picker: Picker?
    @State private var pickedPhotos: [PhotosPickerItem] = []
    @State private var benchOpen = false
    /// Whether you are at the end of the conversation: new things only pull the list down then.
    @State private var atBottom = true
    /// Following the end: set when you send, kept while the reply grows, and decided again only
    /// when you scroll yourself (a growing reply never counts as you leaving the end).
    @State private var stick = true
    /// Haptics: a light tap when you send, a very soft one when the reply has all arrived.
    @State private var sentCount = 0
    @State private var settledCount = 0
    /// The message box's real height (it grows with lines, a quote, files): the list keeps that
    /// much room at its end, so the last message is never behind it.
    @State private var composerHeight: CGFloat = 76
    /// The first load is placed at the end without the entrance animation: animated, the list
    /// was still moving when it scrolled, and the conversation opened at its start.
    @State private var opened = false
    @State private var shownCount = ChatScreen.page
    private static let page = 60
    @State private var call: CallController?
    /// "Falar as respostas", outside a call.
    @State private var speaker = VoiceEngine()
    @State private var spokenIds: Set<String> = []
    @FocusState private var composerFocused: Bool
    /// Bumped when a turn ends in a project's chat: its card loads the new notes.
    @State private var cardRefresh = 0

    enum Picker: Identifiable {
        case photos, camera, files
        var id: Self { self }
    }

    /// It can speak first: what it said on its own shows up while you look (as on the web).
    private static let initiativePoll: Duration = .seconds(15)

    /// Told when the first message creates the conversation (the continuous one, the first time).
    private let onCreated: (Conversation) -> Void

    /// In front: the progress and the openings are only looked at while you see this chat.
    private let isActive: Bool

    /// "Abrir o projeto «…» →" under a reply, and the project card's way back.
    private let onOpenProject: (String) -> Void
    private let onBackToProjects: () -> Void
    private let onProjectDeleted: () -> Void

    init(
        api: APIClient, conversationId: String?, projectId: String? = nil, continuous: Bool = false, isActive: Bool = true,
        onCreated: @escaping (Conversation) -> Void = { _ in }, onOpenProject: @escaping (String) -> Void = { _ in },
        onBackToProjects: @escaping () -> Void = {}, onProjectDeleted: @escaping () -> Void = {}
    ) {
        self.isActive = isActive
        self.onOpenProject = onOpenProject
        self.onBackToProjects = onBackToProjects
        self.onProjectDeleted = onProjectDeleted
        _store = State(initialValue: ChatStore(api: api, conversationId: conversationId, projectId: projectId, paged: continuous))
        self.onCreated = onCreated
        _draft = State(initialValue: AttachmentDraft(api: api))
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                // A plain stack: a lazy one measured older messages only as they scrolled into
                // view, and the list jumped. The last ones are drawn; older ones on request.
                VStack(alignment: .leading, spacing: 14) {
                    if store.messages.isEmpty && !store.sending && !store.loading {
                        EmptyConversation()
                    }
                    if store.messages.count > shownCount || store.olderLeft {
                        Button {
                            // What is already here first; then the page before it, from the server.
                            if store.messages.count > shownCount {
                                shownCount += Self.page
                            } else {
                                Task {
                                    await store.loadOlder()
                                    shownCount = store.messages.count
                                }
                            }
                        } label: {
                            Text(store.loadingOlder ? "Carregando…" : "Carregar mensagens anteriores")
                                .font(Typo.text(.footnote, weight: .medium))
                                .padding(.horizontal, 14)
                                .frame(minHeight: 34)
                                .glass(palette, cornerRadius: 999, strong: false, shadow: false)
                                .frame(minHeight: 44)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity)
                    }
                    ForEach(store.messages.suffix(shownCount).filter { $0.id != store.settlingId }) { message in
                        MessageRow(
                            message: message,
                            speaker: session.speakerName,
                            onReply: { reply(to: message) },
                            onQuoteTap: { id in withAnimation { proxy.scrollTo(id, anchor: .center) } },
                            onOpenPage: { viewing = $0 },
                            projectName: message.projectId.flatMap { session.projectNames[$0] },
                            onOpenProject: message.projectId == nil || message.projectId == store.projectId ? nil : onOpenProject,
                            onFeedback: { positive, tags in
                                do {
                                    let changed = try await session.api.feedback(messageId: message.id, positive: positive, tags: tags)
                                    return changed ? "Valeu. Ajustei meu jeito de responder." : "Valeu."
                                } catch {
                                    session.handle(error)
                                    return nil
                                }
                            }
                        )
                        .equatable()
                        .id(message.id)
                        .transition(.asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity), removal: .opacity))
                    }
                    if store.sending || store.settlingId != nil {
                        LiveBubble(
                            step: store.liveStep,
                            text: store.liveText ?? "",
                            settling: store.settlingId != nil && !store.sending,
                            canStop: store.canStop,
                            onStop: store.stop,
                            onSettled: {
                                store.finishSettling()
                                if scenePhase == .active && isActive { settledCount += 1 }
                            }
                        )
                        .id("live")
                        .transition(.opacity)
                    }
                    ForEach(session.pending.asks(in: store.conversationId)) { ask in
                        ActionCard(ask: ask, busy: session.pending.deciding.contains(ask.id)) { approve in
                            decide(ask, approve: approve)
                        }
                        .id(ask.id)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                    }
                    if let error = store.error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.erro)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .glass(palette, cornerRadius: 16, strong: true, shadow: false)
                    }
                    // The room for the message box, as part of the content: "the end" is below it.
                    Color.clear.frame(height: composerHeight).id(Self.bottomId)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 12)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            // Real case (14/11/2026): with the box in safeAreaInset the list did not get the room,
            // and the end of the last reply stayed behind the box. The box now floats over the
            // list, and the list ends with a spacer as tall as the box (measured).
            .contentMargins(.bottom, composerHeight, for: .scrollIndicators)
            .modifier(BottomAnchor(atBottom: $atBottom, stick: stick))
            .onScrollPhaseChange { old, new in
                // Only your own scrolling decides whether the list follows the end.
                if new == .idle, old == .interacting || old == .decelerating { stick = atBottom }
            }
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .top, spacing: 6) {
                if let projectId = store.projectId {
                    ProjectCard(
                        projectId: projectId, refreshKey: cardRefresh, onBack: onBackToProjects,
                        onDeleted: onProjectDeleted, onOpenPage: { viewing = $0 },
                        onBench: store.conversationId == nil ? nil : { benchOpen = true }
                    )
                }
            }
            .animation(opened ? .spring(response: 0.35, dampingFraction: 0.9) : nil, value: store.messages.count)
            .overlay(alignment: .bottom) {
                Composer(
                    text: $text,
                    replyTo: $replyTo,
                    focused: $composerFocused,
                    draft: draft,
                    thinking: store.sending,
                    speaker: session.speakerName,
                    placeholder: "Enviar mensagem para \(session.agentName ?? "o Visão")",
                    onPick: { picker = $0 },
                    onCall: { startCall() },
                    live: call != nil,
                    offline: session.listError != nil,
                    onSend: send
                )
                // A box that grows (more lines, a quote, files) never covers the end.
                .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height in
                    composerHeight = height
                    scrollToBottom(proxy, force: stick)
                }
            }
            .sensoryFeedback(.impact(weight: .light), trigger: sentCount)
            .sensoryFeedback(.impact(flexibility: .soft, intensity: 0.4), trigger: settledCount)
            // The messages arrive after the screen opens: once loaded, open at the last one.
            .onChange(of: store.loading) { _, loading in
                if !loading { jumpToEnd(proxy) }
            }
            .overlay(alignment: .bottomTrailing) {
                // Reading further up: one tap back to the end, as in Messages.
                if !atBottom && !store.messages.isEmpty {
                    Button { jumpToEnd(proxy, animated: true) } label: {
                        Image(systemName: "chevron.down")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(palette.tinta)
                            .glassCircle(palette, size: 44)
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 16)
                    .padding(.bottom, composerHeight + 8)
                    .transition(.scale.combined(with: .opacity))
                    .accessibilityLabel("Ir para a última mensagem")
                }
            }
            .animation(.spring(duration: 0.3), value: atBottom)
            .onChange(of: store.messages.count) { old, new in
                // What you just sent always comes into view.
                let mine = new > old && store.messages.last?.local == .sending
                scrollToBottom(proxy, force: mine)
            }
            .onChange(of: store.liveText) { scrollToBottom(proxy, force: stick) }
            .onChange(of: session.chatDraft) { _, draftText in
                guard let draftText else { return }
                text = draftText
                composerFocused = true
                session.chatDraft = nil
            }
            .onChange(of: store.settlingId) { scrollToBottom(proxy, force: stick) }
            .onChange(of: store.sending) { _, sending in
                scrollToBottom(proxy, force: stick)
                if !sending { speakReplyIfAsked() }
                followOnLockScreen(sending: sending)
                // A turn can leave an email or Mac work waiting for a tap.
                if !sending { Task { await session.pending.refresh() } }
                if !sending { afterTurn() }
            }
            .onChange(of: session.pending.asks(in: store.conversationId).count) { scrollToBottom(proxy) }
            .onChange(of: store.liveStep) { scrollToBottom(proxy) }
            .onChange(of: draft.items.count) { scrollToBottom(proxy) }
            .onChange(of: composerFocused) { _, focused in
                if focused { scrollToBottom(proxy, delay: .milliseconds(250), force: true) }
            }
        }
        .overlay(alignment: .topTrailing) {
            // The Bancada: what he really did here, the pages and the sites he read.
            if store.conversationId != nil && store.projectId == nil {
                Button { benchOpen = true } label: {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(palette.tinta)
                        .glassCircle(palette, size: 44)
                }
                .buttonStyle(.plain)
                .padding(.trailing, 14)
                .padding(.top, 4)
                .accessibilityLabel("Bancada: o que ele fez nesta conversa")
            }
        }
        .fullScreenCover(item: Binding(get: { call.map(CallBox.init) }, set: { call = $0?.controller })) { box in
            CallView(controller: box.controller, agentName: session.agentName, messages: store.messages)
        }
        .sheet(isPresented: $benchOpen) {
            if let id = store.conversationId {
                BenchSheet(conversationId: id, working: store.sending, steps: store.liveSteps) { artifact in
                    benchOpen = false
                    viewing = artifact
                }
                .presentationDetents([.medium, .large])
                .presentationBackground(.thinMaterial)
            }
        }
        .environment(\.attachmentLoader, session.loader)
        .sheet(item: $viewing) { artifact in
            if let path = artifact.path {
                PageSheet(artifact: artifact, url: session.api.pageURL(path: path)) {
                    Task { await store.deleteArtifact(artifact) }
                }
            }
        }
        .photosPicker(
            isPresented: Binding(get: { picker == .photos }, set: { if !$0 { picker = nil } }),
            selection: $pickedPhotos,
            maxSelectionCount: max(draft.room, 1),
            matching: .images,
            preferredItemEncoding: .compatible
        )
        .fullScreenCover(isPresented: Binding(get: { picker == .camera }, set: { if !$0 { picker = nil } })) {
            CameraPicker { data in draft.addImage(data, filename: photoName(index: 0, ext: "jpg")) }
                .ignoresSafeArea()
        }
        .fileImporter(
            isPresented: Binding(get: { picker == .files }, set: { if !$0 { picker = nil } }),
            allowedContentTypes: AttachmentRules.documentTypes,
            allowsMultipleSelection: true
        ) { result in
            guard case .success(let urls) = result else { return }
            for url in urls.prefix(draft.room) { addFile(url) }
        }
        .onChange(of: pickedPhotos) { _, items in
            guard !items.isEmpty else { return }
            pickedPhotos = []
            Task {
                for (index, item) in items.prefix(draft.room).enumerated() {
                    guard let data = try? await item.loadTransferable(type: Data.self) else { continue }
                    let ext = item.supportedContentTypes.first?.preferredFilenameExtension ?? "jpg"
                    draft.addImage(data, filename: photoName(index: index, ext: ext))
                }
            }
        }
        .task {
            store.onError = { session.handle($0) }
            // Only with the switch on and a "perto de mim" text; the position goes with that one
            // message and is kept nowhere.
            store.locate = { text in
                await LocationPrefs.position(for: text, enabled: LocationPrefs.enabled(), source: DevicePosition())
            }
            store.onAction = { Task { await session.pending.refresh() } }
            store.onConversationCreated = { conversation in
                session.added(conversation)
                onCreated(conversation)
            }
            await store.load()
            // A new conversation has nothing to place: what comes next animates in.
            if store.messages.isEmpty { opened = true }
            await speaker.prepare(api: session.api)
            await session.pending.refresh()
            // What he said on his own is right here: it stops counting as a notice.
            await session.pending.markOpeningsRead()
        }
        .onChange(of: store.liveSteps) { _, steps in LiveTurn.shared.update(steps) }
        .onChange(of: scenePhase) { _, phase in
            // Leaving mid-turn: keep the card going for the seconds the iPhone allows.
            let away = phase != .active && store.sending
            store.followInBackground = away
            if away { LiveTurn.shared.beginBackgroundTime() }
        }
        .task(id: [scenePhase == .active, isActive]) {
            store.isVisible = scenePhase == .active && isActive
            guard store.isVisible else { return }
            await store.refresh()
            await session.pending.markOpeningsRead()
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.initiativePoll)
                await store.refresh()
                await session.pending.refresh()
                await session.pending.markOpeningsRead()
            }
        }
    }

    private static let bottomId = "bottom"

    private var canSend: Bool {
        !draft.isUploading && (!text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !draft.ready.isEmpty)
    }

    private func send() {
        guard canSend else { return }
        stick = true
        sentCount += 1
        store.send(text, attachments: draft.ready, replyTo: replyTo)
        text = ""
        replyTo = nil
        draft.clear()
    }

    private func addFile(_ url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else { return }
        draft.addFile(data, filename: url.lastPathComponent)
    }

    /// The Live Activity: starts with the turn, ends with the reply (docs/APP_IOS.md, stage 7).
    private func followOnLockScreen(sending: Bool) {
        if sending {
            LiveTurn.shared.start(agentName: session.agentName, conversationId: store.conversationId)
            return
        }
        let reply = store.messages.last { $0.role == .assistant }
        let stopped = store.messages.last { $0.role == .user }?.local
        let failed = stopped == .failed || stopped == .stopped
        LiveTurn.shared.finish(
            reply: failed ? (store.error ?? "Parou antes de responder.") : reply?.content,
            failed: failed,
            onScreen: scenePhase == .active
        )
        store.followInBackground = false
    }

    private func startCall() {
        speaker.stopSpeaking()
        composerFocused = false
        call = CallController(chat: store, pending: session.pending, api: session.api)
    }

    /// With "Falar as respostas" on, a reply received here is read aloud (never inside a call,
    /// which speaks for itself).
    private func speakReplyIfAsked() {
        guard VoicePrefs.speakReplies, call == nil, isActive,
              let reply = store.messages.last(where: { $0.role == .assistant }),
              !spokenIds.contains(reply.id) else { return }
        spokenIds.insert(reply.id)
        speaker.speak(VoiceRules.speakable(reply.content))
    }

    private func decide(_ ask: PendingAsk, approve: Bool) {
        Task {
            let ok = await session.pending.decide(ask, approve: approve)
            // What was sent or scheduled comes back as his message in this conversation.
            if ok && approve { await store.refresh() }
        }
    }

    /// A turn ended: the project card reloads (new notes), and a project the reply names but the
    /// app does not know yet gets its name.
    private func afterTurn() {
        if store.projectId != nil { cardRefresh += 1 }
        if store.messages.contains(where: { $0.projectId.map { session.projectNames[$0] == nil } ?? false }) {
            Task { await session.loadProjectNames() }
        }
    }

    private func reply(to message: Message) {
        replyTo = message
        composerFocused = true
    }

    /// To the last message, without animation when the conversation opens; twice, because long
    /// replies finish measuring a moment after the first pass.
    private func jumpToEnd(_ proxy: ScrollViewProxy, animated: Bool = false) {
        Task {
            await Task.yield()
            if animated {
                withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo(Self.bottomId, anchor: .bottom) }
            } else {
                // Again as long replies and the box finish measuring.
                for wait in [0, 120, 350] {
                    if wait > 0 { try? await Task.sleep(for: .milliseconds(wait)) }
                    proxy.scrollTo(Self.bottomId, anchor: .bottom)
                }
            }
            atBottom = true
            stick = true
            opened = true
        }
    }

    /// Follows the end of the conversation only when you are there (or just sent something):
    /// reading further up, nothing yanks the list.
    private func scrollToBottom(_ proxy: ScrollViewProxy, delay: Duration = .zero, force: Bool = false) {
        guard atBottom || force else { return }
        Task {
            if delay > .zero { try? await Task.sleep(for: delay) }
            withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(Self.bottomId, anchor: .bottom) }
        }
    }
}

private struct EmptyConversation: View {
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(spacing: 10) {
            Rotulo("Conversa nova")
            (Text("Por onde a gente ").font(Typo.display(30, relativeTo: .title))
                + Text("começa?").font(Typo.display(30, relativeTo: .title, italic: true)))
                .multilineTextAlignment(.center)
            Text("Um bug, uma ideia pela metade, um plano. Pode escrever, colar código, mandar uma foto ou um arquivo.")
                .font(Typo.text(.callout))
                .foregroundStyle(palette.tintaSuave)
                .multilineTextAlignment(.center)
        }
        .padding(28)
        .frame(maxWidth: .infinity)
        .glass(palette, cornerRadius: 32)
        .padding(.top, 60)
        .accessibilityElement(children: .combine)
    }
}

private struct CallBox: Identifiable {
    let controller: CallController
    var id: ObjectIdentifier { ObjectIdentifier(controller) }
}

/// Opens at the end of the conversation and knows whether you are still there. On iOS 18+ the
/// list keeps its place when something above grows, instead of re-pinning to the bottom.
private struct BottomAnchor: ViewModifier {
    @Binding var atBottom: Bool
    let stick: Bool

    func body(content: Content) -> some View {
        if #available(iOS 18.0, *) {
            content
                .defaultScrollAnchor(.bottom, for: .initialOffset)
                // At the end, growth keeps you at the end; reading above, nothing moves.
                .defaultScrollAnchor(atBottom || stick ? .bottom : nil, for: .sizeChanges)
                .onScrollGeometryChange(for: Bool.self) { geometry in
                    let distance = geometry.contentSize.height - geometry.visibleRect.maxY
                    return distance < 80
                } action: { _, isNear in
                    if isNear != atBottom { atBottom = isNear }
                }
        } else {
            content.defaultScrollAnchor(.bottom)
        }
    }
}
