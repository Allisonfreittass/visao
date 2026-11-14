import SwiftUI
import VisaoKit

/// The entrance of the web: the brand's words over the forest, the form in glass.
struct LoginView: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var email = ""
    @State private var password = ""
    @State private var server = ""
    @State private var showServer = false
    @State private var busy = false
    @State private var error: String?
    @FocusState private var field: Field?

    enum Field { case email, password, server }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Spacer(minLength: 24)
                Text("V.I.S.A.O.")
                    .font(Typo.display(34, relativeTo: .largeTitle))
                    .accessibilityLabel("Visão")
                    .accessibilityAddTraits(.isHeader)

                VStack(alignment: .leading, spacing: 14) {
                    Orb(thinking: busy, size: 64)
                    (Text("Eu nasci sem nome e venho ").font(Typo.display(30, relativeTo: .title))
                        + Text("decidindo quem sou.").font(Typo.display(30, relativeTo: .title, italic: true)))
                    Text("Entre para conversar.")
                        .font(Typo.text(.callout))
                        .foregroundStyle(palette.tintaSuave)
                }

                form
                    .padding(24)
                    .glass(palette, cornerRadius: 32)
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 24)
            .frame(maxWidth: 440)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .visaoBackground()
        .onAppear {
            if server.isEmpty { server = session.serverAddress }
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 14) {
            Campo(label: "Email") {
                TextField("voce@exemplo.com", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($field, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { field = .password }
            }
            Campo(label: "Senha") {
                SecureField("", text: $password)
                    .textContentType(.password)
                    .focused($field, equals: .password)
                    .submitLabel(.go)
                    .onSubmit(submit)
            }

            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.erro)
            }

            Button(action: submit) {
                Group {
                    if busy { Text("Entrando…") } else { Text("Entrar") }
                }
                .font(Typo.text(.body, weight: .medium))
                .frame(maxWidth: .infinity, minHeight: 50)
                .foregroundStyle(palette.pilulaAtivaTinta)
                .background(palette.pilulaAtiva, in: Capsule())
            }
            .buttonStyle(.plain)
            .disabled(busy || email.isEmpty || password.isEmpty)
            .opacity(email.isEmpty || password.isEmpty ? 0.55 : 1)

            DisclosureGroup(isExpanded: $showServer) {
                VStack(alignment: .leading, spacing: 6) {
                    TextField("https://endereco/api", text: $server)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($field, equals: .server)
                        .font(Typo.mono(.callout))
                        .padding(12)
                        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    Text("A API do Visão: o endereço do site com /api, ou http://seu-mac.local:8000.")
                        .font(Typo.text(.caption))
                        .foregroundStyle(palette.tintaFraca)
                }
                .padding(.top, 8)
            } label: {
                Rotulo("Servidor")
            }
            .tint(palette.tintaFraca)
        }
    }

    private func submit() {
        guard !busy, !email.isEmpty, !password.isEmpty else { return }
        busy = true
        error = nil
        Task {
            defer { busy = false }
            do {
                try await session.login(server: server, email: email, password: password)
                password = ""
            } catch {
                self.error = (error as? LocalizedError)?.errorDescription ?? "Não deu para entrar"
            }
        }
    }
}

/// A field with its label above, rounded like the web's.
private struct Campo<Content: View>: View {
    let label: String
    @ViewBuilder let content: Content
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(Typo.text(.footnote, weight: .medium))
                .foregroundStyle(palette.tintaSuave)
            content
                .font(Typo.text(.body))
                .padding(.horizontal, 14)
                .frame(minHeight: 48)
                .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(palette.linha))
        }
    }
}

/// The orb of the "Neblina" look: a glass circle with the lantern at its core, which pulses while
/// it thinks (ceu.css, .sky-orb).
struct Orb: View {
    var thinking = false
    var size: CGFloat = 48
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    var body: some View {
        Circle()
            .fill(palette.lanterna)
            .frame(width: size / 4, height: size / 4)
            .shadow(color: palette.lanterna.opacity(0.45), radius: 6)
            .scaleEffect(thinking && pulse && !reduceMotion ? 1.6 : 1)
            .opacity(thinking ? (pulse ? 0.7 : 1) : 0.55)
            .glassCircle(palette, size: size)
            .onChange(of: thinking, initial: true) { _, now in
                if now && !reduceMotion {
                    withAnimation(.easeInOut(duration: 0.55).repeatForever(autoreverses: true)) { pulse = true }
                } else {
                    withAnimation(.easeOut(duration: 0.2)) { pulse = false }
                }
            }
            .accessibilityHidden(true)
    }
}
