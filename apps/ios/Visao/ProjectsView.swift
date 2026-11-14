import QuickLook
import SwiftUI
import VisaoKit

/// Projetos: subjects with their conversations, pages and files together (ProjectsView.tsx).
struct ProjectsView: View {
    let currentConversation: String?
    let onOpen: (String) -> Void
    let onNew: (String) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var list: [Project]?
    @State private var open: ProjectDetail?
    @State private var name = ""
    @State private var renaming = false
    @State private var newName = ""
    @State private var confirmDelete = false
    @State private var error: String?
    @State private var page: Artifact?
    @State private var preview: URL?

    var body: some View {
        Group {
            if let open {
                detail(open)
            } else if list?.isEmpty == true {
                empty
            } else {
                overview
            }
        }
        .task { await reload() }
        .sheet(item: $page) { artifact in
            if let path = artifact.path {
                PageSheet(artifact: artifact, url: session.api.pageURL(path: path)) {
                    Task {
                        try? await session.api.deleteArtifact(id: artifact.id)
                        if let id = open?.id { await show(id) }
                    }
                }
            }
        }
        .quickLookPreview($preview)
    }

    /// No project yet: the big serif sentence over the forest, as on the web.
    private var empty: some View {
        VStack(alignment: .leading, spacing: 28) {
            Spacer(minLength: 0)
            (Text("projetos").font(Typo.display(36, relativeTo: .largeTitle, italic: true))
                + Text(" são o lugar de cada assunto: as conversas, as páginas e os arquivos dele juntos, e eu lembrando do que foi dito em todas. dê um nome para começar.")
                .font(Typo.display(36, relativeTo: .largeTitle)))
                .shadow(color: palette.usesGlass && palette == .neblinaDia ? .white.opacity(0.45) : .clear, radius: 9)
            createRow(placeholder: "ex.: Viagem a Santiago")
            if let error { errorLine(error) }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(maxWidth: 620)
        .frame(maxWidth: .infinity)
    }

    private var overview: some View {
        GlassPage(
            label: "Projetos", title: "Cada assunto ", italic: "no seu lugar.",
            lede: "Conversas, páginas e arquivos de um assunto juntos. Numa conversa do projeto, eu lembro do que foi falado nas outras."
        ) {
            createRow(placeholder: "Novo projeto, ex.: Viagem a Santiago")
            if let error { errorLine(error) }
            if list == nil { ProgressView().frame(maxWidth: .infinity) }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                ForEach(list ?? []) { project in
                    Button { Task { await show(project.id) } } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Spacer(minLength: 0)
                            Text(project.name)
                                .font(Typo.text(.body, weight: .medium))
                                .multilineTextAlignment(.leading)
                            Text(project.countsLabel)
                                .font(Typo.text(.caption))
                                .foregroundStyle(palette.tintaFraca)
                        }
                        .frame(maxWidth: .infinity, minHeight: 104, alignment: .bottomLeading)
                        .padding(18)
                        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(palette.linhaForte))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .refreshable { await reload() }
    }

    private func detail(_ project: ProjectDetail) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                VStack(alignment: .leading, spacing: 12) {
                    Button {
                        self.open = nil
                        Task { await reload() }
                    } label: {
                        Text("← Projetos")
                            .font(Typo.text(.footnote, weight: .medium))
                            .underline(color: palette.linhaForte)
                    }
                    .buttonStyle(.plain)
                    Text(project.name)
                        .font(Typo.display(40, relativeTo: .largeTitle))
                        .accessibilityAddTraits(.isHeader)
                    FlowButtons {
                        PillButton(title: "Nova conversa aqui", primary: true) { onNew(project.id) }
                        if let current = currentConversation, !project.conversationList.contains(where: { $0.id == current }) {
                            PillButton(title: "Trazer a conversa aberta") { Task { await bring(current, into: project.id) } }
                        }
                        PillButton(title: "Renomear") {
                            newName = project.name
                            renaming = true
                        }
                        PillButton(title: "Apagar") { confirmDelete = true }
                    }
                    if let error { errorLine(error) }
                }
                .padding(.bottom, 16)
                Rectangle().fill(palette.linha).frame(height: 1)
                VStack(alignment: .leading, spacing: 28) {
                    PageGroup(label: "Conversas") {
                        if project.conversationList.isEmpty {
                            Text("Nenhuma ainda. Comece uma aqui ou traga a que está aberta.")
                                .font(Typo.text(.footnote))
                                .foregroundStyle(palette.tintaSuave)
                        }
                        ForEach(project.conversationList) { row in
                            projectRow(row.title, detail: DayLabel.text(for: row.createdAt)) { onOpen(row.id) }
                        }
                    }
                    if !project.pageList.isEmpty {
                        PageGroup(label: "Páginas") {
                            ForEach(project.pageList) { artifact in
                                projectRow(artifact.title, detail: DayLabel.text(for: artifact.createdAt)) { page = artifact }
                            }
                        }
                    }
                    if !project.fileList.isEmpty {
                        PageGroup(label: "Arquivos") {
                            ForEach(project.fileList) { file in
                                let kind = file.isImage ? "Foto" : file.mediaType == "application/pdf" ? "PDF" : "Texto"
                                projectRow(file.filename, detail: "\(kind) · \(AttachmentRules.formatSize(file.sizeBytes))") {
                                    Task { preview = try? await session.loader.file(file) }
                                }
                            }
                        }
                    }
                }
                .padding(.top, 20)
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 22)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glass(palette, cornerRadius: 26)
            .padding(.horizontal, 10)
            .padding(.top, 6)
            .padding(.bottom, 12)
        }
        .scrollIndicators(.hidden)
        .refreshable { await show(project.id) }
        .alert("Novo nome do projeto", isPresented: $renaming) {
            TextField("Nome", text: $newName)
            Button("Cancelar", role: .cancel) {}
            Button("Renomear") { Task { await rename(project.id) } }
        }
        .confirmationDialog("Apagar o projeto “\(project.name)”?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Apagar", role: .destructive) { Task { await remove(project.id) } }
        } message: {
            Text("As conversas, páginas e arquivos continuam, só saem do projeto.")
        }
    }

    private func projectRow(_ title: String, detail: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            PageRow {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Text(title)
                        .font(Typo.text(.subheadline, weight: .medium))
                        .lineLimit(1)
                    Spacer()
                    Text(detail)
                        .font(Typo.text(.caption))
                        .foregroundStyle(palette.tintaFraca)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func createRow(placeholder: String) -> some View {
        HStack(spacing: 8) {
            PageField(placeholder: placeholder, text: $name) { Task { await create() } }
            PillButton(title: "Criar", primary: true) { Task { await create() } }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    private func errorLine(_ text: String) -> some View {
        Label(text, systemImage: "exclamationmark.triangle")
            .font(Typo.text(.footnote))
            .foregroundStyle(palette.erro)
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

    private func reload() async {
        await run { list = try await session.api.projects() }
    }

    private func show(_ id: String) async {
        await run { open = try await session.api.project(id: id) }
    }

    private func create() async {
        let trimmed = String(name.trimmingCharacters(in: .whitespaces).prefix(80))
        guard !trimmed.isEmpty else { return }
        await run {
            let project = try await session.api.createProject(name: trimmed)
            name = ""
            open = try await session.api.project(id: project.id)
            list = try await session.api.projects()
        }
    }

    private func rename(_ id: String) async {
        let trimmed = String(newName.trimmingCharacters(in: .whitespaces).prefix(80))
        guard !trimmed.isEmpty else { return }
        await run {
            _ = try await session.api.renameProject(id: id, name: trimmed)
            open = try await session.api.project(id: id)
        }
    }

    private func remove(_ id: String) async {
        await run {
            try await session.api.deleteProject(id: id)
            open = nil
            list = try await session.api.projects()
            await session.loadHome()
        }
    }

    private func bring(_ conversationId: String, into projectId: String) async {
        await run {
            _ = try await session.api.moveConversation(conversationId, toProject: projectId)
            open = try await session.api.project(id: projectId)
            await session.loadHome()
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
