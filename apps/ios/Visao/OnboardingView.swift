import SwiftUI
import VisaoKit

/// The first run (Onboarding.tsx): how it works, a few questions and the permissions. Shown once,
/// always skippable; the answers only stay if memory is on.
struct OnboardingView: View {
    let status: OnboardingStatus
    let onDone: () -> Void
    @Environment(Session.self) private var session
    @Environment(Appearance.self) private var appearance
    @State private var step = 1
    @State private var answers = OnboardingAnswers()
    @State private var permissions: (memory: Bool, study: Bool, research: Bool)?
    @State private var saving: String?
    @State private var failure: String?
    @State private var notice: String?

    private var palette: Palette { appearance.palette }

    private let points = [
        ("Lembra de você", "Se você ligar a memória, guarda entre conversas o que for útil sobre você."),
        ("Pensa e estuda entre conversas", "Um processo roda em segundo plano, chama o modelo e parte do que vocês conversaram. Estudar sozinho só com a sua permissão."),
        ("Puxa conversa", "Pode mandar mensagem sem você pedir. Fica quieto no horário silencioso e para se você não responder."),
        ("Aprende com correções", "Quando você corrige o jeito dele, isso vira uma regra curta para as próximas conversas."),
        ("Você vê e desfaz", "No Caderno ficam as anotações, os pensamentos e os estudos. Anotações e autodescrição dá para desfazer; anotações, também apagar."),
    ]

    private let questions: [(WritableKeyPath<OnboardingAnswers, String>, String, String)] = [
        (\.who, "Quem é você?", "Nome, como prefere ser chamado, o que quiser contar."),
        (\.work, "No que você trabalha?", "Profissão, projetos, o que ocupa seus dias."),
        (\.goal, "O que você quer dele?", "Pensar junto, acompanhar um projeto, lembrar das coisas."),
        (\.tone, "Como prefere que ele fale com você?", "Direto, curto, com exemplos, sem formalidade."),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Rotulo("Passo \(step) de 3")
                    Spacer()
                    PillButton(title: answers.wroteSomething ? "Descartar e pular tudo" : "Pular tudo") { Task { await skipAll() } }
                        .disabled(saving != nil)
                }
                if let failure {
                    Label(failure, systemImage: "exclamationmark.triangle")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.erro)
                }
                switch step {
                case 1: howItWorks
                case 2: questionsStep
                default: permissionsStep
                }
                actions
            }
            .padding(24)
            .glass(palette, cornerRadius: 32)
            .padding(.horizontal, 14)
            .padding(.vertical, 24)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)
            .animation(.spring(duration: 0.35), value: step)
        }
        .scrollDismissesKeyboard(.interactively)
        .visaoBackground()
        .interactiveDismissDisabled()
    }

    private var howItWorks: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Como ele funciona").font(Typo.display(34, relativeTo: .largeTitle)).accessibilityAddTraits(.isHeader)
            Text("Isto é software: um modelo de linguagem com memória, estudo e iniciativa em volta. Em resumo:")
                .font(Typo.text(.callout)).foregroundStyle(palette.tintaSuave)
            ForEach(points, id: \.0) { title, text in
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Typo.text(.subheadline, weight: .medium))
                    Text(text).font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
            }
            if !status.mindEnabled {
                Text("Nesta instalação a mente está desligada: pensar entre conversas, puxar conversa e usar as anotações nas respostas só funcionam quando ela for ligada.")
                    .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
            }
        }
    }

    private var questionsStep: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Algumas perguntas").font(Typo.display(34, relativeTo: .largeTitle)).accessibilityAddTraits(.isHeader)
            Text("Todas opcionais. Só ficam guardadas se a memória estiver ligada no próximo passo. Não escreva senhas nem documentos.")
                .font(Typo.text(.callout)).foregroundStyle(palette.tintaSuave)
            ForEach(questions, id: \.1) { key, label, hint in
                VStack(alignment: .leading, spacing: 6) {
                    Text(label).font(Typo.text(.footnote, weight: .medium)).foregroundStyle(palette.tintaSuave)
                    TextField(hint, text: Binding(get: { answers[keyPath: key] }, set: { answers[keyPath: key] = $0 }), axis: .vertical)
                        .lineLimit(2...5)
                        .font(Typo.text(.body))
                        .padding(12)
                        .background(palette.fundoElevado, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
            }
            Text("Espaço livre nas anotações: \(status.room.profile) caracteres para quem você é, \(status.room.rules) para o jeito de falar. Se já houver algo anotado, as respostas entram depois, sem apagar nada.")
                .font(Typo.text(.caption)).foregroundStyle(palette.tintaFraca)
        }
    }

    private var permissionsStep: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("O que ele pode fazer").font(Typo.display(34, relativeTo: .largeTitle)).accessibilityAddTraits(.isHeader)
            Text("Cada chave vale assim que você muda e aparece como está agora. Depois você muda tudo em Ajustes e no Caderno.")
                .font(Typo.text(.callout)).foregroundStyle(palette.tintaSuave)
            if let permissions {
                SettingRow(title: "Memória entre conversas", description: "Guarda informações selecionadas e as suas respostas daqui. Desligada, nada disso fica.",
                           isOn: Binding(get: { permissions.memory }, set: { on in Task { await toggle("memory", on) } }), disabled: saving != nil)
                SettingRow(title: "Estudo autônomo", description: "Estuda temas ligados a você entre as conversas, dentro do orçamento. Cada rodada fica no Caderno.",
                           isOn: Binding(get: { permissions.study }, set: { on in Task { await toggle("study", on) } }), disabled: saving != nil)
                SettingRow(title: "Pesquisa autônoma", description: "Dúvidas de fatos públicos que ficaram sem resposta são pesquisadas de novo, sem pedir aprovação a cada vez.",
                           isOn: Binding(get: { permissions.research }, set: { on in Task { await toggle("research", on) } }), disabled: saving != nil)
                if answers.wroteSomething {
                    Text(permissions.memory
                         ? "Memória ligada: suas respostas vão para as anotações dele, e você pode desfazer ou apagar no Caderno."
                         : "Memória desligada: nada do que você escreveu será guardado.")
                        .font(Typo.text(.footnote)).foregroundStyle(palette.tintaSuave)
                }
            } else {
                ProgressView().frame(maxWidth: .infinity).task { await loadPermissions() }
            }
        }
    }

    private var actions: some View {
        FlowButtons {
            if step > 1 { PillButton(title: "Voltar") { step -= 1 } }
            PillButton(title: step == 2 ? "Pular sem responder" : "Pular esta etapa") {
                if step == 3 { Task { await finish() } } else {
                    if step == 2 { answers = OnboardingAnswers() }
                    step += 1
                }
            }
            PillButton(title: saving == "finish" ? "Salvando…" : step == 3 ? "Concluir" : "Continuar", primary: true) {
                if step == 3 { Task { await finish() } } else { step += 1 }
            }
        }
        .disabled(saving != nil)
        .padding(.top, 6)
    }

    private func loadPermissions() async {
        do {
            async let settings = session.api.serverSettings()
            async let study = session.api.study()
            let (s, n) = try await (settings, study)
            permissions = (s.memory, n.enabled, s.autoResearch)
        } catch {
            session.handle(error)
            failure = "Não deu para ler as permissões: \((error as? LocalizedError)?.errorDescription ?? "erro")"
        }
    }

    private func toggle(_ key: String, _ on: Bool) async {
        guard var current = permissions else { return }
        saving = key
        defer { saving = nil }
        do {
            switch key {
            case "memory": current.memory = try await session.api.setMemory(enabled: on)
            case "study": current.study = try await session.api.setStudy(enabled: on)
            default: current.research = try await session.api.setAutoResearch(on)
            }
            permissions = current
        } catch {
            failure = "Não deu para mudar, continua como estava: \((error as? LocalizedError)?.errorDescription ?? "erro")"
        }
    }

    private func finish() async {
        saving = "finish"
        defer { saving = nil }
        do {
            _ = try await session.api.finishOnboarding(answers)
            onDone()
        } catch {
            // A refusal is about the answers: back to them, with the text intact.
            if (error as? APIError)?.status == 422 { step = 2 }
            failure = (error as? LocalizedError)?.errorDescription
        }
    }

    private func skipAll() async {
        saving = "finish"
        defer { saving = nil }
        do {
            _ = try await session.api.skipOnboarding()
            onDone()
        } catch {
            failure = "Não deu para pular: \((error as? LocalizedError)?.errorDescription ?? "erro")"
        }
    }
}
