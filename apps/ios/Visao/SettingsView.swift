import Speech
import SwiftUI
import VisaoKit

/// Ajustes: all the switches in one place, grouped by what they touch (SettingsView.tsx). The
/// voice ones come with the call (stage 5).
struct SettingsView: View {
    @Environment(Session.self) private var session
    @Environment(Appearance.self) private var appearance
    @Environment(\.palette) private var palette
    @State private var server: ServerSettings?
    @State private var google: GoogleState?
    @State private var email: String?
    @State private var error: String?
    @State private var confirmLogout = false
    @State private var changing: AccountChange?
    @State private var confirmGoogle = false
    @State private var notice: String?
    @State private var speakReplies = VoicePrefs.speakReplies
    @State private var sampleVoice = VoiceEngine()
    @State private var voiceApproval = VoicePrefs.voiceApproval
    private let onDeviceSpeech = SFSpeechRecognizer(locale: Locale(identifier: "pt-BR"))?.supportsOnDeviceRecognition ?? false

    var body: some View {
        @Bindable var appearance = appearance
        GlassPage(label: "Ajustes", title: "Do seu ", italic: "jeito.") {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.erro)
            }
            if KokoroVoice.shared.state == .absent {
                // The first thing to see while the voice is still the robotic one.
                PageGroup(label: "Voz") {
                    KokoroRow(sample: { sampleVoice.speak("Oi! Esta é a voz Kokoro, rodando aqui no seu iPhone, sem servidor.") })
                }
            }
            PageGroup(label: "Aparência") {
                SettingRow(
                    title: "Floresta com neblina ao fundo",
                    description: "Pinheiros com neblina que se mexe, nas cores da hora do dia, com vidro de névoa por cima. Desligado, volta o tema escuro.",
                    isOn: Binding(get: { appearance.mode == .neblina }, set: { appearance.mode = $0 ? .neblina : .noite })
                )
                if appearance.mode == .neblina {
                    SettingRow(
                        title: "Neblina em movimento",
                        description: "Desligado, a floresta fica parada e só acompanha a hora, gastando menos bateria. Para sozinha no Modo de Pouca Energia.",
                        isOn: $appearance.moving
                    )
                }
            }
            PageGroup(label: "Voz e avisos") {
                if KokoroVoice.shared.state != .absent {
                    KokoroRow(sample: { sampleVoice.speak("Oi! Esta é a voz Kokoro, rodando aqui no seu iPhone, sem servidor.") })
                }
                SettingRow(
                    title: "Falar as respostas",
                    description: "Leio em voz alta com a voz do aparelho (\(VoiceEngine.voiceName)). Vozes melhores em Ajustes do iPhone → Acessibilidade → Conteúdo Falado → Vozes.",
                    isOn: Binding(get: { speakReplies }, set: { speakReplies = $0; VoicePrefs.speakReplies = $0 })
                )
                SettingRow(
                    title: "Aprovar por voz na ligação",
                    description: "Numa ligação, eu leio em voz alta o email, o evento ou o pedido ao Mac e espero você dizer “pode mandar” (ou “não”). Fora da ligação, só com o toque.",
                    isOn: Binding(get: { voiceApproval }, set: { voiceApproval = $0; VoicePrefs.voiceApproval = $0 })
                )
                PageRow {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Ligar").font(Typo.text(.subheadline, weight: .medium))
                        Text("Toque na orbe ao lado do campo. Eu ouço pelo reconhecimento de fala do iPhone\(onDeviceSpeech ? ", que roda no próprio aparelho: o áudio não sai dele." : "; neste iPhone ele usa os servidores da Apple.") Nada escuta com o app fechado.")
                            .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                PageRow {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Avisos com o app fechado").font(Typo.text(.subheadline, weight: .medium))
                        Text("Precisam da conta paga de desenvolvedor da Apple (APNs). Até lá, os avisos chegam pelo app do site na tela inicial.")
                            .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                    }
                }
            }
            PageGroup(label: "Autonomia") {
                SettingRow(
                    title: "Agir por conta própria",
                    description: "Pensar, estudar e puxar conversa quando eu tiver algo útil. Desligado, só respondo.",
                    isOn: serverBinding(\.paused, inverted: true) { try await session.api.setAutonomy(paused: !$0) == false },
                    disabled: server == nil
                )
                SettingRow(
                    title: "Pesquisar sozinho",
                    description: "Dúvidas de fatos públicos que ficaram sem resposta, só na Wikipédia e dentro do orçamento.",
                    isOn: serverBinding(\.autoResearch) { try await session.api.setAutoResearch($0) },
                    disabled: server == nil || server?.paused == true
                )
            }
            PageGroup(label: "Google") {
                PageRow {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Gmail e Google Agenda").font(Typo.text(.subheadline, weight: .medium))
                        Text(googleText)
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.tintaSuave)
                            .fixedSize(horizontal: false, vertical: true)
                        if let problem = google?.problem, !problem.isEmpty {
                            Text(problem).font(Typo.text(.footnote)).foregroundStyle(palette.erro)
                        }
                    }
                }
                if google?.connected == true {
                    PageRow {
                        HStack {
                            Spacer()
                            PillButton(title: "Desconectar") { confirmGoogle = true }
                        }
                    }
                    SettingRow(
                        title: "Olhar email e agenda sozinho",
                        description: "Vejo os compromissos das próximas 24 h e os assuntos dos emails não lidos, nunca o texto, para te lembrar do que importa.",
                        isOn: Binding(get: { google?.background ?? false }, set: { on in
                            Task { await run { google = try await session.api.setGoogleBackground(on) } }
                        })
                    )
                }
            }
            PageGroup(label: "Memória") {
                SettingRow(
                    title: "Lembrar entre conversas",
                    description: "Guardo o que você escolher para continuar de onde paramos. O que sei de você fica no Caderno.",
                    isOn: serverBinding(\.memory) { try await session.api.setMemory(enabled: $0) },
                    disabled: server == nil
                )
                PageRow {
                    HStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Perguntas iniciais").font(Typo.text(.subheadline, weight: .medium))
                            Text("Refazer a apresentação do começo, para eu te conhecer de novo.")
                                .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        }
                        Spacer()
                        PillButton(title: "Refazer") {
                            Task {
                                await run { try await session.api.restartOnboarding() }
                                NotificationCenter.default.post(name: .visaoRestartOnboarding, object: nil)
                            }
                        }
                    }
                }
            }
            PageGroup(label: "Conta") {
                PageRow {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Login").font(Typo.text(.subheadline, weight: .medium))
                        Text(email ?? "…").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        Text(session.serverAddress).font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
                        HStack(spacing: 14) {
                            linkButton("Trocar senha") { changing = .password }
                            linkButton("Trocar email") { changing = .email }
                        }
                        .padding(.top, 4)
                        if let notice {
                            Text("✓ \(notice)").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        }
                    }
                }
                PageRow {
                    HStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Sair deste aparelho").font(Typo.text(.subheadline, weight: .medium))
                            Text("Os outros continuam conectados.").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        }
                        Spacer()
                        PillButton(title: "Sair") { confirmLogout = true }
                    }
                }
            }
        }
        .task { await load() }
        .refreshable { await load() }
        .confirmationDialog("Sair desta conta?", isPresented: $confirmLogout, titleVisibility: .visible) {
            Button("Sair", role: .destructive) { session.logout() }
        }
        .confirmationDialog("Desconectar o Google?", isPresented: $confirmGoogle, titleVisibility: .visible) {
            Button("Desconectar", role: .destructive) {
                Task {
                    await run { try await session.api.disconnectGoogle() }
                    await load()
                }
            }
        } message: {
            Text("Ele para de ler seu email e sua agenda. Para conectar de novo, é pelo computador.")
        }
        .sheet(item: $changing) { mode in
            AccountChangeSheet(mode: mode) { message in
                notice = message
                Task { await load() }
            }
            .presentationDetents([.medium])
        }
    }

    private var googleText: String {
        guard let google else { return "…" }
        if google.connected {
            return "Conectado como \(google.email). Leio quando você pergunta; mandar ou marcar algo só com o seu sim."
        }
        return "Desconectado. Para eu ler seu email e sua agenda (e preparar respostas e eventos para você aprovar), conecte pelo computador, como explica a página de Ajustes do site."
    }

    /// A switch whose truth is on the server: it shows what the server says after each change.
    private func serverBinding(_ key: WritableKeyPath<ServerSettings, Bool>, inverted: Bool = false, save: @escaping (Bool) async throws -> Bool) -> Binding<Bool> {
        Binding(
            get: {
                guard let value = server?[keyPath: key] else { return false }
                return inverted ? !value : value
            },
            set: { shown in
                let value = inverted ? !shown : shown
                server?[keyPath: key] = value
                Task {
                    await run {
                        let saved = try await save(shown)
                        server?[keyPath: key] = inverted ? !saved : saved
                    }
                }
            }
        )
    }

    private func linkButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(Typo.text(.footnote, weight: .medium))
                .underline(color: palette.linhaForte)
                .foregroundStyle(palette.tinta)
        }
        .buttonStyle(.plain)
    }

    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "Não deu para salvar"
            session.handle(error)
            await load()
        }
    }

    private func load() async {
        async let s = try? session.api.serverSettings()
        async let g = try? session.api.google()
        async let me = try? session.api.me()
        server = await s ?? server
        google = await g ?? google
        email = await me?.email ?? email
    }
}

enum AccountChange: String, Identifiable {
    case password, email
    var id: String { rawValue }
}

/// Email or password, changed with the current password; every other device is signed out,
/// this one keeps going with the new token (AccountPanel.tsx).
struct AccountChangeSheet: View {
    let mode: AccountChange
    let onDone: (String) -> Void
    @Environment(Session.self) private var session
    @Environment(Appearance.self) private var appearance
    @Environment(\.dismiss) private var dismiss
    @State private var current = ""
    @State private var next = ""
    @State private var confirm = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    SecureField("Senha atual", text: $current).textContentType(.password)
                    if mode == .password {
                        SecureField("Senha nova", text: $next).textContentType(.newPassword)
                        SecureField("Repita a senha nova", text: $confirm).textContentType(.newPassword)
                    } else {
                        TextField("Email novo", text: $next)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                } footer: {
                    Text("Os outros aparelhos vão pedir login de novo; este continua conectado.")
                }
                if let error {
                    Section { Text(error).foregroundStyle(.red) }
                }
            }
            .navigationTitle(mode == .password ? "Trocar senha" : "Trocar email")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(busy ? "Trocando…" : "Trocar") { Task { await submit() } }
                        .disabled(busy || current.isEmpty || next.isEmpty)
                }
            }
        }
        .tint(appearance.palette.tinta)
    }

    private func submit() async {
        if mode == .password && next != confirm {
            error = "As senhas novas não conferem."
            return
        }
        busy = true
        defer { busy = false }
        do {
            if mode == .password {
                try await session.api.changePassword(current: current, new: next)
            } else {
                try await session.api.changeEmail(current: current, newEmail: next.trimmingCharacters(in: .whitespaces).lowercased())
            }
            onDone(mode == .password ? "Senha trocada. Os outros aparelhos vão pedir login de novo." : "Email trocado. Os outros aparelhos vão pedir login de novo.")
            dismiss()
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "Não consegui trocar agora."
        }
    }
}

/// The Kokoro voice on the iPhone: download it once (with progress), hear a sample, switch it on
/// or off, delete it to free the space.
private struct KokoroRow: View {
    let sample: () -> Void
    @Environment(\.palette) private var palette
    @State private var confirmRemove = false

    private var kokoro: KokoroVoice { KokoroVoice.shared }

    var body: some View {
        @Bindable var kokoro = KokoroVoice.shared
        PageRow {
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Voz Kokoro no iPhone").font(Typo.text(.subheadline, weight: .medium))
                    Text("A voz aberta que ele escolheu (Dora), rodando no próprio iPhone: mais natural que a do sistema, sem servidor e sem internet depois de baixar.")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        .fixedSize(horizontal: false, vertical: true)
                }
                switch kokoro.state {
                case .absent:
                    PillButton(title: "Baixar (\(KokoroVoice.downloadSize))", primary: true) { Task { await kokoro.download() } }
                    Text("De preferência no Wi-Fi. Vem do Hugging Face (aufklarer/Kokoro-82M-CoreML, licença Apache-2.0).")
                        .font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
                case .downloading(let fraction):
                    ProgressView(value: fraction) {
                        Text("Baixando… \(Int(fraction * 100))%").font(Typo.text(.footnote))
                    }
                    .tint(palette.estanho)
                case .loading:
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("Abrindo o modelo…").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                    }
                case .ready, .onDisk:
                    Toggle(isOn: $kokoro.enabled) {
                        Text("Falar com a voz Kokoro").font(Typo.text(.footnote, weight: .medium))
                    }
                    .toggleStyle(VisaoSwitch())
                    HStack(spacing: 8) {
                        PillButton(title: "Ouvir uma amostra", primary: true, action: sample)
                        PillButton(title: "Apagar") { confirmRemove = true }
                    }
                case .failed(let reason):
                    Text(reason).font(Typo.text(.footnote)).foregroundStyle(palette.erro)
                    PillButton(title: "Tentar de novo", primary: true) { Task { await kokoro.download() } }
                }
            }
        }
        .confirmationDialog("Apagar a voz Kokoro do iPhone?", isPresented: $confirmRemove, titleVisibility: .visible) {
            Button("Apagar", role: .destructive) { Task { await KokoroVoice.shared.remove() } }
        } message: {
            Text("Libera \(KokoroVoice.downloadSize). Ele volta a falar com a voz do servidor ou do iPhone.")
        }
    }
}
