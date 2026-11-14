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

    var body: some View {
        @Bindable var appearance = appearance
        GlassPage(label: "Ajustes", title: "Do seu ", italic: "jeito.") {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.erro)
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
            }
            PageGroup(label: "Conta") {
                PageRow {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Login").font(Typo.text(.subheadline, weight: .medium))
                        Text(email ?? "…").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        Text(session.serverAddress).font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
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
