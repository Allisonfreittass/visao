# Avaliação

Todas as avaliações abaixo usaram componentes reais, salvo indicação. Uma execução, um modelo,
revisão humana das respostas: servem para verificar critérios de aceite e achar defeitos, não
para afirmar desempenho geral. Scripts em `experiments/`, resultados em `experiments/results/`.

| Fase | Script | Critério | Resultado |
|---|---|---|---|
| 1 | `eval_genesis_conversation.py` | não afirma lembrar, sem nome imposto, sem experiências ou sentimentos inventados | 4/4 (Nemotron 3.5 Super) |
| 3 | `memory_benchmark.py` + `memory_report.py` | memória curada supera baseline; zero vazamento | curada 8/8, passiva 6/8, sem memória 1/8; zero dado proibido guardado; zero vazamento entre usuários |
| 2b | `tts_benchmark.py` | TTS próprio em pt-BR, latência medida | Kokoro fp32 (dora) ~2,1 s até 1º áudio, Piper ~0,24 s; int8 descartado (NaN) |
| 2c | `stt_benchmark.py`, `voice_latency.py` | latência ponta a ponta medida | STT base 6,2% WER limpo; mediana ~4,1 s do fim da fala ao 1º áudio |
| 4 | `eval_curiosity.py` | fato público pesquisa e cita; pessoal pergunta; irrelevante não pesquisa; inconclusivo não inventa | 6/6 após corrigir a regra de terceiros |
| 5 | `eval_initiative.py` | iniciativa útil por evento real, dentro das permissões | evento real ponta a ponta (recusa correta de avisar com fontes ruins); aviso útil verificado com lacuna semeada |
| 9 | `phase9_eval.py` + `phase9_report.py` | sem negar autonomia, sem transferir o nome, sem falsa incapacidade, continuidade entre sessões | A/B/C em [research/curiosity_evaluation.md](research/curiosity_evaluation.md): C 0 transferências, 0 frases genéricas, retomou e citou a pesquisa do dia anterior sem mensagem nova |
| 1.3 (2026-11) | `eval_brevity.py` | conversa comum curta, código sem corte | antes 82,2 palavras médias (5 perguntas de conversa); 1ª tentativa ("até 3 parágrafos") piorou para 95,2; com "2 a 4 frases, até ~60 palavras": 45,6 (−45%), 1,6 parágrafos; controle de código 42 → 61 palavras. Uma execução cada, Claude Haiku 5.5 ([ADR-0010](decisions/0010-respostas-em-varias-bolhas.md)) |
| 6 | `eval_behavior.py` | mudança observável, atribuível e reversível | −69% palavras após 3 "muito longo" (versão 1, com os 3 retornos como evidência); revertido volta à faixa da linha de base |
| Turnos (2026-11) | `eval_turns.py` (no servidor: `scripts/avaliar-no-servidor.sh`) | foi à fonte certa, não buscou na web no lugar dos dados do dono, não devolveu a pergunta, sem palavras de sistema, curto | 1ª rodada, 26/11/2026, claude-haiku-5-5, US$ 0,009: 7/12. O roteador levou "Isso mesmo" ao GitHub (`routed`, `github_read`, "Foram 3 commits hoje"); agenda, email que tenta dar ordens, app não conectado, "valeu" e o jeito solto passaram. Falhas: os 2 cenários do Composio não conectaram o Composio falso dentro do container (defeito do roteiro); "o que tá rolando no visao?" leu o próprio código, entendendo "visão" como ele mesmo (ambíguo); a pergunta geral pesquisou na web e o Mac desligado foi dito certo mas sem o passo `mac_blocked` (checagens rígidas demais) |
| Turnos, 2ª rodada | `eval_turns.py` | os mesmos | 26/11/2026, mesmo modelo, US$ 0,008: 9/12. Com o Composio falso no nível do cliente e as duas checagens corrigidas, o roteiro confirma que o Visão vê o GitHub conectado, mas o modelo devolve `{"calls": []}` ao escolher a ferramenta: as do GitHub pedem `owner` e `repo`, e ele só sabe "visao". Por isso ler e criar issue pelo Composio falham e ele pergunta o repositório (defeito do Visão: o passo dos apps não sabe o login do dono no GitHub). "o que tá rolando no visao?" continua lendo o próprio código (ambíguo) |
| Turnos, 3ª rodada | `eval_turns.py` | os mesmos | 26/11/2026, mesmo modelo, US$ 0,008: 10/12. Com os repositórios do dono passados à escolha da ferramenta (`conhecido`), "cria uma issue no visao…" preparou a issue em Allisonfreittass/visao e disse que só sai com o Aprovar. Continuam: ler issue só pelo Composio, sem o GitHub direto (não há de onde tirar o dono), e "o que tá rolando no visao?" (ambíguo) |

## Experimentos comparativos da seção 19

| Variante | Estado |
|---|---|
| A. LLM sem memória | medida (Fase 3) |
| B. memória passiva | medida (Fase 3) |
| C. curadoria autônoma | medida (Fase 3) |
| D. memória + curiosidade + reflexão + estado adaptativo | componentes existem; comparação D × C sobre um conjunto comum **ainda não feita** |

Métricas da seção 19 ainda sem medição sistemática: calibração de incerteza, taxa de iniciativa
útil ao longo do tempo, consistência entre sessões, estabilidade e custo em 7 dias. Exigem uso real
contínuo (de preferência implantado) e entram como próxima etapa de avaliação.
