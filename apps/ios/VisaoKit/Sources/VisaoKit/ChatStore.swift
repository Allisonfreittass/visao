import Foundation
import Observation

/// One conversation on screen: what you sent shows at once, what you write while it answers waits
/// (dimmed) and goes as one message after the reply, and the turn in flight says what it is doing.
/// Same rules as `send` in apps/web/src/App.tsx.
@MainActor
@Observable
public final class ChatStore {
    public private(set) var conversationId: String?
    /// A new conversation started from a project is created inside it.
    public let projectId: String?
    public private(set) var messages: [Message] = []
    public private(set) var sending = false
    /// What the turn in flight is doing now; nil reads "Pensando".
    public private(set) var liveStep: ProgressStep?
    public private(set) var liveSteps: [ProgressStep] = []
    /// In a voice call, the reply written so far, so the call can start speaking before it ends.
    public private(set) var liveDraft: String?
    public var error: String?
    public private(set) var loading = false
    /// Set by the screen from the scene phase: progress is only asked for while you look, so the
    /// server notices a locked phone and also sends the reply as a notification (docs/STATUS.md).
    public var isVisible = true
    /// The lock-screen card (Live Activity) keeps following the turn for the little time the
    /// iPhone gives an app after it leaves the screen; the server still notifies once it stops.
    public var followInBackground = false
    /// Called when a conversation is created by the first message (the list adds it).
    public var onConversationCreated: ((Conversation) -> Void)?
    /// Called with every API error, so a 401 can send the app back to the login screen.
    public var onError: ((Error) -> Void)?

    private let api: APIClient
    private let progressInterval: Duration
    private var queue: [Queued] = []
    private var turnTask: Task<Turn, Error>?
    private var watchTask: Task<Void, Never>?
    private var counter = 0

    struct Queued {
        let id: String
        let text: String
        let attachments: [Attachment]
        let replyTo: Message?
    }

    private let artifactInterval: Duration
    private var artifactTask: Task<Void, Never>?

    public init(
        api: APIClient, conversationId: String?, projectId: String? = nil, progressInterval: Duration = .milliseconds(900),
        artifactInterval: Duration = .seconds(3)
    ) {
        self.api = api
        self.conversationId = conversationId
        self.projectId = projectId
        self.progressInterval = progressInterval
        self.artifactInterval = artifactInterval
    }

    public func load() async {
        guard let conversationId else { return }
        loading = true
        defer { loading = false }
        do {
            let stored = try await api.messages(conversationId: conversationId)
            messages = merge(stored: stored)
            watchPages()
        } catch {
            report(error)
        }
    }

    /// Picks up what it said on its own while you were away, keeping what was never sent.
    public func refresh() async {
        guard let conversationId, !sending else { return }
        guard let stored = try? await api.messages(conversationId: conversationId), !sending else { return }
        let next = merge(stored: stored)
        if next.map(\.id) != messages.map(\.id) {
            messages = next
            watchPages()
        }
    }

    private func merge(stored: [Message]) -> [Message] {
        // Sources only come with the turn; keep them for replies received in this session.
        let known = Dictionary(messages.map { ($0.id, $0.sources) }, uniquingKeysWith: { a, _ in a })
        let withSources = stored.map { message -> Message in
            var m = message
            if let sources = known[m.id], !sources.isEmpty { m.sources = sources }
            return m
        }
        return withSources + messages.filter { $0.local == .failed || $0.local == .queued || $0.local == .stopped }
    }

    public var canStop: Bool { sending && turnTask != nil }

    /// Sends now, or queues it if a reply is still being written. A photo alone is a message.
    public func send(_ rawText: String, attachments: [Attachment] = [], replyTo: Message? = nil, spoken: Bool = false) {
        let text = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty || !attachments.isEmpty else { return }
        let files = Array(attachments.prefix(AttachmentRules.maxPerMessage))
        error = nil
        // `/mac projeto pedido`: work for the Mac, not a message to him (as on the web).
        if attachments.isEmpty, !sending, let command = MacCommand.parse(text) {
            switch command {
            case .usage: error = MacCommand.usageText
            case .ask(let project, let prompt): Task { await askMac(project: project, prompt: prompt) }
            }
            return
        }
        if sending {
            counter += 1
            let id = "queued-\(counter)"
            queue.append(Queued(id: id, text: text, attachments: files, replyTo: replyTo))
            messages.append(Message(id: id, role: .user, content: text, createdAt: Date(), attachments: files, replyTo: replyTo?.quoted, local: .queued))
            return
        }
        Task { await run(text: text, attachments: files, replyTo: replyTo, spoken: spoken) }
    }

    private func askMac(project: String, prompt: String) async {
        sending = true
        defer { sending = false }
        do {
            let id = try await ensureConversation()
            _ = try await api.askArm(project: project, prompt: prompt, conversationId: id)
            messages = merge(stored: try await api.messages(conversationId: id))
        } catch {
            report(error)
        }
    }

    /// The page is gone: its link stops working, and the card leaves the reply.
    public func deleteArtifact(_ artifact: Artifact) async {
        do {
            try await api.deleteArtifact(id: artifact.id)
            for index in messages.indices where messages[index].artifact?.id == artifact.id {
                messages[index].artifact = nil
            }
        } catch {
            report(error)
        }
    }

    /// Pages still being written ("Criando…") are checked every few seconds while you look.
    private func watchPages() {
        let pending = messages.compactMap { $0.artifact?.status == "pending" ? $0.artifact?.id : nil }
        artifactTask?.cancel()
        guard !pending.isEmpty else { return }
        let api = self.api
        let interval = artifactInterval
        artifactTask = Task { [weak self] in
            var waiting = Set(pending)
            while !waiting.isEmpty, !Task.isCancelled {
                try? await Task.sleep(for: interval)
                guard let self, !Task.isCancelled else { return }
                guard self.isVisible else { continue }
                for id in waiting {
                    guard let fresh = try? await api.artifact(id: id), fresh.status != "pending" else { continue }
                    waiting.remove(id)
                    for index in self.messages.indices where self.messages[index].artifact?.id == id {
                        self.messages[index].artifact = fresh
                    }
                }
            }
        }
    }

    /// Parar: tell the server, and stop waiting at once.
    public func stop() {
        guard let turnTask, let conversationId else { return }
        let api = self.api
        Task { try? await api.cancel(conversationId: conversationId) }
        turnTask.cancel()
    }

    private func run(text: String, attachments: [Attachment], replyTo: Message?, spoken: Bool = false) async {
        counter += 1
        let localId = "local-\(counter)"
        let optimistic = Message(id: localId, role: .user, content: text, createdAt: Date(), attachments: attachments, replyTo: replyTo?.quoted, local: .sending)
        messages.append(optimistic)
        sending = true
        defer {
            turnTask = nil
            watchTask?.cancel()
            watchTask = nil
            liveStep = nil
            liveSteps = []
            liveDraft = nil
            sending = false
            flushQueue()
        }

        let id: String
        do {
            id = try await ensureConversation()
        } catch {
            report(error)
            mark(localId, .failed)
            return
        }
        liveDraft = nil
        // Spoken: asked more often, since every sentence of the draft is heard as soon as it ends.
        startWatching(id, every: spoken ? .milliseconds(300) : progressInterval)
        let api = self.api
        let attachmentIds = attachments.map(\.id)
        let task = Task { try await api.send(conversationId: id, content: text, modality: spoken ? "voice" : "text", attachmentIds: attachmentIds, replyToId: replyTo?.id) }
        turnTask = task
        do {
            let turn = try await task.value
            var reply = turn.assistantMessage
            reply.sources = turn.sources
            let waiting = messages.filter { $0.local == .queued }
            messages = messages.filter { $0.id != localId && $0.local != .queued } + [turn.userMessage, reply] + waiting
            if reply.artifact?.status == "pending" { watchPages() }
        } catch {
            let stopped = error is CancellationError || (error as? APIError)?.isStoppedByOwner == true
            if !stopped { report(error) }
            let state: Message.LocalState = stopped ? .stopped : .failed
            mark(localId, state)
            // The message may have been stored even if the reply failed: reload, keeping the one
            // that never arrived visible so it is not silently lost.
            if let stored = try? await api.messages(conversationId: id) {
                let lastUser = stored.last(where: { $0.role == .user })
                let arrived = lastUser.map { $0.content == text && $0.createdAt >= optimistic.createdAt.addingTimeInterval(-5) } ?? false
                let waiting = messages.filter { $0.local == .queued }
                var failed = optimistic
                failed.local = state
                messages = (arrived ? stored : stored + [failed]) + waiting
            }
        }
    }

    /// Everything written meanwhile goes as one message: one answer to all of it.
    private func flushQueue() {
        guard !queue.isEmpty else { return }
        let batch = queue
        queue = []
        let ids = Set(batch.map(\.id))
        messages.removeAll { ids.contains($0.id) }
        let text = batch.map(\.text).filter { !$0.isEmpty }.joined(separator: "\n\n")
        let files = Array(batch.flatMap(\.attachments).prefix(AttachmentRules.maxPerMessage))
        let replyTo = batch.first(where: { $0.replyTo != nil })?.replyTo
        Task { await run(text: text, attachments: files, replyTo: replyTo) }
    }

    private func ensureConversation() async throws -> String {
        if let conversationId { return conversationId }
        let created = try await api.createConversation(projectId: projectId)
        conversationId = created.id
        if created.memoryUnavailable {
            error = "Não consegui preparar a memória desta vez. Dá para conversar, mas posso esquecer detalhes."
        }
        onConversationCreated?(created)
        return created.id
    }

    private func startWatching(_ id: String, every interval: Duration) {
        let api = self.api
        watchTask = Task { [weak self] in
            while !Task.isCancelled {
                if self?.isVisible == true || self?.followInBackground == true, let progress = try? await api.progress(conversationId: id) {
                    guard let self, !Task.isCancelled else { return }
                    if progress.active, let last = progress.steps.last {
                        self.liveStep = last
                        self.liveSteps = progress.steps
                    }
                    if progress.active, let draft = progress.draft, !draft.isEmpty { self.liveDraft = draft }
                }
                try? await Task.sleep(for: interval)
            }
        }
    }

    private func mark(_ id: String, _ state: Message.LocalState) {
        if let index = messages.firstIndex(where: { $0.id == id }) { messages[index].local = state }
    }

    private func report(_ error: Error) {
        self.error = (error as? LocalizedError)?.errorDescription ?? "Algo deu errado"
        onError?(error)
    }
}
