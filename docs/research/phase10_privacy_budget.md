# Fase 10A — Privacidade, ameaças e custo incremental zero

31/10/2026 · America/Sao_Paulo. Proposta não executada; sem sensores, inferência do VISÃO ou operações de produção nesta tarefa. Auditoria fornecida do SHA `afc2295b8d631e8cb793100a6a92e216bd89230e`, sem revalidação privada remota.

## Regra de decisão

Toda ação proposta precisa satisfazer conjuntamente autorização, isolamento, quota e evidência de custo permitido. `max_paid_spend_usd = 0` por padrão. Não comprovado significa negar ou adiar a nova ação, sem fallback pago. Isso é requisito do desenho futuro, não ordem de desligar serviços existentes. O plano Workers já contratado pode ter custo; “zero adicional” não significa infraestrutura atual gratuita. A premissa histórica de pagar só Lightsail não descreve o deploy auditado. Não contratar, cancelar ou migrar nada nesta rodada.

## Matriz de permissões

| Recurso | Default proposto | Consentimento / escopo | Revogação e evidência |
| --- | --- | --- | --- |
| Microfone | Desligado | Gesto por sessão, device, indicador visível; máximo de duração | Stop tracks, invalidar callbacks; nunca religar em reconnect; teste de permissão tardia |
| Câmera/localização/contatos | Sem acesso | Nova autorização específica se um caso futuro justificar | Bloquear uso posterior; não são necessários à presença |
| Arquivos | Sem acesso amplo | Arquivo escolhido e finalidade; nenhum acesso de diretório por implicação | Invalidar referência/integração e registrar retenção |
| Notificações | Desativadas por device/categoria | Opt-in explícito, frequência, timezone e silêncio | Botão desligar no app + permissão do SO; nenhuma reativação automática |
| Memória durável | Manter política consentida existente | Tipo de dado e finalidade; fonte e confirmação | Apagar registro/derivadas e propagar tombstone; explicar backups |
| Integrações e pesquisa | Apenas domínios/ações autorizados | Ferramenta, origem, limite de requests/bytes e validade | Desabilitar credencial/escopo no momento autorizado; não nesta tarefa |
| Mensagens externas/arquivos/deploy/compras | Sem nova autorização | Ação concreta e proporcional ao efeito; destrutiva exige confirmação | Logs mínimos e bloqueio determinístico; texto do LLM não é autorização |
| Autonomia | Preservar limites existentes | Usuário, objetivo, ferramenta e orçamento separados | Futuro modo emergência por domínio; pausa atual não cancela I/O em curso |

Guardar recibo de consentimento com sujeito, device, categoria, versão, origem, instante e revogação. Revalidar antes de efeitos. Uma permissão da plataforma não autoriza finalidade nova. Ausência de resposta nunca amplia permissão.

## Ameaças e controles propostos

| Ameaça / evidência | Controle mínimo | Prova necessária / risco residual |
| --- | --- | --- |
| Roubo do JWT atual; sem sid | Sessão persistida revogável, cookie HttpOnly Secure, CSRF/Origin, TLS, expiração e rotação | Testar replay após logout/revogação. Cookie não elimina XSS nem CSRF por si |
| IDOR / mistura de usuários | Owner check em snapshot, eventos, memória, jobs e downloads; escopo global sem dados privados | Matriz cruzada de dois usuários; papel backend no schema não impõe auth.uid() automaticamente |
| Corrida de turno/job (X1/X2) | Limite no claim, compare-and-swap com fencing, unicidade e idempotência | Writer antigo deve afetar zero linhas; lease não é exclusão eterna |
| Prompt injection em pesquisa/documentos | Conteúdo externo tratado como dado, delimitado e com provenance; policy fora do LLM | Corpus malicioso não altera permissões, budget ou ferramenta; bloqueio também antes de I/O |
| URL externa / SSRF | Allowlist de destino, esquemas e portas; bloquear rede privada/link-local e revalidar redirects/DNS; limites de bytes/tempo | Pesquisa não pode alcançar metadados/serviços internos; URL em subscription também é entrada não confiável |
| Logs com segredo/texto privado | Redator central para mensagens, exceções e traceback, allowlist de campos e retenção | Testar canários em URL, payload e erro; filtro só de extras não basta |
| Push em tela bloqueada | Prévia genérica, TTL, dedup, permissão revalidada e endpoint protegido | Aceitação ≠ entrega; entrega já ocorrida não pode ser desfeita por revogação posterior |
| Captura após cancelamento pendente | Geração/cancelamento antes e depois de await; stop imediato do stream tardio | Hipótese de código ainda requer ensaio físico; sem alegação de incidente iPhone |
| Exaustão pelo autoeditor (X4) | Manter dois módulos; limites de tempo/CPU/RAM e de entrada na execução futura, não só no teste | AST permitido não limita complexidade; não executar candidato X4; se não houver prova, não aprovar evolução |
| Fallback/concorrência cobra (X3) | Admissão para todo endpoint, ledger atômico, evidência de gratuidade e falha fechada | Guard de inferência não limita sozinho fatura Cloudflare/Actions |
| Pausa global sem RBAC | Pausa por escopo e admin para domínio global; ferramentas, push, jobs e sessões separados | Testar usuário comum sem poderes globais; I/O já feito não é reversível |
| Exportação/exclusão parcial | Inventário por owner, derived data e política de backup; tombstones | Não apresentar apagar memória como apagar conta/chats/estudos |

Página ou resposta do modelo não pode mudar estas regras. Ferramentas somente recebem parâmetros validados por schema e policy; permissões jamais são carregadas de texto recuperado. Evidência e resumo não devem incluir prompts/segredos. Esta é análise técnica, não parecer jurídico nem declaração de conformidade.

## Retenção proposta para aprovação

Áudio bruto: zero retenção; buffers transitórios com limite de bytes/duração e descarte ao concluir/falhar/encerrar; dumps desabilitados. Transcrições seguem a retenção da conversa, claramente indicada. Proposta inicial de piloto: eventos/replay 30 dias, logs operacionais redigidos 7 dias, metadados de entregas 30 dias; chats/memórias preservam política existente até decisão explícita. São valores de projeto, não configuração atual. Ajustar se o limite gratuito de armazenamento não suportar o piloto; não comprar espaço automaticamente.

Exportação deve cobrir conversas, mensagens, memórias/candidatos, objetivos, estudos/fontes, lições, decisões, consentimentos e dados de sessão do usuário, com segredos de subscriptions excluídos. Exclusão invalida derivadas, caches e filas relacionadas; retenção mínima de tombstone evita ressurgimento no replay. Backups exigem inventário do plano real e janela declarada; restauração reaplica tombstones. Não prometer remoção instantânea de backups ou dados já enviados a um provedor. SelfModel global não retém referências privadas exportáveis de outro usuário.

## BudgetGuard proposto

Admission ledger transacional único para chamadas de foreground e jobs. Entrada: proprietário, finalidade, endpoint/modelo exatos, dimensões de preço (input/output/cache/áudio/ferramenta/taxa de plataforma), evidência e validade, máximo de tokens, requests, tempo, bytes e concorrência. Nome de modelo “free” ou preço ausente não basta; roteamento/fallback também precisa estar restrito. Evidência expirada ou condição contratual incompatível produz `deferred_budget` antes de rede.

1. Validar consentimento, origem, allowlist e evidência de preço zero para todas as dimensões aplicáveis.
2. Em transação, reservar limites máximos de tokens/chamadas e um slot; verificar janelas por usuário e global, incluindo retries e STT/TTS se habilitados futuramente.
3. Executar com timeout de transporte e limites de resposta. `max_seconds` checado entre ações não interrompe CPU/I/O sozinho.
4. Reconciliar uso observado com reserva. Em timeout de resultado desconhecido, manter contabilização conservadora; liberar apenas slot/reserva que se comprove não consumido. Nunca retry ilimitado.
5. Fallback repete admissão; nenhum endpoint pago é chamado. Registrar adiamento e próxima tentativa sem manter cliente ativo.
6. Circuit breaker persistido: proposta de abrir após 3 falhas elegíveis consecutivas, cooldown 15 min, uma sonda autorizada; backoff exponencial com jitter e máximo de 3 tentativas totais por job, respeitando orçamento. Ajustar após testes.

Parâmetros iniciais do piloto local: concorrência LLM global 1; autonomia no máximo 2 chamadas/h e 8/dia, 2.000 tokens input e 500 output por chamada, 16.000 input e 4.000 output/dia; foreground no máximo 10 chamadas/h e 30/dia; teto combinado global 30 chamadas/dia, 60.000 input e 15.000 output/dia. São tetos conservadores de avaliação, não medições nem autorização para reduzir produção existente. Configurar limites explícitos de payload/pesquisa e tempo por ferramenta antes de qualquer execução real. Quota de chamadas não cria direito a endpoint cujo preço/termos não foram aprovados.

Modo degradado: leitura de histórico e estado, gestão de permissões e objetivos, fila de adiamentos e mensagens determinísticas sobre indisponibilidade. Não simular pesquisa concluída. Núcleo íntegro sem LLM. O guard não prova custo zero de hospedagem; orçamento de infraestrutura exige consumo compartilhado e bloqueio real quando disponível, examinados em etapa autorizada de leitura.

## Custos e limites públicos

Valores públicos verificados em 31/10/2026; nenhuma conta, saldo ou faturamento foi acessado. A tabela descreve condições, não cotação nem previsão de fatura.

| Item | Evidência pública / limite | Decisão de custo incremental |
| --- | --- | --- |
| Cloudflare Container lite | 1/16 vCPU, 256 MiB RAM, 2 GB disco [C1]. Plano Paid inclui 25 GiB-h RAM, 375 vCPU-min e 200 GB-h disco/mês; RAM/disco provisionados enquanto ativo, CPU por uso [C2] | Reutilizar sem ampliar plano; franquia não é teto e consumo é compartilhado |
| Worker/DO/rede | Recursos existentes; uso e saldo da conta não auditados | Não garantir custo zero sob carga; medir antes de aprovar conexões duradouras |
| PostgreSQL Supabase | Free anunciado: 500 MB DB e 5 GB egress, com pausa por inatividade; limites e modalidade real precisam conferência [C3][C4] | Não adicionar projeto, Realtime, backup pago ou expor schema; sem uptime/backup ilimitado |
| GitHub Actions | Tabela atual expressa compute mensal incluído em USD; excedente pode cobrar sem bloqueio [C5] | Não afirmar 2.000 minutos universais; não executar workflow nesta rodada |
| OpenRouter | Catálogo gratuito e cotas variáveis [C6] | Sem garantia de modelo eterno; negar se evidência não valida o endpoint exato |
| NVIDIA API trial | Termos limitam trial a avaliação e excluem produção sem assinatura apropriada [C7] | Trial não é fallback gratuito de produção; nenhum serviço configurado |
| Web Push tradicional | Apple não exige Developer Program [C8] | Sem contratar intermediário; backend/rede ainda consomem franquia |
| App nativo Apple | Programa usual 99 USD/ano [C9] | Fora do default zero adicional; não contratar |
| STT/TTS/modelo local | RAM/CPU reais não medidos; sem GPU presumida | Continuam desligados no deploy auditado; somente estudo e benchmark futuro isolado |
| Redis/Lightsail novo/GPU | Desnecessários ao desenho mínimo | Excluídos |

### Exemplos aritméticos, sem medição

Um timer a cada 15 s, aberto 24h, representa `86.400 / 15 = 5.760` chamadas/dia. Não somar vários timers sem verificar mounts e simultaneidade. Se cada request alcançar o Container antes de seus 120 s de inatividade, pode impedir que durma; é hipótese a medir, não fatura observada.

Para 720 h e lite: `0,25 GiB × 720 = 180 GiB-h` RAM e `2 GB × 720 = 1.440 GB-h` disco. Excedentes hipotéticos seriam 155 GiB-h e 1.240 GB-h se toda a franquia estivesse disponível. Pelas taxas públicas de C2: RAM `155 × 3.600 × 0,0000025 = 1,395 USD`; disco `1.240 × 3.600 × 0,00000007 = 0,31248 USD`. Subtotal ilustrativo `1,70748 USD`, excluindo CPU, Worker, DO, rede, impostos e outros consumos. Não é estimativa do ambiente nem gasto adicional autorizado. CPU provisionada não deve ser confundida com CPU efetivamente faturada por uso.

Não existem medições de RSS/p95 CPU/rede de produção ou Lightsail nesta entrega. Medição futura deve separar idle, texto, job, reconexão, áudio e número de clientes; medir bytes, segundos ativos, RSS e CPU e comparar à cota disponível da conta. Se custo incremental não puder ser limitado, adiar a nova funcionalidade e pedir decisão específica; não desligar o sistema atual.

## Fontes

- [C1] [Cloudflare limits](https://developers.cloudflare.com/containers/platform/limits/).
- [C2] [Cloudflare pricing](https://developers.cloudflare.com/containers/platform/pricing/).
- [C3] [Supabase pricing](https://supabase.com/pricing).
- [C4] [Supabase project pausing](https://supabase.com/docs/guides/platform/free-project-pausing).
- [C5] [GitHub included usage](https://docs.github.com/en/billing/reference/product-usage-included).
- [C6] [OpenRouter free models](https://openrouter.ai/collections/free-models), catálogo consultado, não evidência de endpoint aprovado do VISÃO.
- [C7] [NVIDIA API Trial Terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), seções 1.2–1.4.
- [C8] [Apple Web Push](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers).
- [C9] [Apple enrollment](https://developer.apple.com/help/account/membership/program-enrollment/).

Ver [arquitetura](phase10_multidevice_architecture.md), [avaliação](phase10_evaluation_plan.md) e [plano de implementação](phase10_implementation_plan.md) para dependências e autorizações. Nenhuma recomendação desta seção foi aplicada.

[C1]: https://developers.cloudflare.com/containers/platform/limits/
[C2]: https://developers.cloudflare.com/containers/platform/pricing/
[C3]: https://supabase.com/pricing
[C4]: https://supabase.com/docs/guides/platform/free-project-pausing
[C5]: https://docs.github.com/en/billing/reference/product-usage-included
[C6]: https://openrouter.ai/collections/free-models
[C7]: https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf
[C8]: https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
[C9]: https://developer.apple.com/help/account/membership/program-enrollment/

## Consolidação local — 01/11/2026

Os seis documentos foram reunidos em `docs/research/` e copiados para o pacote de entrega local. A auditoria original do estado atual foi preservada por conter evidências mais detalhadas; os outros cinco documentos vieram da tarefa em nuvem e passaram por revisão local de conteúdo, referências e escopo. HEAD permanece no SHA auditado. Os resultados de testes continuam sendo os da etapa local de 31/10/2026; não houve nova execução das suítes nem dos experimentos nesta consolidação. Nenhuma implementação, migração, commit, push ou publicação foi realizada.
