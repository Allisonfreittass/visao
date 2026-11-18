import SwiftUI
import VisaoKit

/// Início: everything that waits for a yes, a no or a read (InboxView.tsx).
struct InicioView: View {
    let currentConversation: String?
    let onOpenConversation: (String) -> Void
    /// Opens the chat with this text in the box (a suggestion, "Criar um novo painel").
    let onDraft: (String) -> Void
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette

    @State private var panels: [LivePanel]?
    @State private var macOnline: Bool?

    private var pending: PendingStore { session.pending }
    private var online: Bool { session.listError == nil }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                hero
                content
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 24)
            .frame(maxWidth: 760)
            .frame(maxWidth: .infinity)
        }
        .scrollIndicators(.hidden)
        .safeAreaInset(edge: .bottom) { HomeBox(onDraft: onDraft) }
        .refreshable { await pending.refresh() }
        .task {
            await pending.refresh()
            macOnline = (try? await session.api.armDevices()).flatMap { list in list.isEmpty ? nil : list.contains { $0.online } }
        }
    }

    /// The mascot, "Boa noite, Allison." / "Estou de olho em 2 painéis." (the number in red),
    /// and the status line, all from real data.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 12) {
            SentinelaView(state: online ? .idle : .offline, size: 64)
            Group {
                if let count = HomeLines.watchCount(panels) {
                    Text("\(Opening.greeting()), \(OwnerName.value).\n") + Text("Estou de olho em ") + Text(count).foregroundColor(palette.redText) + Text(".")
                } else {
                    Text("\(Opening.greeting()), \(OwnerName.value).\nNada sob vigilância ainda.")
                }
            }
            .font(Typo.display(32, relativeTo: .largeTitle))
            .foregroundStyle(palette.text)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityAddTraits(.isHeader)
            Text(HomeLines.status(online: online, macOnline: macOnline, pendingCount: pending.count, panels: panels))
                .font(Typo.text(.subheadline, weight: .medium))
                .foregroundStyle(palette.textMuted)
        }
        .padding(.top, 12)
    }

    @ViewBuilder
    private var content: some View {
            PanelsSection(nothingPending: pending.count == 0, onDraft: onDraft, onPanels: { panels = $0 })
            let mac = pending.asks.filter { if case .arm = $0.source { true } else { false } }
            let google = pending.asks.filter { if case .google = $0.source { true } else { false } }
            let panels = pending.asks.filter { if case .panel = $0.source { true } else { false } }
            if !panels.isEmpty {
                PageGroup(label: "Painéis") {
                    ForEach(panels) { ask in
                        if case .panel(let offer) = ask.source {
                            item(id: ask.id, title: "Deixo isto no Início?", lines: [offer.summary], date: offer.createdAt) { approve in
                                Task { await pending.decide(ask, approve: approve) }
                            }
                        }
                    }
                }
            }
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
                Text("Nada esperando você. O que eu quiser fazer por conta própria aparece aqui antes.")
                    .font(Typo.text(.footnote))
                    .foregroundStyle(palette.textMuted)
            }
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

/// Início's message box, above the tab bar: what you write goes to the chat's box, ready to send.
private struct HomeBox: View {
    let onDraft: (String) -> Void
    @State private var text = ""
    @FocusState private var focused: Bool
    @Environment(\.palette) private var palette

    var body: some View {
        HStack(spacing: 6) {
            TextField("Dê uma ordem ao Visão", text: $text, axis: .vertical)
                .font(Typo.text(.body))
                .lineLimit(1...4)
                .focused($focused)
                .padding(.leading, 14)
                .padding(.vertical, 12)
                .submitLabel(.send)
                .onSubmit(send)
                .accessibilityLabel("Mensagem")
            if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Button(action: send) {
                    Image(systemName: "arrow.up")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(palette.onRed)
                        .frame(width: 40, height: 40)
                        .background(palette.red, in: Circle())
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Enviar para o chat")
            }
        }
        .padding(2)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).strokeBorder(palette.border))
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private func send() {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        text = ""
        focused = false
        onDraft(value)
    }
}
