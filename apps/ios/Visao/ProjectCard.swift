import QuickLook
import SwiftUI
import VisaoKit

/// On top of a project's chat (ProjectHeader.tsx, ADR-0021): back to Projetos and the whole name,
/// then the summary, which opens and closes the rest: the notes (with Editar), the project's
/// panels, pages and files, Renomear and Apagar projeto.
struct ProjectCard: View {
    let projectId: String
    /// Changes when a turn ends here, so new notes show without leaving the screen.
    let refreshKey: Int
    let onBack: () -> Void
    let onDeleted: () -> Void
    let onOpenPage: (Artifact) -> Void
    let onBench: (() -> Void)?
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var project: ProjectDetail?
    @State private var open = false
    @State private var editing: String?
    @State private var renaming = false
    @State private var newName = ""
    @State private var confirmDelete = false
    @State private var preview: URL?
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 4) {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(palette.tinta)
                        .frame(width: 44, height: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Voltar para Projetos")
                Text(project?.name ?? session.projectNames[projectId] ?? "Projeto")
                    .font(Typo.display(24, relativeTo: .title2))
                    .foregroundStyle(palette.tinta)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityAddTraits(.isHeader)
                if let onBench {
                    Button(action: onBench) {
                        Image(systemName: "list.bullet.rectangle")
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(palette.tintaSuave)
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Bancada: o que ele fez neste projeto")
                }
            }
            Button {
                withAnimation(reduceMotion ? nil : .spring(duration: 0.3)) { open.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Text(project?.summary ?? "…")
                    Text(open ? "▴" : "▾").accessibilityHidden(true)
                    Spacer(minLength: 0)
                }
                .font(Typo.text(.footnote))
                .foregroundStyle(palette.tintaSuave)
                .padding(.leading, 12)
                .frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityValue(open ? "aberto" : "fechado")
            .accessibilityHint("Mostra as anotações, os painéis e os arquivos")
            if open, let project {
                ScrollView {
                    details(project)
                        .padding(.horizontal, 12)
                        .padding(.bottom, 12)
                }
                .frame(maxHeight: 440)
                .scrollBounceBehavior(.basedOnSize)
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 2)
        .glass(palette, cornerRadius: 22, strong: true, shadow: true)
        .padding(.horizontal, 10)
        .padding(.top, 4)
        .task(id: refreshKey) { await load() }
        .quickLookPreview($preview)
        .sheet(isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
            NotesEditor(text: editing ?? "") { saved in
                Task { await saveNotes(saved) }
            }
        }
        .alert("Novo nome do projeto", isPresented: $renaming) {
            TextField("Nome", text: $newName)
            Button("Cancelar", role: .cancel) {}
            Button("Renomear") { Task { await rename() } }
        }
        .confirmationDialog(
            "Apagar o projeto “\(project?.name ?? "")”? As anotações vão junto; o chat, as páginas, os arquivos e os painéis continuam, fora de projeto.",
            isPresented: $confirmDelete, titleVisibility: .visible
        ) {
            Button("Apagar projeto", role: .destructive) { Task { await remove() } }
            Button("Cancelar", role: .cancel) {}
        }
    }

    @ViewBuilder
    private func details(_ project: ProjectDetail) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.erro)
            }
            PageGroup(label: "Anotações") {
                let lines = project.noteLines
                if lines.isEmpty {
                    Text("Nada anotado ainda. Peça aqui: “anota isso”.")
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text("•").foregroundStyle(palette.estanho).accessibilityHidden(true)
                                Text(line).fixedSize(horizontal: false, vertical: true)
                            }
                            .font(Typo.text(.subheadline))
                        }
                    }
                }
                PillButton(title: "Editar anotações") { editing = project.notes }
            }
            PanelsSection(nothingPending: false, onDraft: { _ in }, projectId: project.id)
            if !project.pageList.isEmpty {
                PageGroup(label: "Páginas") {
                    ForEach(project.pageList) { page in
                        row(page.title, detail: DayLabel.text(for: page.createdAt)) { onOpenPage(page) }
                    }
                }
            }
            if !project.fileList.isEmpty {
                PageGroup(label: "Arquivos") {
                    ForEach(project.fileList) { file in
                        row(file.filename, detail: AttachmentRules.formatSize(file.sizeBytes)) {
                            Task { preview = try? await session.loader.file(file) }
                        }
                    }
                }
            }
            FlowButtons {
                PillButton(title: "Renomear") {
                    newName = project.name
                    renaming = true
                }
                PillButton(title: "Apagar projeto") { confirmDelete = true }
            }
        }
        .padding(.top, 4)
    }

    private func row(_ title: String, detail: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(title)
                    .font(Typo.text(.subheadline, weight: .medium))
                    .lineLimit(2)
                Spacer()
                Text(detail)
                    .font(Typo.text(.caption))
                    .foregroundStyle(palette.tintaFraca)
            }
            .frame(minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "Algo deu errado"
            session.handle(error)
        }
    }

    private func load() async {
        await run { project = try await session.api.project(id: projectId) }
    }

    private func saveNotes(_ notes: String) async {
        await run {
            _ = try await session.api.updateProject(id: projectId, ProjectChange(notes: notes))
            editing = nil
            project = try await session.api.project(id: projectId)
        }
    }

    private func rename() async {
        let trimmed = String(newName.trimmingCharacters(in: .whitespaces).prefix(80))
        guard !trimmed.isEmpty else { return }
        await run {
            let saved = try await session.api.updateProject(id: projectId, ProjectChange(name: trimmed))
            session.renamed(project: projectId, to: saved.name)
            project = try await session.api.project(id: projectId)
        }
    }

    private func remove() async {
        await run {
            try await session.api.deleteProject(id: projectId)
            await session.loadProjectNames()
            onDeleted()
        }
    }
}

/// "Editar anotações": one fact per line, as he writes them ("- …").
private struct NotesEditor: View {
    @State var text: String
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            TextEditor(text: $text)
                .font(Typo.text(.body))
                .padding(.horizontal, 12)
                .navigationTitle("Anotações")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button("Cancelar") { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) { Button("Salvar") { onSave(text) } }
                }
        }
        .presentationDetents([.medium, .large])
    }
}
