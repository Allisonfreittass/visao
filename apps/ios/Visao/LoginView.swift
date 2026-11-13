import SwiftUI
import VisaoKit

struct LoginView: View {
    @Environment(Session.self) private var session
    @State private var email = ""
    @State private var password = ""
    @State private var server = ""
    @State private var showServer = false
    @State private var busy = false
    @State private var error: String?
    @FocusState private var field: Field?

    enum Field { case email, password, server }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("V.I.S.A.O.")
                            .font(.largeTitle.weight(.semibold))
                            .accessibilityLabel("Visão")
                        Text("Virtual Intelligence with Supervised Autonomy & Opt-in memory")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 8)
                    .listRowBackground(Color.clear)
                }

                Section {
                    TextField("E-mail", text: $email)
                        .textContentType(.username)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($field, equals: .email)
                        .submitLabel(.next)
                        .onSubmit { field = .password }
                    SecureField("Senha", text: $password)
                        .textContentType(.password)
                        .focused($field, equals: .password)
                        .submitLabel(.go)
                        .onSubmit(submit)
                }

                Section {
                    DisclosureGroup("Servidor", isExpanded: $showServer) {
                        TextField("https://endereco/api", text: $server)
                            .keyboardType(.URL)
                            .textContentType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .focused($field, equals: .server)
                            .font(.callout.monospaced())
                    }
                } footer: {
                    Text("A API do Visão. Em produção é o endereço do site com /api; com a API no Mac, http://seu-mac.local:8000.")
                }

                if let error {
                    Section {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.red)
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Spacer()
                            if busy { ProgressView() } else { Text("Entrar").bold() }
                            Spacer()
                        }
                    }
                    .disabled(busy || email.isEmpty || password.isEmpty)
                }
            }
            .navigationTitle("Entrar")
            .navigationBarTitleDisplayMode(.inline)
            .onAppear {
                if server.isEmpty { server = session.serverAddress }
                field = .email
            }
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
