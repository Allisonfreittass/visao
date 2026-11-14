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
    @State private var call: CallController?
    /// "Falar as respostas", outside a call.
    @State private var speaker = VoiceEngine()
    @State private var spokenIds: Set<String> = []
    @FocusState private var composerFocused: Bool

    enum Picker: Identifiable {
        case photos, camera, files
        var id: Self { self }
    }

    /// It can speak first: what it said on its own shows up while you look (as on the web).
    private static let initiativePoll: Duration = .seconds(15)

    /// Told when the first message creates the conversation, so the drawer marks it.
    private let onCreated: (Conversation) -> Void

    /// In front: the progress and the openings are only looked at while you see this chat.
    private let isActive: Bool

    init(api: APIClient, conversationId: String?, projectId: String? = nil, isActive: Bool = true, onCreated: @escaping (Conversation) -> Void = { _ in }) {
        self.isActive = isActive
        _store = State(initialValue: ChatStore(api: api, conversationId: conversationId, projectId: projectId))
        self.onCreated = onCreated
        _draft = State(initialValue: AttachmentDraft(api: api))
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if store.messages.isEmpty && !store.sending && !store.loading {
                        EmptyConversation()
                    }
                    ForEach(store.messages) { message in
                        MessageRow(
                            message: message,
                            speaker: session.speakerName,
                            onReply: { reply(to: message) },
                            onQuoteTap: { id in withAnimation { proxy.scrollTo(id, anchor: .center) } },
                            onOpenPage: { viewing = $0 },
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
                        .id(message.id)
                    }
                    if store.sending {
                        LiveStatusView(step: store.liveStep, canStop: store.canStop, onStop: store.stop)
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
                    Color.clear.frame(height: 1).id(Self.bottomId)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 12)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) {
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
                    onSend: send
                )
            }
            .onChange(of: store.messages.count) { scrollToBottom(proxy) }
            .onChange(of: store.sending) { _, sending in
                scrollToBottom(proxy)
                if !sending { speakReplyIfAsked() }
                // A turn can leave an email or Mac work waiting for a tap.
                if !sending { Task { await session.pending.refresh() } }
            }
            .onChange(of: session.pending.asks(in: store.conversationId).count) { scrollToBottom(proxy) }
            .onChange(of: store.liveStep) { scrollToBottom(proxy) }
            .onChange(of: draft.items.count) { scrollToBottom(proxy) }
            .onChange(of: composerFocused) { _, focused in
                if focused { scrollToBottom(proxy, delay: .milliseconds(250)) }
            }
        }
        .overlay(alignment: .topTrailing) {
            // The Bancada: what he really did here, the pages and the sites he read.
            if store.conversationId != nil {
                Button { benchOpen = true } label: {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(palette.tinta)
                        .glassCircle(palette, size: 38)
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
            store.onConversationCreated = { conversation in
                session.added(conversation)
                onCreated(conversation)
            }
            await store.load()
            await session.pending.refresh()
            // What he said on his own is right here: it stops counting as a notice.
            await session.pending.markOpeningsRead()
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

    private func startCall() {
        speaker.stopSpeaking()
        composerFocused = false
        call = CallController(chat: store, pending: session.pending)
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

    private func reply(to message: Message) {
        replyTo = message
        composerFocused = true
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy, delay: Duration = .zero) {
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

/// "Pensando" or the step the server says it is on, in his bubble, with Parar; the detail (the
/// term searched, the site) in a glass pill below.
struct LiveStatusView: View {
    let step: ProgressStep?
    let canStop: Bool
    let onStop: () -> Void
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                ThinkingDots(color: palette.tintaFraca)
                Text(step?.label ?? "Pensando")
                    .font(Typo.text(.subheadline))
                    .foregroundStyle(palette.tintaFraca)
                    .contentTransition(.opacity)
                    .animation(.easeInOut, value: step?.label)
                if canStop {
                    Button(action: onStop) {
                        Image(systemName: "xmark")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(palette.tintaSuave)
                            .frame(width: 28, height: 28)
                            .background(palette.fundoHover, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Parar")
                }
            }
            .padding(.leading, 20)
            .padding(.trailing, canStop ? 10 : 20)
            .padding(.vertical, canStop ? 10 : 16)
            .background(palette.bolhaDele, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .shadow(color: palette.sombra, radius: 11, y: 6)

            if let detail = step?.detail, !detail.isEmpty {
                Text(detail)
                    .font(Typo.text(.subheadline))
                    .foregroundStyle(palette.tintaSuave)
                    .lineLimit(2)
                    .padding(.horizontal, 22)
                    .padding(.vertical, 12)
                    .glass(palette, cornerRadius: 999, shadow: false)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(step?.label ?? "Pensando")
    }
}

private struct CallBox: Identifiable {
    let controller: CallController
    var id: ObjectIdentifier { ObjectIdentifier(controller) }
}
