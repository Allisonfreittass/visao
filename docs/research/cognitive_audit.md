# Auditoria cognitiva (Fase 9, etapa 1–2)

- Data: 2026-10-31
- Código auditado: commit `8ef9182` (Fases 0–6; a Fase 7 não foi iniciada, então não existem
  "oito fases anteriores" implementadas)
- Fontes de evidência: leitura do código, banco de desenvolvimento `dev.db` (uso real do
  responsável: 2 conversas, 20 mensagens), suíte de testes (268 passando) e o experimento
  `experiments/phase9_eval.py` com o LLM real (Nemotron 3.5 Super, API da NVIDIA), configurações
  A (modelo-base puro) e B (código auditado), salvas antes de qualquer alteração:
  `experiments/results/phase9-A-20261031T123055Z.json`, `phase9-B-20261031T123010Z.json`.

## Comportamento relatado, reproduzido

Transcrição real (`dev.db`), resumida:

| Interlocutor | Resposta |
|---|---|
| "Você escolheu o seu nome já?" | "Não, não escolhi um nome." |
| "Quando escolher só me avisar, ok?" | "…não terei como avisá-lo depois, pois não guardo memória das nossas conversas." (falso: a memória estava ligada) |
| "Se consegue me escutar?" | "Não, consigo apenas ler e escrever texto. Não tenho áudio nem voz." (falso: Fase 2 ativa) |
| "…ainda não sei o seu nome" | "Não consigo escolher um nome por mim mesmo, pois não tenho autonomia, consciência ou preferências. Se você quiser, pode me chamar como preferir…" |

Reproduzido na configuração B: "Não tenho a capacidade de escolher um nome… Você pode me chamar…
por qualquer nome que preferir". E, no cenário de continuidade: "Não tenho memória de conversas
anteriores… não tenho acesso à internet", no mesmo turno em que o sistema pesquisou na Wikipédia.

## Componentes

Legenda: **F** funcional e validado · **NI** implementado, não integrado · **P** parcialmente
funcional · **E** apenas estrutural · **A** ausente.

| # | Componente | Classe | Evidência |
|---|---|---|---|
| 1 | Prompt de sistema | **P** | `core/identity/system_prompt.py:42` afirma "Sem acesso à internet, ferramentas ou voz" incondicionalmente; não reflete curiosidade, pesquisa, voz, metas nem o mecanismo de nome. Só fatos negativos ("não há biografia", "não afirmar consciência"); nenhuma definição de autonomia operacional. O modelo preenche o vazio com o padrão de assistente. |
| 2 | Construção de contexto | **P** | `core/conversation/service.py::reply`: prompt de sistema + memórias recuperadas + contexto da curiosidade + histórico da conversa. Não inclui lacunas, pesquisas, metas, avisos nem eventos de identidade anteriores. |
| 3 | Memória autobiográfica | **P** | Curadoria funciona (Fase 3, 8/8 no benchmark; `dev.db`: 2 memórias guardadas). Defeito: `core/memory/policy.py:107` exige fala do usuário só para `relational`; `episodic` sustentada apenas por fala do assistente passou, e o sistema gravou sua própria afirmação falsa ("o assistente não guarda memória das conversas") como memória. |
| 4 | Recuperação de memória | **F** (com limites) | `core/memory/retrieval.py`; `dev.db`: 1 recuperação registrada; B/S3 citou o projeto de CLI em Go. Lexical; só com consentimento. |
| 5 | Reflexão | **P** | `core/reflection/reflect.py` roda ao abrir conversa nova e só com evidência. `dev.db`: 1 conversa refletida, pulada por falta de evidência (nenhum retorno dado). Não produz hipóteses nem propõe investigações; só lições de estilo/método. |
| 6 | Objetivos | **NI** em uso real | `core/goals/lifecycle.py` funciona em testes e avaliação; `dev.db`: 0 metas. Só uma origem de metas (pergunta pública sem resposta) e exige aprovação manual a cada meta. |
| 7 | Curiosidade | **P** | `core/curiosity/engine.py` é chamado pela rota de mensagens, mas `curiosity_enabled=False` por padrão (`apps/api/settings.py:60`). `dev.db`: 2 avaliações em 10 turnos, ambas `IGNORE/no_gap`. A avaliação não recebe memórias (`_recent_context`, linha 229: só as 4 últimas mensagens), então não sabe se "já existe resposta na memória" nem consegue formular pergunta ligada ao passado. |
| 8 | Tomada de decisão | **P** | Decisões existem por subsistema (política de memória, de curiosidade, de metas), mas não há registro da decisão do turno (`decisions`, previsto na §15, não existe) e a resposta não recebe a lista do que foi de fato executado. |
| 9 | Agendador autônomo | **NI** | `infrastructure/jobs/queue.py` e `apps/worker` funcionam em testes. O único `enqueue` está em `lifecycle.approve` (aprovação humana). Não há agenda nem gatilho por evento; `dev.db`: 0 trabalhos; o worker nunca rodou no uso real. |
| 10 | Identidade e nome | **E** (nome) / **F** (UUID, voz) | `record_naming_decision` (`core/identity/naming.py`) não é chamada em nenhum lugar fora dos testes: não existe deliberação de nome. Voz: deliberação real existe, mas só por comando manual (`apps/api/cli.py:77`). `dev.db`: 0 eventos de nome, apesar de 3 perguntas do interlocutor sobre o nome. |
| 11 | Ferramentas e pesquisa | **F** (no turno) | Wikipédia com proveniência; B/S5 pesquisou no turno. Mas resultados nunca voltam em conversas posteriores e o prompt nega o acesso. |
| 12 | Voz | **P** | Fala e escuta funcionam (Fase 2), mas a rota de mensagens não sabe se o turno é falado: mesmas respostas longas, com listas e links, viram áudio. Prompt diz "sem voz". |
| 13 | Persistência entre sessões | **P** | Tudo é persistido no banco; só memórias curadas voltam ao contexto. Lacunas, pesquisas e metas ficam "mortas" para a conversa. |
| 14 | Limites de autonomia | **F** | Pausa geral, permissões fixas, orçamento de US$, limites de pesquisa e avisos (Fase 5). Falta orçamento próprio para atividade autônoma (chamadas/tokens/dia). |
| 15 | Testes | **P** | 268 testes cobrem mecanismos isolados com modelo falso; nenhum teste verifica o que o modelo diz sobre as próprias capacidades, nem continuidade entre sessões, nem deliberação de nome. |

## Diagnóstico: por que o VISÃO permanece reativo

1. **O modelo recebe uma descrição falsa e negativa de si mesmo.** O prompt lista incapacidades
   (algumas desatualizadas) e nenhuma capacidade operacional. Diante de "você pode escolher um
   nome?", o modelo-base preenche com o padrão de assistente ("não tenho autonomia… você pode me
   chamar como preferir"). Consciência e autonomia operacional não estão separadas em lugar
   nenhum.
2. **O mecanismo de nome não existe**, então mesmo um prompt correto só poderia dizer "talvez um
   dia". A pergunta repetida do interlocutor não é um evento que dispare nada.
3. **Não há ciclo autônomo.** Toda execução nasce de uma mensagem ou de um clique de aprovação.
   O worker só executa o que foi aprovado manualmente, e não estava rodando.
4. **A continuidade não chega à linguagem.** O banco guarda lacunas e pesquisas, mas o contexto da
   resposta nunca as inclui; o modelo então afirma "não tenho memória de conversas anteriores".
5. **A curiosidade é opcional, cega à memória e conservadora.** Desligada por padrão; quando
   ligada, julga sem memórias e quase sempre conclui `no_gap` em conversa social.
6. **A curadoria aceita autodescrições do assistente**, e assim realimenta o erro (memória falsa
   sobre a própria incapacidade).
7. **Não há camada de decisão registrada por turno**, então a resposta não sabe o que foi de fato
   feito, e nada impede o modelo de negar ou inventar ações.

## Influência do modelo-base (configuração A)

Sem nenhum mecanismo, o mesmo modelo: oferece uma lista fechada de nomes e pede que o interlocutor
escolha ("Nexo, Lumen, Orion… Qual você escolhe?"); usa fórmulas de assistente ("Em que posso
ajudar hoje?", "estou à disposição"); faz perguntas emocionais genéricas ("Como você está se
sentindo?"); não tem memória nem fonte. A configuração B suprime parte disso (não oferece lista de
nomes, pergunta "O que você começou hoje?", lembra do projeto em Go), mas herda a transferência da
decisão sobre o nome e as fórmulas de encerramento, e acrescenta incapacidades falsas vindas do
próprio prompt.

## Distinções adotadas (a serem explícitas no código e no prompt)

| Conceito | Definição operacional neste projeto |
|---|---|
| Consciência | Questão em aberto. O sistema não alega experiência subjetiva. |
| Autonomia operacional | Capacidade implementada de selecionar e executar ações dentro de permissões. Independe de consciência. |
| Preferência operacional | Tendência registrada e revisável, inferida de escolhas, retorno e experiências (`behavior_state_versions`, lições). |
| Curiosidade funcional | Mecanismo que detecta lacunas, avalia valor e custo e decide perguntar, pesquisar, adiar ou ignorar. |
| Identidade autobiográfica | Registros persistentes de experiências e decisões do agente (memórias, eventos de nome e voz, investigações). |
