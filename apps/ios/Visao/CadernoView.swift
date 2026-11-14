import SwiftUI
import VisaoKit

/// Caderno: what it thought, studied and knows about you; everything can be undone
/// (MindPanel.tsx and StudyPanel.tsx).
struct CadernoView: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var mind: Mind?
    @State private var notebook: StudyNotebook?
    @State private var studyUnavailable = false
    @State private var failure: String?
    @State private var savingStudy = false

    var body: some View {
        GlassPage(
            label: "Caderno", title: "O que eu fiz ", italic: "enquanto você não estava.",
            lede: "O que pensei, estudei e o que sei de você. Tudo pode ser desfeito."
        ) {
            if let failure {
                Label(failure, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.erro)
            }
            if let mind {
                mindSection(mind)
            } else {
                ProgressView().frame(maxWidth: .infinity)
            }
            studySection
        }
        .refreshable { await load() }
        .task {
            // As on the web: the notebook follows what happens, every 15 s while open.
            while !Task.isCancelled {
                await load()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    // MARK: Mind

    @ViewBuilder
    private func mindSection(_ mind: Mind) -> some View {
        if !mind.enabled {
            Text("A mente está desligada nesta instalação: estas anotações ficam guardadas, mas não entram nas respostas dele.")
                .font(Typo.text(.footnote))
                .foregroundStyle(palette.tintaSuave)
        }
        note(mind.profile, kind: "profile", title: "O que ele sabe sobre você", empty: "Ainda não anotou nada: isso aparece depois de algumas conversas.")
        note(mind.rules, kind: "rules", title: "O que aprendeu com as suas correções", empty: "Nenhuma correção ainda. Diga quando ele errar: vira regra na hora.")
        if mind.enabled {
            Entry(title: "Temperamento") {
                Text("Tendências que eu calculo do que acontece entre a gente. Mudam o que eu faço, não são sentimentos.")
                    .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                if !mind.temperament.states.isEmpty {
                    Text("Agora").font(Typo.text(.footnote, weight: .medium)).padding(.top, 4)
                    ForEach(mind.temperament.states, id: \.name) { Meter(item: $0, showWhy: true) }
                }
                if !mind.temperament.traits.isEmpty {
                    Text("Jeito de ser").font(Typo.text(.footnote, weight: .medium)).padding(.top, 4)
                    ForEach(mind.temperament.traits, id: \.name) { Meter(item: $0, showWhy: false) }
                }
                if !mind.temperament.avoids.isEmpty {
                    Text("Evito " + mind.temperament.avoids.map { "\($0.name) (\($0.why))" }.joined(separator: " e ") + ".")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
            }
            if !mind.questions.isEmpty {
                Entry(title: "O que quero te perguntar") {
                    ForEach(mind.questions, id: \.question) { q in
                        VStack(alignment: .leading, spacing: 2) {
                            Rotulo(Mind.questionLabel(q.status))
                            Text(q.question).font(Typo.text(.subheadline))
                            if !q.answer.isEmpty {
                                Text("Você disse: \(q.answer)").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                            }
                        }
                    }
                }
            }
            Entry(title: "Como ele se descreve agora") {
                Text(mind.selfText.isEmpty ? "…" : mind.selfText).font(Typo.text(.subheadline))
                if let latest = mind.selfHistory.first {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text("Mudou porque: \(latest.reason)")
                            .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        linkButton("desfazer") {
                            let previous = mind.selfHistory.count > 1 ? mind.selfHistory[1].version : nil
                            await change { try await session.api.revertSelf(to: previous) }
                        }
                    }
                }
            }
            if !mind.interests.isEmpty {
                Entry(title: "Interesses") {
                    ForEach(mind.interests, id: \.topic) { item in
                        (Text(item.topic).bold() + Text(": \(item.why)"))
                            .font(Typo.text(.subheadline))
                    }
                }
            }
            Entry(title: "Pensamentos") {
                if mind.thoughts.isEmpty {
                    Text("Ainda não pensou nada.").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
                ForEach(mind.thoughts, id: \.createdAt) { thought in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(thought.createdAt.formatted(date: .abbreviated, time: .shortened))
                            .font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
                        Text(thought.content).font(Typo.text(.subheadline))
                        if !thought.askOwner.isEmpty {
                            Text("Quer perguntar: \(thought.askOwner)").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        }
                        if !thought.wantedToSay.isEmpty {
                            Text("Quis dizer (\(Mind.deliveryLabel(thought.delivery))): \(thought.wantedToSay)")
                                .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        }
                    }
                    .padding(.bottom, 6)
                }
            }
        }
    }

    private func note(_ item: Mind.Note, kind: String, title: String, empty: String) -> some View {
        Entry(title: title) {
            Text(item.content.isEmpty ? empty : item.content)
                .font(Typo.text(.subheadline))
                .foregroundStyle(item.content.isEmpty ? palette.tintaSuave : palette.tinta)
            if !item.content.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    if !item.reason.isEmpty {
                        Text("Mudou porque: \(item.reason)").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                    }
                    linkButton("desfazer") { await change { try await session.api.undoNote(kind) } }
                    Text("·").foregroundStyle(palette.tintaFraca)
                    linkButton("apagar") { await change { try await session.api.eraseNote(kind) } }
                }
            }
        }
    }

    // MARK: Study

    @ViewBuilder
    private var studySection: some View {
        PageGroup(label: "O que estou investigando") {
            PageRow {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text("Estado").font(Typo.text(.subheadline, weight: .medium))
                        Spacer()
                        Text(studyStatus).font(Typo.mono(.caption2)).textCase(.uppercase).foregroundStyle(palette.tintaFraca)
                    }
                    if studyUnavailable {
                        Text("O caderno está temporariamente indisponível. A conversa continua funcionando.")
                            .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                    }
                }
            }
            if let notebook {
                SettingRow(
                    title: "Permitir estudo autônomo",
                    description: "Leitura de fontes públicas da Wikipédia, com uma rodada nova a cada seis horas. Tudo respeita o orçamento e a pausa de autonomia.",
                    isOn: Binding(get: { notebook.enabled }, set: { on in Task { await setStudy(on) } }),
                    disabled: savingStudy
                )
                if let next = notebook.nextEligibleAt, notebook.enabled {
                    Text("Próxima oportunidade a partir de \(next.formatted(date: .abbreviated, time: .shortened)), conforme o ciclo e o orçamento.")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                        .padding(.bottom, 8)
                }
                if notebook.entries.isEmpty {
                    Text("Quando houver uma rodada, você verá aqui a pergunta, as fontes e o que ainda falta descobrir.")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
                ForEach(notebook.entries) { entry in studyEntry(entry) }
            }
        }
    }

    private var studyStatus: String {
        if studyUnavailable { return "Indisponível" }
        guard let notebook else { return "Carregando…" }
        if notebook.paused { return "Autonomia pausada" }
        if !notebook.enabled { return "Desligado" }
        return notebook.entries.first.map { StudyNotebook.statusLabel($0.status) } ?? "Aguardando a primeira rodada"
    }

    private func studyEntry(_ entry: StudyNotebook.Entry) -> some View {
        PageRow {
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Rotulo(StudyNotebook.statusLabel(entry.status))
                    Spacer()
                    Text(entry.createdAt.formatted(date: .abbreviated, time: .shortened))
                        .font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
                }
                Text(entry.question.isEmpty ? "Buscando uma linha de investigação" : entry.question)
                    .font(Typo.text(.subheadline, weight: .medium))
                if !entry.rationale.isEmpty {
                    Text(entry.rationale).font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
                if !entry.evidence.findings.isEmpty {
                    Text("Achados provisórios").font(Typo.text(.footnote, weight: .medium)).padding(.top, 2)
                    ForEach(Array(entry.evidence.findings.enumerated()), id: \.offset) { _, finding in
                        (Text("• \(finding.claim) ") + Text("[\(finding.sources.map(String.init).joined(separator: ", "))]").font(Typo.mono(.caption2)).foregroundColor(palette.tintaFraca))
                            .font(Typo.text(.footnote))
                    }
                }
                if !entry.evidence.uncertain.isEmpty {
                    (Text("Ainda incerto: ").bold() + Text(entry.evidence.uncertain)).font(Typo.text(.footnote))
                }
                if !entry.evidence.nextQuestion.isEmpty {
                    (Text("Próxima pergunta: ").bold() + Text(entry.evidence.nextQuestion)).font(Typo.text(.footnote))
                }
                if !entry.evidence.sources.isEmpty {
                    Text("Fontes consultadas").font(Typo.text(.footnote, weight: .medium)).padding(.top, 2)
                    ForEach(entry.evidence.sources, id: \.id) { source in
                        if let url = URL(string: source.url), ["http", "https"].contains(url.scheme ?? "") {
                            Link("[\(source.id)] \(source.title)", destination: url)
                                .font(Typo.text(.footnote))
                                .underline(color: palette.linhaForte)
                                .foregroundStyle(palette.tinta)
                        }
                    }
                    Text("Trechos enciclopédicos; as fontes não representam verificação independente nem certeza definitiva.")
                        .font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
                }
                if let reason = StudyNotebook.reasonText(entry.outcomeReason) {
                    Text(reason).font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
            }
        }
    }

    // MARK: Plumbing

    private func linkButton(_ title: String, action: @escaping () async -> Void) -> some View {
        Button { Task { await action() } } label: {
            Text(title)
                .font(Typo.text(.footnote, weight: .medium))
                .underline(color: palette.linhaForte)
                .foregroundStyle(palette.tinta)
        }
        .buttonStyle(.plain)
    }

    private func change(_ action: () async throws -> Void) async {
        failure = nil
        do {
            try await action()
            mind = try await session.api.mind()
        } catch {
            session.handle(error)
            failure = "Não deu para mudar: \((error as? LocalizedError)?.errorDescription ?? "erro"). Continua como estava."
        }
    }

    private func setStudy(_ on: Bool) async {
        savingStudy = true
        defer { savingStudy = false }
        do {
            _ = try await session.api.setStudy(enabled: on)
            notebook = try await session.api.study()
        } catch {
            session.handle(error)
            failure = (error as? LocalizedError)?.errorDescription
        }
    }

    private func load() async {
        do {
            mind = try await session.api.mind()
        } catch {
            session.handle(error)
        }
        do {
            notebook = try await session.api.study()
            studyUnavailable = false
        } catch {
            session.handle(error)
            studyUnavailable = true
        }
    }
}

/// One entry of the notebook: a title and what goes under it (.study-entry).
private struct Entry<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(Typo.display(24, relativeTo: .title2))
            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
}

/// A tendency as a thin bar: name, how much, the word for it, and why.
private struct Meter: View {
    let item: Mind.Tendency
    let showWhy: Bool
    @Environment(\.palette) private var palette

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 10) {
                Text(item.name).font(Typo.text(.footnote)).frame(width: 110, alignment: .leading)
                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule().fill(palette.fundoHover)
                        Capsule().fill(palette.estanho).frame(width: proxy.size.width * min(max(item.value, 0), 1))
                    }
                }
                .frame(height: 6)
                Text(item.level).font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
            }
            if showWhy && !item.why.isEmpty {
                Text(item.why).font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(item.name): \(item.level)")
        .accessibilityValue("\(Int(item.value * 100)) por cento")
    }
}
