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
    /// Two-way audio, so talking over him stops him; nil when "Interromper falando" is off.
    private(set) var duplex: DuplexVoice?

    var level: Float { duplex?.level ?? voice.level }
    var partial: String { duplex?.partial ?? voice.partial }
    var usesServerVoice: Bool { duplex?.usesServerVoice ?? voice.usesServerVoice }
    var onDevice: Bool { duplex?.onDevice ?? voice.onDevice }
    var canInterruptByVoice: Bool { duplex != nil }

    /// The camera, while it is on: what it sees goes with each sentence.
    private(set) var camera: CallCamera?
    private var uploading = false

    func toggleCamera() {
        if let camera {
            camera.stop()
            self.camera = nil
            return
        }
        Task {
            guard await CallCamera.requestAccess() else {
                error = CameraError.denied.errorDescription
                return
            }
            let camera = CallCamera()
            do {
                try camera.start()
                self.camera = camera
            } catch {
                self.error = (error as? LocalizedError)?.errorDescription
            }
        }
    }

    func flipCamera() { camera?.flip() }
    private let chat: ChatStore
    private let pending: PendingStore
    private let api: APIClient
    private var approvals = VoiceApprovalSession()
    private var known: Set<String> = []
    private var awaitingReply = false
    private var watcher: Task<Void, Never>?
    private var ended = false

    init(chat: ChatStore, pending: PendingStore, api: APIClient) {
        self.chat = chat
        self.pending = pending
        self.api = api
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
        if VoicePrefs.bargeIn {
            let duplex = DuplexVoice()
            duplex.onUtterance = { [weak self] sentence in self?.heard(sentence) }
            duplex.onBargeIn = { [weak self] in self?.state = .listening }
            duplex.onDeaf = { [weak self] in self?.fallBackToHalfDuplex() }
            do {
                try await duplex.start(api: api)
                self.duplex = duplex
            } catch {
                // The iPhone refused two-way audio: the call goes on the old way.
                duplex.stop()
            }
        }
        if duplex == nil {
            do {
                try voice.activate()
            } catch {
                fail(error)
                return
            }
            await voice.prepare(api: api)
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
        camera?.stop()
        camera = nil
        duplex?.stop()
        voice.deactivate()
        UIApplication.shared.isIdleTimerDisabled = false
    }

    /// Stops it talking and listens again.
    func interrupt() {
        duplex?.stopSpeaking()
        voice.stopSpeaking()
        state = .interrupted
        listen()
    }

    func decideOnScreen(_ ask: PendingAsk, approve: Bool) {
        Task {
            duplex?.stopSpeaking()
            voice.stopSpeaking()
            let ok = await pending.decide(ask, approve: approve)
            if ok && approve { await chat.refresh() }
            known = Set(chat.messages.map(\.id))
            say(VoiceRules.done(for: ask, verdict: approve ? .approve : .reject, accepted: ok))
        }
    }

    /// Two-way audio heard your voice but no words: the call goes on the old way, and says so.
    private func fallBackToHalfDuplex() {
        guard let duplex else { return }
        duplex.stop()
        self.duplex = nil
        Task {
            do {
                try voice.activate()
                await voice.prepare(api: api)
                error = "Troquei para o modo sem interrupção: pode falar de novo."
                listen()
            } catch {
                fail(error)
            }
        }
    }

    // MARK: Flow

    private func listen() {
        guard !ended else { return }
        // Two-way: the microphone never stopped.
        if duplex != nil {
            state = .listening
            return
        }
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
        // Camera on: the picture of this moment goes with the sentence.
        guard let photo = camera?.snapshot() else {
            chat.send(sentence, spoken: true)
            return
        }
        uploading = true
        Task {
            defer { uploading = false }
            do {
                let attachment = try await api.uploadAttachment(data: photo, filename: photoName(index: 0, ext: "jpg"), mimeType: "image/jpeg")
                chat.send(sentence, attachments: [attachment], spoken: true)
            } catch {
                // The words still go, without the picture.
                chat.send(sentence, spoken: true)
            }
        }
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
            guard !chat.sending, !uploading else { return }
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
        let after: () -> Void = { [weak self] in
            guard let self, self.state == .speaking else { return }
            self.afterSpeaking()
        }
        if let duplex {
            duplex.speak(text, done: after)
        } else {
            voice.speak(text, done: after)
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
                Text(voiceLabel)
            }
            .font(Typo.mono(.caption2))
            .textCase(.uppercase)
            .foregroundStyle(palette.tintaSuave)

            KokoroOffer(usesServerVoice: controller.usesServerVoice)
            Spacer(minLength: 0)
            CallOrb(state: controller.state, level: controller.level)
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
                Button { controller.toggleCamera() } label: {
                    Image(systemName: controller.camera == nil ? "camera" : "camera.fill")
                        .font(.body.weight(.medium))
                        .foregroundStyle(controller.camera == nil ? palette.tinta : palette.pilulaAtivaTinta)
                        .frame(width: 52, height: 52)
                        .background(controller.camera == nil ? palette.fundoHover : palette.pilulaAtiva, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(controller.camera == nil ? "Ligar a câmera: ele vê o que ela mostra quando você fala" : "Desligar a câmera")
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
        .overlay(alignment: .topTrailing) {
            if let camera = controller.camera {
                // What he will see with your next sentence.
                CameraPreview(session: camera.session)
                    .frame(width: 120, height: 170)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(palette.vidroBorda))
                    .overlay(alignment: .bottomTrailing) {
                        Button { controller.flipCamera() } label: {
                            Image(systemName: "arrow.triangle.2.circlepath.camera")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(.white)
                                .frame(width: 44, height: 44)
                                .background(.black.opacity(0.35), in: Circle())
                        }
                        .buttonStyle(.plain)
                        .padding(4)
                        .accessibilityLabel("Trocar de câmera")
                    }
                    .shadow(color: .black.opacity(0.25), radius: 10, y: 4)
                    .padding(.top, 44)
                    .padding(.trailing, 16)
                    .transition(.scale(scale: 0.8, anchor: .topTrailing).combined(with: .opacity))
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel("O que a câmera está mostrando")
            }
        }
        .animation(.spring(duration: 0.3), value: controller.camera != nil)
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
            if !controller.partial.isEmpty {
                line("Você", controller.partial, dim: true)
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

    /// Which voice is speaking, top right.
    private var voiceLabel: String {
        if let local = LocalVoices.shared.active { return "Voz \(local.kind.name) · no iPhone" }
        if controller.usesServerVoice { return "Voz própria" }
        return controller.onDevice ? "Voz do aparelho · no iPhone" : "Voz do aparelho"
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
        case .speaking: controller.canInterruptByVoice ? "Fale por cima para me interromper." : "Toque em Interromper para falar por cima."
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
            // Content, not a control: a standard material, not Liquid Glass (liquid-glass.md).
            .background(palette.usesGlass ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(palette.fundoElevado), in: Circle())
            .overlay(Circle().strokeBorder(palette.vidroBorda))
        }
        .accessibilityHidden(true)
    }
}

/// While the voice is still the iPhone's robotic one: a nudge to download a better one, here.
private struct KokoroOffer: View {
    let usesServerVoice: Bool
    @Environment(\.palette) private var palette

    var body: some View {
        let voices = LocalVoices.shared
        let supertonic = voices.supertonic
        if case .downloading(let fraction) = supertonic.state {
            ProgressView(value: fraction) {
                Text("Baixando a voz Supertonic… \(Int(fraction * 100))%").font(Typo.text(.caption))
            }
            .tint(palette.estanho)
            .padding(12)
            .glass(palette, cornerRadius: 18, shadow: false)
        } else if voices.active == nil && !usesServerVoice && supertonic.state == .absent {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Voz robótica?").font(Typo.text(.footnote, weight: .medium))
                    Text("A Supertonic roda no iPhone e soa bem mais natural (\(supertonic.kind.size), uma vez).")
                        .font(Typo.text(.caption)).foregroundStyle(palette.tintaSuave)
                }
                Spacer()
                PillButton(title: "Baixar", primary: true) { Task { await voices.download(.supertonic) } }
            }
            .padding(12)
            .glass(palette, cornerRadius: 18, shadow: false)
        }
    }
}
