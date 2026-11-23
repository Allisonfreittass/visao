import SwiftUI
import VisaoKit

/// The entrance (Login on the web): the mascot, "Identifique-se.", the form in a card. While
/// the password has the focus the mascot narrows its eye to a slit: "Não estou olhando."
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
            VStack(alignment: .center, spacing: 28) {
                Spacer(minLength: 24)
                Wordmark(size: 20)

                VStack(spacing: 14) {
                    SentinelaView(state: busy ? .thinking : .idle, size: 124, eyesClosed: field == .password)
                        .overlay(alignment: .topTrailing) {
                            if field == .password {
                                Text("Não estou olhando.")
                                    .font(Typo.text(.caption, weight: .medium))
                                    .foregroundStyle(palette.text2)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 6)
                                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(palette.borderStrong))
                                    .fixedSize()
                                    .offset(x: 96, y: -14)
                                    .transition(.opacity)
                            }
                        }
                        .animation(.easeOut(duration: 0.2), value: field)
                    Text("Identifique-se.")
                        .font(Typo.display(30, relativeTo: .title))
                        .accessibilityAddTraits(.isHeader)
                    Text("Acesso restrito. Só você entra aqui.")
                        .font(Typo.text(.callout))
                        .foregroundStyle(palette.textMuted)
                }

                form
                    .padding(20)
                    .glass(palette, cornerRadius: 16)
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
            Campo(label: "E-mail", focused: field == .email) {
                TextField("voce@exemplo.com", text: $email)
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($field, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { field = .password }
            }
            Campo(label: "Senha", focused: field == .password) {
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
                    if busy { Text("Verificando…") } else { Text("Acessar") }
                }
                .font(Typo.text(.body, weight: .medium))
                .frame(maxWidth: .infinity, minHeight: 50)
                .foregroundStyle(palette.onRed)
                .background(palette.red, in: Capsule())
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
                self.error = (error as? LocalizedError)?.errorDescription ?? "Acesso negado. Confira o e-mail e a senha."
            }
        }
    }
}

/// A field with its label above, rounded like the web's.
private struct Campo<Content: View>: View {
    let label: String
    var focused = false
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
                .background(focused ? palette.surface : palette.bg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(focused ? palette.red : palette.borderStrong, lineWidth: focused ? 2 : 1))
                // Focus: a 2 pt red border with a soft red halo.
                .background(RoundedRectangle(cornerRadius: 15, style: .continuous).stroke(Palette.red.opacity(focused ? 0.22 : 0), lineWidth: 4).padding(-3))
                .animation(.easeOut(duration: 0.15), value: focused)
        }
    }
}
