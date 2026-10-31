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
| 6 | `eval_behavior.py` | mudança observável, atribuível e reversível | −69% palavras após 3 "muito longo" (versão 1, com os 3 retornos como evidência); revertido volta à faixa da linha de base |

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
