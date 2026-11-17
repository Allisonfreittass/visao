import SwiftUI
import VisaoKit

/// The live panels on Início (docs/PAINEIS.md): native cards the server keeps up to date. A new
/// card comes in with a spring, the total rolls to a new number when a check changes it, and
/// tapping a card opens its history, its sites, pause and delete (PanelsBoard.tsx on the web).
struct PanelsSection: View {
    let nothingPending: Bool
    let onDraft: (String) -> Void
    /// In a project's card: only its panels, without suggestions or "Criar", and nothing when
    /// it has none.
    var projectId: String? = nil
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var panels: [LivePanel]?
    @State private var suggested: [PanelSuggestion] = []

    var body: some View {
        if projectId != nil && panels?.isEmpty != false {
            Color.clear.frame(height: 0).task { await load() }
        } else {
            board
        }
    }

    private var board: some View {
        PageGroup(label: "Painéis") {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(panels ?? []) { panel in
                    PanelCard(panel: panel) { await load() }
                        .transition(reduceMotion ? .opacity : .scale(scale: 0.96).combined(with: .opacity))
                }
                if panels?.isEmpty == true && nothingPending && projectId == nil {
                    if !suggested.isEmpty {
                        Text("Sugestões: tocar escreve o pedido na conversa, e nada roda antes de você mandar.")
                            .font(Typo.text(.footnote))
                            .foregroundStyle(palette.tintaSuave)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ForEach(suggested, id: \.text) { suggestion in
                        PillButton(title: suggestion.text) { onDraft(suggestion.draft) }
                    }
                }
                if projectId == nil {
                    PillButton(title: "+ Criar um novo painel") { onDraft("Quero acompanhar ") }
                }
            }
            .animation(reduceMotion ? nil : .spring(response: 0.45, dampingFraction: 0.8), value: panels?.map(\.id))
        }
        .task {
            await load()
            // The server checks once a day; looking again every minute is plenty.
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(60))
                await load()
            }
        }
    }

    private func load() async {
        guard let all = try? await session.api.panels() else { return }
        let list = projectId.map { id in all.filter { $0.projectId == id } } ?? all
        panels = list
        if list.isEmpty && nothingPending && projectId == nil, let ideas = try? await session.api.panelSuggestions() {
            suggested = ideas
        }
    }
}

private struct PanelCard: View {
    let panel: LivePanel
    let reload: () async -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var open = false
    @State private var detail: LivePanel?
    @State private var confirmDelete = false

    private let positive = Color(red: 0.18, green: 0.49, blue: 0.31)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                withAnimation(reduceMotion ? nil : .spring(duration: 0.35)) { open.toggle() }
            } label: {
                header
            }
            .buttonStyle(.plain)
            .accessibilityHint(open ? "Fecha o detalhe" : "Abre o histórico e os sites")
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(panel.items.enumerated()), id: \.offset) { _, item in itemRow(item) }
                if panel.items.isEmpty {
                    Text("Os preços ainda estão a confirmar.").font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
            }
            Text([PanelText.checked(panel), PanelText.watch(panel), panel.note.isEmpty ? nil : panel.note].compactMap { $0 }.joined(separator: " · "))
                .font(Typo.mono(.caption2))
                .foregroundStyle(palette.tintaFraca)
            if open { details }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.bolhaDele, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .shadow(color: palette.sombra.opacity(0.6), radius: 8, y: 3)
        .opacity(panel.status == "paused" ? 0.7 : 1)
        .task(id: open) { if open { detail = try? await session.api.panel(id: panel.id) } }
        .confirmationDialog("Apagar o painel “\(panel.title)”?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Apagar", role: .destructive) {
                Task {
                    try? await session.api.deletePanel(id: panel.id)
                    await reload()
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Rotulo(panel.status == "paused" ? "Pausado" : "Painel")
            Text(panel.title).font(Typo.text(.headline, weight: .medium))
            Text(PanelText.brl(panel.total) ?? "a confirmar")
                .font(Typo.display(40, relativeTo: .largeTitle))
                .monospacedDigit()
                .contentTransition(reduceMotion ? .identity : .numericText(value: panel.totalValue ?? 0))
                .animation(reduceMotion ? nil : .snappy, value: panel.total)
            if let travelers = panel.spec.travelers, travelers > 1 {
                Text("total para \(travelers)").font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
            }
            if let words = panel.goalWords {
                Text(words)
                    .font(Typo.text(.footnote, weight: .medium))
                    .foregroundStyle(panel.isBelowGoal ? positive : palette.tintaSuave)
            }
            if panel.changeValue != 0 {
                let down = panel.changeValue < 0
                let amount = PanelText.brl("\(abs(NSDecimalNumber(decimal: panel.changeValue).doubleValue))") ?? ""
                Label("\(amount) desde a última conferência", systemImage: down ? "arrow.down" : "arrow.up")
                    .font(Typo.mono(.caption2))
                    .foregroundStyle(down ? positive : palette.erro)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private func itemRow(_ item: PanelItem) -> some View {
        HStack(alignment: .center, spacing: 10) {
            // No third-party logos without a clear license: the provider's initial.
            Text(String(item.provider.prefix(1)).uppercased())
                .font(Typo.text(.subheadline, weight: .semibold))
                .foregroundStyle(palette.tintaSuave)
                .frame(width: 32, height: 32)
                .background(palette.fundoHover, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(item.provider).font(Typo.text(.subheadline, weight: .medium))
                Text([item.kind == "flight" ? "Voo" : "Hospedagem", item.where].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(Typo.text(.caption)).foregroundStyle(palette.tintaSuave)
                let stops = item.kind == "flight" ? item.connections.map { $0 == 0 ? "direto" : "\($0) parada\($0 > 1 ? "s" : "")" } : nil
                let extra = [item.dates, stops ?? ""].filter { !$0.isEmpty }.joined(separator: " · ")
                if !extra.isEmpty { Text(extra).font(Typo.text(.caption)).foregroundStyle(palette.tintaSuave) }
            }
            Spacer(minLength: 8)
            Text(PanelText.brl(item.cost) ?? "a confirmar")
                .font(Typo.text(.subheadline, weight: .medium))
                .monospacedDigit()
                .contentTransition(reduceMotion ? .identity : .numericText())
        }
        .accessibilityElement(children: .combine)
    }

    private var details: some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()
            if let history = detail?.history, history.count > 1 {
                ForEach(history, id: \.checkedAt) { point in
                    HStack {
                        Text(point.checkedAt.formatted(.dateTime.day(.twoDigits).month(.twoDigits)))
                            .font(Typo.mono(.caption)).foregroundStyle(palette.tintaFraca)
                        Text(PanelText.brl(point.total) ?? "a confirmar").font(Typo.text(.footnote)).monospacedDigit()
                    }
                }
            }
            ForEach(panel.items.filter { !$0.url.isEmpty }, id: \.url) { item in
                if let url = URL(string: item.url) {
                    Link("\(item.site.isEmpty ? "site" : item.site): \(item.provider)", destination: url)
                        .font(Typo.text(.footnote))
                }
            }
            HStack(spacing: 8) {
                PillButton(title: panel.status == "paused" ? "Retomar" : "Pausar") {
                    Task {
                        try? await session.api.setPanel(id: panel.id, paused: panel.status != "paused")
                        await reload()
                    }
                }
                PillButton(title: "Apagar") { confirmDelete = true }
            }
        }
        .transition(.opacity)
    }
}
