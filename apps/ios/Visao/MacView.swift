import SwiftUI
import VisaoKit

/// Mac: the paired machines and what it did there (MacView.tsx). Pairing a new Mac shows a
/// secret token, so it stays on the site, where you copy it to the Mac.
struct MacView: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var devices: [ArmDevice] = []
    @State private var tasks: [ArmTask] = []
    @State private var loaded = false

    private static let status: [String: String] = [
        "proposed": "esperando você", "approved": "na fila", "running": "rodando", "done": "feito",
        "failed": "falhou", "rejected": "recusado", "cancelled": "cancelado",
    ]

    var body: some View {
        GlassPage(
            label: "Mac",
            title: devices.isEmpty && loaded ? "Conecte o seu " : "Trabalho no seu ",
            italic: "Mac.",
            lede: "Eu peço ao Claude Code nos projetos que você liberou. Escreva /mac projeto o que fazer na conversa."
        ) {
            PageGroup(label: "Aparelhos") {
                if devices.isEmpty && loaded {
                    Text("Nenhum Mac pareado. Pareie pelo site, em Mac, e cole o token no Mac.")
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                }
                ForEach(devices) { device in
                    PageRow {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(spacing: 8) {
                                Circle()
                                    .fill(device.online ? palette.sucesso : palette.tintaFraca)
                                    .frame(width: 7, height: 7)
                                Text("\(device.name) · \(device.online ? "ligado" : "desligado")")
                                    .font(Typo.text(.subheadline, weight: .medium))
                            }
                            Text(device.projects.isEmpty ? "Nenhum projeto liberado no braco.json." : device.projects.joined(separator: ", "))
                                .font(Typo.text(.footnote))
                                .foregroundStyle(palette.tintaSuave)
                        }
                    }
                }
            }
            PageGroup(label: "O que eu fiz lá") {
                let history = tasks.filter { $0.status != "proposed" }
                if history.isEmpty && loaded {
                    Text("Nada ainda.")
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                }
                ForEach(history) { task in
                    PageRow {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(task.project).font(Typo.text(.subheadline, weight: .medium))
                                Spacer()
                                Text(Self.status[task.status] ?? task.status)
                                    .font(Typo.mono(.caption2))
                                    .textCase(.uppercase)
                                    .foregroundStyle(task.status == "failed" ? palette.erro : palette.tintaFraca)
                            }
                            Text(task.prompt)
                                .font(Typo.text(.footnote))
                                .foregroundStyle(palette.tintaSuave)
                                .lineLimit(3)
                            Text(DayLabel.text(for: task.createdAt))
                                .font(Typo.mono(.caption2))
                                .foregroundStyle(palette.tintaFraca)
                        }
                    }
                }
            }
        }
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        async let d = try? session.api.armDevices()
        async let t = try? session.api.armTasks()
        devices = await d ?? devices
        tasks = await t ?? tasks
        loaded = true
    }
}
