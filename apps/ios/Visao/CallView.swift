import Observation
import SwiftUI
import UIKit
import VisaoKit

/// What moves a call: hear a sentence, send it as voice, speak the reply, read aloud what waits for
/// a yes and wait for "pode mandar" or "não" (docs/VOICE.md). The rules live in VisaoKit.
@MainActor
@Observable
final class CallController {
    enum State: Equatable {
        case starting, listening, thinking, speaking, interrupted, failed
    }

    private(set) var state: State = .starting
    private(set) var error: String?
    let started = Date()

    let voice = VoiceEngine()
    private let chat: ChatStore
    private let pending: PendingStore
    private var approvals = VoiceApprovalSession()
    private var known: Set<String> = []
    private var awaitingReply = false
    private var watcher: Task<Void, Never>?
    private var ended = false

    init(chat: ChatStore, pending: PendingStore) {
        self.chat = chat
        self.pending = pending
    }

    var asksHere: [PendingAsk] { pending.asks(in: chat.conversationId) }
    var voiceApproval: Bool { VoicePrefs.voiceApproval }
    /// The ask read aloud and waiting for a spoken answer, shown big on screen.
    var askOnScreen: PendingAsk? { approvals.asked?.ask ?? asksHere.first }

    func start() async {
        guard await voice.requestPermissions() else {
            fail(VoiceError.denied)
            return
        }
        do {
            try voice.activate()
        } catch {
            fail(error)
            return
        }
        UIApplication.shared.isIdleTimerDisabled = true
        known = Set(chat.messages.map(\.id))
        watch()
        afterSpeaking()
    }

    /// Nothing listens once the call ends, or when the app leaves the screen.
    func hangUp() {
        guard !ended else { return }
        ended = true
        watcher?.cancel()
        voice.deactivate()
        UIApplication.shared.isIdleTimerDisabled = false
    }

    /// Stops it talking and listens again.
    func interrupt() {
        voice.stopSpeaking()
        state = .interrupted
        listen()
    }

    func decideOnScreen(_ ask: PendingAsk, approve: Bool) {
        Task {
            voice.stopSpeaking()
            let ok = await pending.decide(ask, approve: approve)
            if ok && approve { await chat.refresh() }
            known = Set(chat.messages.map(\.id))
            say(VoiceRules.done(for: ask, verdict: approve ? .approve : .reject, accepted: ok))
        }
    }

    // MARK: Flow

    private func listen() {
        guard !ended else { return }
        do {
            try voice.listen { [weak self] sentence in self?.heard(sentence) }
            state = .listening
        } catch {
            fail(error)
        }
    }

    private func heard(_ sentence: String) {
        // A clear answer to what it just read decides it, said back only after the server accepted.
        if voiceApproval, let (ask, verdict) = approvals.interpret(sentence, stillWaiting: asksHere) {
            state = .thinking
            Task {
                let ok = await pending.decide(ask, approve: verdict == .approve, via: .voz)
                if ok && verdict == .approve { await chat.refresh() }
                known = Set(chat.messages.map(\.id))
                say(VoiceRules.done(for: ask, verdict: verdict, accepted: ok))
            }
            return
        }
        state = .thinking
        awaitingReply = true
        chat.send(sentence, spoken: true)
    }

    /// Watches the chat: the reply to what you said, and what it says on its own, are spoken.
    private func watch() {
        watcher = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(250))
                guard let self, !self.ended else { return }
                self.check()
            }
        }
    }

    private func check() {
        if awaitingReply {
            guard !chat.sending else { return }
            awaitingReply = false
            let fresh = chat.messages.filter { $0.role == .assistant && !known.contains($0.id) }
            known = Set(chat.messages.map(\.id))
            if let reply = fresh.last {
                Task {
                    await pending.refresh()
                    say(VoiceRules.speakable(reply.content))
                }
            } else {
                // Failed or stopped: say so and keep listening.
                say(chat.error.map { "Não consegui responder: \($0)" } ?? "Parei.")
            }
            return
        }
        // It spoke first (an opening, the Mac's report) while you were quiet.
        guard state == .listening else { return }
        let fresh = chat.messages.filter { $0.role == .assistant && !known.contains($0.id) && $0.local == nil }
        if let opening = fresh.last {
            known = Set(chat.messages.map(\.id))
            say(VoiceRules.speakable(opening.content))
        } else if voiceApproval, approvals.asked == nil, !asksHere.isEmpty {
            afterSpeaking()
        }
    }

    private func say(_ text: String) {
        guard !ended else { return }
        state = .speaking
        voice.speak(text) { [weak self] in
            guard let self, self.state == .speaking else { return }
            self.afterSpeaking()
        }
    }

    /// Once it stops talking: read the next ask aloud (once per call), or listen.
    private func afterSpeaking() {
        guard !ended else { return }
        if voiceApproval, let ask = approvals.nextToAnnounce(from: asksHere) {
            say(VoiceRules.question(for: ask))
            return
        }
        listen()
    }

    private func fail(_ error: Error) {
        self.error = (error as? LocalizedError)?.errorDescription ?? "A ligação caiu."
        state = .failed
    }
}

/// A call: the whole screen is the conversation, hands free, the screen kept on (CallView.tsx).
struct CallView: View {
    let controller: CallController
    let agentName: String?
    let messages: [Message]
    @Environment(Appearance.self) private var appearance
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.openURL) private var openURL

    private var palette: Palette { appearance.palette }

    var body: some View {
        VStack(spacing: 18) {
            HStack {
                TimelineView(.periodic(from: controller.started, by: 1)) { context in
                    HStack(spacing: 6) {
                        Circle().fill(palette.lanterna).frame(width: 7, height: 7)
                        Text("Em ligação · \(clock(context.date.timeIntervalSince(controller.started)))")
                    }
                }
                Spacer()
                Text(controller.voice.onDevice ? "Voz do aparelho · no iPhone" : "Voz do aparelho")
            }
            .font(Typo.mono(.caption2))
            .textCase(.uppercase)
            .foregroundStyle(palette.tintaSuave)

            Spacer(minLength: 0)
            CallOrb(state: controller.state, level: controller.voice.level)
            VStack(spacing: 6) {
                Text(agentName ?? "Sem nome ainda")
                    .font(Typo.display(34, relativeTo: .largeTitle, italic: agentName == nil))
                Text(stateLabel)
                    .font(Typo.mono(.caption))
                    .textCase(.uppercase)
                    .foregroundStyle(palette.tintaFraca)
                    .accessibilityAddTraits(.updatesFrequently)
                Text(hint)
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.tintaSuave)
                    .multilineTextAlignment(.center)
            }
            Spacer(minLength: 0)

            transcript
            if let ask = controller.askOnScreen {
                ActionCard(ask: ask, busy: false) { approve in controller.decideOnScreen(ask, approve: approve) }
                    .overlay(alignment: .bottomLeading) {
                        if controller.voiceApproval {
                            Text("Ou diga “pode mandar” para aprovar, ou “não”.")
                                .font(Typo.text(.caption))
                                .foregroundStyle(Color(rgb: 0x9aa0b4))
                                .padding(.leading, 18)
                                .padding(.bottom, 6)
                        }
                    }
            }
            HStack(spacing: 12) {
                if controller.state == .speaking {
                    PillButton(title: "Interromper") { controller.interrupt() }
                }
                Button {
                    controller.hangUp()
                    dismiss()
                } label: {
                    Label("Desligar", systemImage: "phone.down.fill")
                        .font(Typo.text(.callout, weight: .medium))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 26)
                        .frame(minHeight: 52)
                        .background(Color(rgb: 0xc8352c), in: Capsule())
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.escape, modifiers: [])
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
        .foregroundStyle(palette.tinta)
        .background {
            ZStack {
                SkyBackground()
                Rectangle().fill(.ultraThinMaterial).opacity(0.55).ignoresSafeArea()
            }
        }
        .environment(\.palette, palette)
        .task { await controller.start() }
        .onChange(of: scenePhase) { _, phase in
            // Hiding the app ends the call: nothing listens in the background.
            if phase != .active {
                controller.hangUp()
                dismiss()
            }
        }
        .onDisappear { controller.hangUp() }
    }

    @ViewBuilder
    private var transcript: some View {
        let lastUser = messages.last { $0.role == .user }
        let lastReply = messages.last { $0.role == .assistant }
        VStack(alignment: .leading, spacing: 8) {
            if !controller.voice.partial.isEmpty {
                line("Você", controller.voice.partial, dim: true)
            } else if let lastUser {
                line("Você", lastUser.content)
            }
            if let lastReply {
                line(agentName ?? "Ele", String(VoiceRules.speakable(lastReply.content).prefix(280)))
            }
            if let error = controller.error {
                Text(error).font(Typo.text(.footnote)).foregroundStyle(palette.erro)
                if controller.state == .failed, let url = URL(string: UIApplication.openSettingsURLString) {
                    PillButton(title: "Abrir Ajustes do iPhone") { openURL(url) }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .glass(palette, cornerRadius: 22, shadow: false)
    }

    private func line(_ who: String, _ text: String, dim: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(who).font(Typo.mono(.caption2)).textCase(.uppercase).foregroundStyle(palette.tintaFraca)
            Text(text).font(Typo.text(.subheadline)).foregroundStyle(dim ? palette.tintaSuave : palette.tinta).lineLimit(4)
        }
    }

    private var stateLabel: String {
        switch controller.state {
        case .starting: "conectando"
        case .listening: "ouvindo"
        case .thinking: "pensando"
        case .speaking: "falando"
        case .interrupted: "interrompido"
        case .failed: "desconectado"
        }
    }

    private var hint: String {
        switch controller.state {
        case .starting: "Pedindo o microfone."
        case .listening: "Pode falar. Eu espero você terminar."
        case .thinking: "Pensando no que você disse."
        case .speaking: "Toque em Interromper para falar por cima."
        case .interrupted: "Parei. Continue."
        case .failed: "A ligação não começou."
        }
    }

    private func clock(_ seconds: TimeInterval) -> String {
        let total = max(0, Int(seconds))
        return String(format: "%02d:%02d", total / 60, total % 60)
    }
}

/// The big orb of the call: glass with the lantern at the core, swelling with your voice while it
/// listens and breathing while it thinks or speaks.
struct CallOrb: View {
    let state: CallController.State
    let level: Float
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            let breathe = reduceMotion ? 0 : sin(t * (state == .thinking ? 6 : 2)) * 0.5 + 0.5
            let swell: Double = switch state {
            case .listening: Double(level) * 0.5
            case .speaking: 0.15 + breathe * 0.15
            case .thinking: breathe * 0.25
            default: breathe * 0.05
            }
            ZStack {
                Circle()
                    .fill(palette.lanterna.opacity(0.18))
                    .frame(width: 210, height: 210)
                    .scaleEffect(1 + swell * 0.6)
                    .blur(radius: 30)
                Circle()
                    .fill(palette.lanterna)
                    .frame(width: 44, height: 44)
                    .shadow(color: palette.lanterna.opacity(0.6), radius: 18)
                    .scaleEffect(state == .failed ? 0.6 : 1 + swell)
                    .opacity(state == .failed ? 0.4 : 1)
            }
            .frame(width: 220, height: 220)
            .liquidGlass(palette, in: Circle(), tint: palette.vidro.opacity(0.2), interactive: false)
        }
        .accessibilityHidden(true)
    }
}
