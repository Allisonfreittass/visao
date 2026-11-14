import SwiftUI
import VisaoKit

/// Início: Pendências, everything that waits for a yes, a no or a read (InboxView.tsx).
struct InicioView: View {
    let currentConversation: String?
    let onOpenConversation: (String) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette

    private var pending: PendingStore { session.pending }

    var body: some View {
        GlassPage(
            label: "Pendências",
            title: pending.count == 0 ? "Nada esperando " : "O que precisa ",
            italic: pending.count == 0 ? "por você." : "de você.",
            lede: "Eu só proponho. Nada roda sem o seu sim."
        ) {
            let mac = pending.asks.filter { if case .arm = $0.source { true } else { false } }
            let google = pending.asks.filter { if case .google = $0.source { true } else { false } }
            if !mac.isEmpty {
                PageGroup(label: "No Mac") {
                    ForEach(mac) { ask in
                        if case .arm(let task) = ask.source {
                            item(id: ask.id, title: "Posso fazer em \(task.project)?", lines: [task.prompt], date: task.createdAt) { approve in
                                Task { await pending.decide(ask, approve: approve) }
                            }
                        }
                    }
                }
            }
            if !google.isEmpty {
                PageGroup(label: "Email e agenda") {
                    ForEach(google) { ask in
                        if case .google(let action) = ask.source {
                            let isEmail = action.kind == "send_email"
                            let extra = isEmail ? action.payload.body : action.payload.location.map { "Local: \($0)" }
                            item(
                                id: ask.id, title: isEmail ? "Posso mandar este email?" : "Posso marcar isto?",
                                lines: [action.summary] + (extra.map { [$0] } ?? []), date: action.createdAt
                            ) { approve in
                                Task {
                                    let ok = await pending.decide(ask, approve: approve)
                                    if ok { await session.loadHome() }
                                }
                            }
                        }
                    }
                }
            }
            if !pending.goals.isEmpty {
                PageGroup(label: "Metas que eu quero seguir") {
                    ForEach(pending.goals) { goal in
                        let needs = goal.requiredPermissions.isEmpty ? [] : ["Preciso de: \(goal.requiredPermissions.joined(separator: ", "))"]
                        item(id: goal.id, title: goal.title, lines: [goal.rationale] + needs, date: nil) { approve in
                            Task { await pending.decide(goal, approve: approve) }
                        }
                    }
                }
            }
            if !pending.notices.isEmpty {
                PageGroup(label: "Avisos") {
                    ForEach(pending.notices) { notice in
                        PageRow {
                            VStack(alignment: .leading, spacing: 10) {
                                texts(title: notice.title, lines: [notice.body], date: notice.createdAt)
                                HStack(spacing: 8) {
                                    PillButton(title: "Responder", primary: true) {
                                        Task {
                                            if let id = await pending.reply(notice, from: currentConversation) {
                                                await session.loadHome()
                                                onOpenConversation(id)
                                            }
                                        }
                                    }
                                    PillButton(title: "Dispensar") { Task { await pending.dismiss(notice) } }
                                }
                            }
                        }
                    }
                }
            }
            if pending.count == 0 {
                Text("Quando eu quiser fazer algo por conta própria, aparece aqui primeiro.")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.tintaSuave)
            }
        }
        .refreshable { await pending.refresh() }
        .task { await pending.refresh() }
    }

    private func item(id: String, title: String, lines: [String], date: Date?, decide: @escaping (Bool) -> Void) -> some View {
        PageRow {
            VStack(alignment: .leading, spacing: 10) {
                texts(title: title, lines: lines, date: date)
                HStack(spacing: 8) {
                    PillButton(title: "Aprovar", primary: true, busy: pending.deciding.contains(id)) { decide(true) }
                    PillButton(title: "Recusar") { decide(false) }
                }
                .disabled(pending.deciding.contains(id))
            }
        }
    }

    private func texts(title: String, lines: [String], date: Date?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(Typo.text(.subheadline, weight: .medium))
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                if !line.isEmpty {
                    Text(line)
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let date {
                Text(DayLabel.text(for: date))
                    .font(Typo.mono(.caption2))
                    .foregroundStyle(palette.tintaFraca)
            }
        }
    }
}
