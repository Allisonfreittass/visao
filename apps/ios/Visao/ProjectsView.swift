import SwiftUI
import VisaoKit

/// Projetos: the list (ProjectsView.tsx). Tapping one, or creating one, opens its own chat, where
/// everything about it lives, with its notes on top (ADR-0021).
struct ProjectsView: View {
    let onOpenProject: (String) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var list: [Project]?
    @State private var name = ""
    @State private var error: String?
    @State private var creating = false

    var body: some View {
        Group {
            if list?.isEmpty == true {
                empty
            } else {
                overview
            }
        }
        .task { await reload() }
    }

    /// No project yet: the big serif sentence over the forest, as on the web.
    private var empty: some View {
        VStack(alignment: .leading, spacing: 28) {
            Spacer(minLength: 0)
            (Text("projetos").font(Typo.display(34, relativeTo: .largeTitle, italic: true))
                + Text(" são o lugar de cada assunto: um chat só dele, com o que eu anotei, os painéis, as páginas e os arquivos em cima. dê um nome, ou me peça na conversa: “cria o projeto…”.")
                .font(Typo.display(34, relativeTo: .largeTitle)))
                .shadow(color: palette.usesGlass && palette == .neblinaDia ? .white.opacity(0.45) : .clear, radius: 9)
            createRow
            if let error { errorLine(error) }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(maxWidth: 620)
        .frame(maxWidth: .infinity)
    }

    private var overview: some View {
        GlassPage(
            label: "Projetos", title: "Cada assunto ", italic: "no seu chat.",
            lede: "Tocar abre o chat do projeto, com as anotações, os painéis e os arquivos em cima."
        ) {
            createRow
            if let error { errorLine(error) }
            if list == nil { ProgressView().frame(maxWidth: .infinity) }
            VStack(spacing: 10) {
                ForEach(list ?? []) { project in
                    Button { onOpenProject(project.id) } label: {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(project.name)
                                    .font(Typo.text(.body, weight: .medium))
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(project.summary)
                                    .font(Typo.text(.caption))
                                    .foregroundStyle(palette.tintaFraca)
                            }
                            Spacer(minLength: 0)
                            Image(systemName: "chevron.right")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(palette.tintaFraca)
                        }
                        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 14)
                        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).strokeBorder(palette.linhaForte))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Abre o chat do projeto")
                }
            }
        }
        .refreshable { await reload() }
    }

    private var createRow: some View {
        HStack(spacing: 8) {
            PageField(placeholder: "Nome do novo projeto", text: $name) { Task { await create() } }
                .accessibilityLabel("Nome do novo projeto")
            PillButton(title: "Criar", primary: true, busy: creating) { Task { await create() } }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || creating)
        }
    }

    private func errorLine(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.triangle")
            .font(Typo.text(.footnote))
            .foregroundStyle(palette.erro)
    }

    private func reload() async {
        do {
            list = try await session.api.projects()
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "Algo deu errado"
            session.handle(error)
        }
    }

    private func create() async {
        let trimmed = String(name.trimmingCharacters(in: .whitespaces).prefix(80))
        guard !trimmed.isEmpty, !creating else { return }
        creating = true
        defer { creating = false }
        do {
            let project = try await session.api.createProject(name: trimmed)
            name = ""
            session.renamed(project: project.id, to: project.name)
            onOpenProject(project.id)
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "Algo deu errado"
            session.handle(error)
        }
    }
}

/// Buttons that wrap to the next line when they don't fit (.row on the web).
struct FlowButtons<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { content }
            VStack(alignment: .leading, spacing: 8) { content }
        }
    }
}
