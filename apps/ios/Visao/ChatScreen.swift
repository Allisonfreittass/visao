import SwiftUI
import VisaoKit

struct ChatScreen: View {
    @Environment(Session.self) private var session
    @Environment(\.scenePhase) private var scenePhase
    @State private var store: ChatStore
    @State private var draft = ""
    @State private var replyTo: Message?
    @FocusState private var composerFocused: Bool

    /// It can speak first: what it said on its own shows up while you look (as on the web).
    private static let initiativePoll: Duration = .seconds(15)

    init(api: APIClient, conversationId: String?) {
        _store = State(initialValue: ChatStore(api: api, conversationId: conversationId))
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
                            onQuoteTap: { id in withAnimation { proxy.scrollTo(id, anchor: .center) } }
                        )
                        .id(message.id)
                    }
                    if store.sending {
                        LiveStatusView(step: store.liveStep, canStop: store.canStop, onStop: store.stop)
                            .id(Self.liveId)
                    }
                    if let error = store.error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .accessibilityAddTraits(.isStaticText)
                    }
                    Color.clear.frame(height: 1).id(Self.bottomId)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
            }
            .defaultScrollAnchor(.bottom)
            .scrollDismissesKeyboard(.interactively)
            .safeAreaInset(edge: .bottom, spacing: 0) {
                Composer(
                    draft: $draft,
                    replyTo: $replyTo,
                    focused: $composerFocused,
                    speaker: session.speakerName,
                    onSend: send
                )
            }
            .onChange(of: store.messages.count) { scrollToBottom(proxy) }
            .onChange(of: store.sending) { scrollToBottom(proxy) }
            .onChange(of: store.liveStep) { scrollToBottom(proxy) }
            .onChange(of: composerFocused) { _, focused in
                if focused { scrollToBottom(proxy, delay: .milliseconds(250)) }
            }
        }
        .navigationTitle(session.agentName ?? "Conversa")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            store.onError = { session.handle($0) }
            store.onConversationCreated = { session.added($0) }
            await store.load()
        }
        .task(id: scenePhase) {
            store.isVisible = scenePhase == .active
            guard scenePhase == .active else { return }
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.initiativePoll)
                await store.refresh()
            }
        }
    }

    private static let liveId = "live-status"
    private static let bottomId = "bottom"

    private func send() {
        let text = draft
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        store.send(text, replyTo: replyTo)
        draft = ""
        replyTo = nil
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
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Conversa nova")
                .font(.caption.weight(.semibold))
                .textCase(.uppercase)
                .foregroundStyle(.secondary)
            Text("Por onde a gente começa?")
                .font(.title2.weight(.semibold))
            Text("Um bug, uma ideia pela metade, um plano. Pode escrever ou colar código.")
                .foregroundStyle(.secondary)
        }
        .padding(.top, 40)
        .accessibilityElement(children: .combine)
    }
}

/// "Pensando" or the step the server says it is on, with Parar.
struct LiveStatusView: View {
    let step: ProgressStep?
    let canStop: Bool
    let onStop: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Image(systemName: "ellipsis")
                    .symbolEffect(.variableColor.iterative, isActive: !reduceMotion)
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
                Text(step?.label ?? "Pensando")
                    .contentTransition(.opacity)
                    .animation(.easeInOut, value: step?.label)
                if canStop {
                    Button(action: onStop) {
                        Image(systemName: "xmark.circle.fill")
                            .imageScale(.large)
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Parar")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Theme.assistantBubble, in: RoundedRectangle(cornerRadius: 18, style: .continuous))

            if let detail = step?.detail, !detail.isEmpty {
                Text(detail)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(.quaternary, in: Capsule())
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(step?.label ?? "Pensando")
    }
}
