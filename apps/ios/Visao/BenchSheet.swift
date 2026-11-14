import SwiftUI
import VisaoKit

/// The Bancada of a conversation (Bench.tsx): what it is doing now, the pages, the sites it read
/// live and what it really did, taken from the system's record, not from what it said.
struct BenchSheet: View {
    let conversationId: String
    let working: Bool
    let steps: [ProgressStep]
    let onOpenPage: (Artifact) -> Void
    @Environment(Session.self) private var session
    @Environment(Appearance.self) private var appearance
    @State private var bench: Bench?

    private var palette: Palette { appearance.palette }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    card("Agora") {
                        if working {
                            let shown = steps.isEmpty ? [ProgressStep(label: "Pensando")] : steps
                            ForEach(Array(shown.enumerated()), id: \.offset) { index, step in
                                HStack(alignment: .top, spacing: 8) {
                                    Group {
                                        if index == shown.count - 1 { ProgressView().controlSize(.mini) } else { Image(systemName: "checkmark").font(.caption2.weight(.bold)) }
                                    }
                                    .frame(width: 18, height: 18)
                                    .foregroundStyle(palette.estanho)
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(step.label).font(Typo.text(.subheadline, weight: index == shown.count - 1 ? .medium : .regular))
                                        if let detail = step.detail { Text(detail).font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca) }
                                    }
                                }
                            }
                        } else {
                            quiet("Parado. Quando você pedir algo, cada passo aparece aqui.")
                        }
                    }
                    if let pages = bench?.pages, !pages.isEmpty {
                        card("Páginas") {
                            ForEach(pages) { page in
                                Button { if page.status == "ready" { onOpenPage(page) } } label: {
                                    row(page.title, page.status == "ready" ? "Abrir" : page.status == "pending" ? "Criando…" : "Não deu certo")
                                }
                                .buttonStyle(.plain)
                                .disabled(page.status != "ready")
                            }
                        }
                    }
                    if let visits = bench?.visits, !visits.isEmpty {
                        card("Lido ao vivo") {
                            ForEach(visits, id: \.self) { visit in
                                if let url = URL(string: visit.url), ["http", "https"].contains(url.scheme ?? "") {
                                    Link(destination: url) {
                                        row(visit.title, "\(url.host() ?? visit.url) · \(visit.at.formatted(date: .omitted, time: .shortened))")
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                    card("O que fiz de verdade") {
                        if let deeds = bench?.deeds, !deeds.isEmpty {
                            ForEach(deeds, id: \.self) { deed in
                                HStack(alignment: .firstTextBaseline, spacing: 10) {
                                    Text(deed.at.formatted(date: .omitted, time: .shortened))
                                        .font(Typo.mono(.caption2)).foregroundStyle(palette.tintaFraca)
                                    Text(deed.text).font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                                }
                            }
                        } else {
                            quiet(bench == nil ? "Lendo…" : "Nada além de conversar, por enquanto.")
                        }
                        Text("Tirado do registro do sistema, não do que eu disse.")
                            .font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
                            .padding(.top, 4)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Bancada")
            .navigationBarTitleDisplayMode(.inline)
            .refreshable { await load() }
        }
        .environment(\.palette, palette)
        .foregroundStyle(palette.tinta)
        .task { await load() }
    }

    private func card<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(Typo.display(22, relativeTo: .title3))
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glass(palette, cornerRadius: 22, shadow: false)
    }

    private func row(_ title: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(Typo.text(.subheadline, weight: .medium)).lineLimit(1)
            Text(detail).font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func quiet(_ text: String) -> some View {
        Text(text).font(Typo.text(.footnote)).foregroundStyle(palette.tintaFraca)
    }

    private func load() async {
        do {
            bench = try await session.api.bench(conversationId: conversationId)
        } catch {
            session.handle(error)
        }
    }
}
