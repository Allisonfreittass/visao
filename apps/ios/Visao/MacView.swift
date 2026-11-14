import SwiftUI
import UIKit
import VisaoKit

/// Mac: the paired machines and what it did there (MacView.tsx). Pairing shows a secret token
/// once, to paste on the Mac.
struct MacView: View {
    @Environment(Session.self) private var session
    @Environment(\.palette) private var palette
    @State private var devices: [ArmDevice] = []
    @State private var tasks: [ArmTask] = []
    @State private var loaded = false
    @State private var pairing: PairedDevice?
    @State private var unpairing: ArmDevice?
    @State private var busy = false
    @State private var copied = false
    @State private var error: String?

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
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
                    .font(Typo.text(.footnote)).foregroundStyle(palette.erro)
            }
            PageGroup(label: "Aparelhos") {
                if devices.isEmpty && loaded {
                    Text("Nenhum Mac pareado ainda.")
                        .font(Typo.text(.footnote))
                        .foregroundStyle(palette.tintaSuave)
                }
                if let pairing {
                    PageRow {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Cole este token em ~/.config/visao/braco.json")
                                .font(Typo.text(.subheadline, weight: .medium))
                            Text(pairing.token)
                                .font(Typo.mono(.footnote))
                                .textSelection(.enabled)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            Text("Ele não aparece de novo. Depois rode bash arm/instalar-mac.sh no Mac.")
                                .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                            HStack(spacing: 8) {
                                PillButton(title: copied ? "Copiado" : "Copiar", primary: true) {
                                    UIPasteboard.general.string = pairing.token
                                    copied = true
                                }
                                PillButton(title: "Pronto") {
                                    self.pairing = nil
                                    copied = false
                                }
                            }
                        }
                    }
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
                            HStack {
                                Spacer()
                                PillButton(title: "Desconectar") { unpairing = device }
                            }
                        }
                    }
                }
                if pairing == nil {
                    PageRow {
                        PillButton(title: devices.isEmpty ? "Parear um Mac" : "Parear outro Mac", primary: true, busy: busy) {
                            Task { await pair() }
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
        .confirmationDialog("Desconectar \(unpairing?.name ?? "o Mac")?", isPresented: Binding(get: { unpairing != nil }, set: { if !$0 { unpairing = nil } }), titleVisibility: .visible) {
            Button("Desconectar", role: .destructive) {
                guard let device = unpairing else { return }
                Task {
                    do { try await session.api.unpairArm(id: device.id) } catch { self.error = (error as? LocalizedError)?.errorDescription }
                    await load()
                }
            }
        } message: {
            Text("O braço dele para na hora.")
        }
    }

    private func pair() async {
        busy = true
        defer { busy = false }
        do {
            pairing = try await session.api.pairArm(name: "Mac")
            error = nil
            await load()
        } catch {
            session.handle(error)
            self.error = (error as? LocalizedError)?.errorDescription
        }
    }

    private func load() async {
        async let d = try? session.api.armDevices()
        async let t = try? session.api.armTasks()
        devices = await d ?? devices
        tasks = await t ?? tasks
        loaded = true
    }
}
