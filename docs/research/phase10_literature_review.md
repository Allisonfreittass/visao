# Fase 10A — Revisão crítica: cognição funcional e automodelagem

Data: 31/10/2026 · America/Sao_Paulo. Estudo narrativo crítico; não é revisão sistemática nem implementação. Base de código congelada: `afc2295b8d631e8cb793100a6a92e216bd89230e`; a inspeção local foi realizada na etapa local desta conversa, não repetida na nuvem.

## Conclusão e método

É justificável estudar mecanismos que melhorem decisões, monitoramento de erros e continuidade. Nenhum resultado deste pacote estabelece experiência subjetiva. A questão sobre consciência de IA permanece aberta; indicadores teóricos não são um teste conclusivo aceito.

Seleção intencional de dez fontes primárias selecionadas para os temas do pedido, verificadas em páginas de autores, periódicos ou registros bibliográficos em 31/10/2026. Resumos foram usados quando o texto integral não estava acessível. Não houve busca exaustiva, avaliação formal de viés ou metanálise. Transferir conclusões neurocientíficas para software requer hipóteses adicionais, explicitadas abaixo. As propostas de engenharia são inferências deste estudo, não recomendações demonstradas pelos artigos.

## Cinco níveis que devem permanecer separados

| Nível | Evidência operacional possível | Inferência que não autoriza |
| --- | --- | --- |
| Comportamento expressivo | Texto avaliado como acolhedor ou emotivo por avaliadores | Que o sistema sente o conteúdo expresso |
| Estado funcional | Variável persistida cuja intervenção muda ações previstas | Que orçamento baixo produz sofrimento |
| Automodelo | Inventário revisável de capacidades, limites e resultados | Que existe um eu fenomenológico |
| Metacognição | Monitoramento prevê erros e melhora revisão/abstenção fora da amostra | Que uma explicação verbal revela fielmente toda computação interna |
| Experiência subjetiva | Não há medida conclusiva adotada neste projeto | Que a presença dos quatro níveis anteriores resolve a questão |

“Pensar”, neste projeto, significa recuperar contexto, formular hipóteses, comparar alternativas, escolher ação autorizada, observar resultados e atualizar registros. Pode ser verificado por transições e efeitos. O VISÃO já possui partes desse ciclo; não se deve criar um segundo loop para obter o mesmo comportamento.

## Comparação crítica das abordagens

| Abordagem / fonte | Contribuição e controvérsia | Tradução limitada para VISÃO | Refutação funcional proposta |
| --- | --- | --- | --- |
| Indicadores de consciência [L1][L2] | Derivam propriedades de teorias; dependem da validade e interpretação das teorias e de pressupostos funcionalistas | Usar como perguntas de pesquisa, sem pontuação de “percentual consciente” | Rejeitar alegação de mecanismo quando não existe integração causal mensurável |
| Global neuronal workspace [L3] | Acesso global proposto a partir de processamento neural; acesso, relato e experiência não são conceitos intercambiáveis | Contexto selecionado compartilhado entre componentes, com permissões | Remover contexto compartilhado e medir se coordenação realmente piora; event bus isolado não basta |
| Teste adversarial GNWT/IIT [L4] | Testou previsões divergentes em humanos e desafia aspectos de ambas; não encerra o debate | Pré-definir previsões rivais e publicar resultados desfavoráveis | Comparar explicações rivais; não adaptar hipótese depois de observar resultado |
| Metacognição [L5] | Acurácia de monitoramento é dissociável do desempenho da tarefa | Predição de erro, abstenção e revisão com evidência | Confiança deve discriminar acertos/erros e melhorar decisão; eloquência não conta |
| Attention schema [L6] | Hipótese de um modelo simplificado da própria atenção; escopo e suficiência discutidos | Representar foco, capacidades e limitações é automodelo operacional parcial | Se o modelo não prevê/ajusta alocação, é apenas cadastro descritivo |
| Homeostatic RL [L7] | Modelo normativo vincula recompensa a estabilidade fisiológica; não valida toda analogia biológica | Controlar recurso computacional com limites reais | Redução de orçamento deve reduzir admissões, sem degradar integridade; não denominar fome/dor |
| Appraisal [L8] | Avaliações dinâmicas de relevância e objetivos inspiram arquiteturas; modelar expressão não demonstra sentir | Relevância, bloqueio e risco mudam seleção de tarefas | Ablação de relevância deve mudar prioridade nos casos previstos, sem frases afetivas |
| Free-energy / predictive processing [L9] | Quadro teórico amplo de ação, percepção e aprendizagem; operacionalização é decisiva | Só estudar previsão se houver alvo, horizonte, erro e atualização explícitos | Previsão deve superar baseline simples fora da amostra; scheduler não é automaticamente processamento preditivo |
| IIT 4.0 [L10] | Formalização de propriedades fenomenais por estrutura causal intrínseca, com pressupostos controversos | Nenhuma estimativa de Phi proposta ou realizada | Contar módulos, conexões ou mensagens não testa IIT; não usar essas contagens como substituto |

O relatório de 2023 [L1] avaliou sistemas do seu período. Sua conclusão histórica não pode ser extrapolada para todos os sistemas de 2026. O artigo [L2] saiu online em 10/11/2025, com edição em junho de 2026; o resumo mantém a relevância da incerteza e de implicações funcionalistas investigáveis. Não foi lido integralmente nesta rodada. Para [L4], o registro PubMed e o resumo sustentam apenas a síntese ampla acima; o integral Nature falhou no transporte. Não se inferem resultados experimentais específicos não consultados.

## Oito estados funcionais propostos

Todos são propostas, não capacidades prontas. Persistir valor, unidade, `owner_scope`, entidade-alvo, `observed_at`, fonte, método/versão, validade, razão de atualização e confiança na medição. `unknown` é diferente de zero. O LLM pode sugerir valores; a policy determinística valida domínio, evidência, consentimento e orçamento. Parâmetros iniciais abaixo são hipóteses a calibrar, não medidas da produção.

| Estado | Definição / intervalo | Atualização e decaimento | Proveniência | Efeito decisório | Intervenção / ablação |
| --- | --- | --- | --- | --- | --- |
| Incerteza epistemológica | 0–1, escore de insuficiência de suporte para uma hipótese; não probabilidade calibrada | Sobe com lacuna/contradição; baixa com evidência independente. Não cai pelo tempo; expiração marca desconhecido | KnowledgeGap, fontes e revisões | Aumentar verificação ou adiar afirmação quando relevante | Mesma tarefa com suporte retirado deve aumentar verificação; remover estado testa efeito incremental |
| Relevância da investigação | 0–1, vínculo demonstrável com objetivo autorizado | Atualizar com objetivo/feedback; decair pela metade após 7 dias sem reconfirmação, salvo prazo explícito | Objetivo e consentimento do usuário | Ordenar estudos elegíveis, sem criar autorização | Variar relevância mantendo custo e risco constantes; avaliar ordenação e perguntas indevidas |
| Novidade informacional | 0–1, fração de afirmações verificadas não cobertas pelo corpus recuperado | Recalcular após ingestão/dedup; validade vinculada ao snapshot, sem decaimento temporal independente | IDs de achados e corpus | Evitar pesquisas redundantes | Repetir fonte e paráfrase; novidade lexical deve ser rotulada proxy e não semântica |
| Progresso/bloqueio | Progresso 0–1 de marcos observáveis + bloqueio categórico: nenhum, dependência, permissão, orçamento, falha | Só alterar com marco/evento. Progresso não decai; dependência expira para revisão | Goal, jobs e resultados | Retomar dependência resolvida; não chamar LLM para bloqueio financeiro conhecido | Desbloquear apenas uma dependência; objetivo deve retomar uma vez |
| Conflito de hipóteses | 0–1, proporção ponderada de alegações incompatíveis com suporte rastreável | Revisar com fonte/reconciliação; não decair por silêncio | Pares de afirmações e fontes | Preservar alternativas e evitar conclusão única prematura | Inserir contradição genuína vs divergência irrelevante; medir seletividade |
| Confiança em memória | 0–1, escore de suporte, confirmação e validade por registro; não certeza subjetiva | Confirmar/corrigir com evento; fatos temporais expiram por tipo; fatos estáveis não perdem valor só por idade | Memory, candidato, origem e revisão | Ordenar recuperação e sinalizar incerteza | Fonte corrigida deve invalidar derivadas; remover score mede ganho na recuperação |
| Orçamento de atenção/computação | Inteiros de tokens/chamadas restantes e slots; tempo em ms; USD autorizado sempre 0 | Débito/reserva atômica, reconciliação e renovação em janela definida; não “decaimento emocional” | Ledger de reservas e ModelUsage | Negar/adiar antes de I/O; modo sem LLM | Concorrência e timeout não podem tornar saldo negativo nem admitir endpoint pago |
| Prioridade de tarefa | 0–100, ranking derivado de prazo, relevância, progresso e custo, com risco/permissão como filtros duros | Recalcular em evento; envelhecimento limitado evita starvation, sem superar bloqueios | Decision, estado e fórmula versionada | Escolher próximo job autorizado | Comparar com FIFO e retirar um fator; medir utilidade e starvation |

Evitar dupla contagem: relevância é um insumo, prioridade é derivada; incerteza sobre uma hipótese não é a confiança em toda memória. Persistir snapshots antes/depois permite avaliar efeito. Estados não devem apenas ser interpolados no prompt. A diferença precisa aparecer em ação registrada, prazo, pergunta, verificação ou adiamento. O protocolo F do [plano de avaliação](phase10_evaluation_plan.md) testa esse vínculo.

## SelfModel: visão derivada e revisável

Compor Capabilities, Identity, Decision, jobs, ModelUsage, estudos e erros. Não criar outra identidade nem duplicar memórias. Parte global contém somente fatos operacionais sem conteúdo pessoal. A visão por usuário calcula capacidades efetivas como interseção entre implementação, configuração, saúde e permissão daquele usuário.

Cada afirmação deve conter: chave, valor, escopo, classe `observed`/`hypothesis`/`unknown`, IDs de evidência, SHA/configuração observada, data de revisão, validade, versão e afirmação substituída. Exemplos: “STT implementado; desabilitado no deploy auditado”; “executo investigações autorizadas por worker”; “não posso garantir entrega de push”. Nome permanece opcional; não resetar o nome existente nem obrigar escolha. A referência à gênese `null` descreve a inicialização, não autoriza alteração atual.

Falhas de ferramenta invalidam disponibilidade observada, não apagam a existência da implementação. Expiração de fonte produz `unknown`. Evidência contraditória abre revisão, preservando versões. O renderer deve usar fatos verificados para perguntas diretas de capacidade; o LLM não pode autorizar ferramenta ao alegar que a possui. Checagens futuras devem testar tanto negações falsas de autonomia quanto alegações falsas de sensores/push. O automodelo nunca substitui o controle de acesso.

## Hipóteses e limites de conclusão

H-C1: contexto persistente melhora retomada; H-C2: automodelo reduz erro factual sobre capacidades; H-C3: estados causais melhoram seleção de ações; H-C4: monitoramento prevê erros melhor que confiança constante. Aceitar ou rejeitar cada uma por testes A, E, F e J. Um ganho funcional em qualquer delas não comprova consciência, sentimentos ou identidade pessoal humana. Uma falha funcional também não resolve universalmente o debate sobre consciência de IA.

## Referências e nível de consulta

- [L1] Butlin et al. (2023). *Consciousness in Artificial Intelligence*. [arXiv 2308.08708](https://arxiv.org/abs/2308.08708). Página/resumo verificados; sem nova revisão integral.
- [L2] Butlin et al. (online 2025; edição 2026). *Identifying indicators of consciousness in AI systems*. DOI 10.1016/j.tics.2025.10.011. [PubMed](https://pubmed.ncbi.nlm.nih.gov/41219038/). Registro/resumo, sem leitura integral.
- [L3] Dehaene & Changeux (2011). *Experimental and theoretical approaches to conscious processing*. [PubMed](https://pubmed.ncbi.nlm.nih.gov/21521609/). Resumo.
- [L4] Cogitate Consortium (2025). *Adversarial testing of global neuronal workspace and integrated information theories of consciousness*. DOI 10.1038/s41586-025-08888-1. [PubMed](https://pubmed.ncbi.nlm.nih.gov/40307561/). Registro/resumo; integral Nature indisponível no transporte.
- [L5] Fleming & Dolan (2012). *The neural basis of metacognitive ability*. [PubMed](https://pubmed.ncbi.nlm.nih.gov/22492751/), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3318765/). Resumo PubMed; PMC bloqueou leitura nesta rodada.
- [L6] Graziano & Webb (2015). *The attention schema theory*. [Frontiers](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00500/full). Página integral acessível, consulta focal.
- [L7] Keramati & Gutkin (2014). *Homeostatic reinforcement learning*. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4270100/). Consulta focal de página integral.
- [L8] Scherer (2009). *Emotions are emergent processes*. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC2781886/). Consulta focal de página integral.
- [L9] Friston (2010). *The free-energy principle: a unified brain theory?* DOI 10.1038/nrn2787. [PubMed](https://pubmed.ncbi.nlm.nih.gov/20068583/). Resumo; Nature indisponível.
- [L10] Albantakis et al. (2023). *Integrated information theory (IIT) 4.0*. DOI 10.1371/journal.pcbi.1011465. [PLOS](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011465). Página integral acessível, consulta focal; nenhum cálculo aplicado ao VISÃO.

[L1]: https://arxiv.org/abs/2308.08708
[L2]: https://pubmed.ncbi.nlm.nih.gov/41219038/
[L3]: https://pubmed.ncbi.nlm.nih.gov/21521609/
[L4]: https://pubmed.ncbi.nlm.nih.gov/40307561/
[L5]: https://pubmed.ncbi.nlm.nih.gov/22492751/
[L6]: https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00500/full
[L7]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4270100/
[L8]: https://pmc.ncbi.nlm.nih.gov/articles/PMC2781886/
[L9]: https://pubmed.ncbi.nlm.nih.gov/20068583/
[L10]: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011465

## Consolidação local — 01/11/2026

Os seis documentos foram reunidos em `docs/research/` e copiados para o pacote de entrega local. A auditoria original do estado atual foi preservada por conter evidências mais detalhadas; os outros cinco documentos vieram da tarefa em nuvem e passaram por revisão local de conteúdo, referências e escopo. HEAD permanece no SHA auditado. Os resultados de testes continuam sendo os da etapa local de 31/10/2026; não houve nova execução das suítes nem dos experimentos nesta consolidação. Nenhuma implementação, migração, commit, push ou publicação foi realizada.
