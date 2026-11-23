# ADR-0022: Provedor por tarefa, escolhido por regra no código

- Data: 2026-11-23
- Estado: aceita

## Contexto

O Visão tem três provedores na nuvem: Claude (pago), OpenAI (pago) e Gemini (cota grátis). Até
aqui eles formavam uma corrente fixa, a mesma para todo propósito: a principal, depois
`FALLBACK`, depois `FALLBACK2` (`VISION_LLM_*`). Só se passava para o próximo quando um falhava
(429, cota, 5xx, rede). O dono pediu que o Visão decidisse sozinho qual usar em cada chamada,
para gastar menos no que ninguém espera.

Duas restrições:

- **Quem escolhe é o código** (ADR-0009). Nenhum modelo escolhe outro modelo. A regra é uma
  tabela, auditável e testada.
- **Privacidade.** No nível grátis, o que vai para o Gemini pode ser usado pelo Google para
  melhorar os produtos dele, inclusive com revisão humana. O `docs/PRIVACIDADE.md` diz que nada é
  usado para treinar modelos, e o uso limitado do Google proíbe isso para dados do Gmail. Ao
  conferir os propósitos, só um não leva nada do dono: o `study_review`. O `study_plan` leva o
  perfil e as memórias, e o `curiosity_assessment` leva memórias, contexto e a última mensagem.

Também entra aqui o item F8 do `docs/research/comparativo_agentes.md`. A pausa de um provedor sem
cota ficava na memória de cada processo e durava sempre 15 minutos, então a API e o worker
descobriam cada um por si.

## Decisão

- **Dois modos**, em Ajustes > Modelo > "Escolha do provedor" (`SystemFlag` `llm_routing`, com
  auditoria `llm.routing`):
  - **Ordem fixa** (padrão): a corrente configurada, como antes.
  - **Por tarefa**: os mesmos provedores, reordenados pelo propósito da chamada.
- **A regra** (`core/llm_routing.py`):

  | Classe | Propósitos | Ordem |
  |---|---|---|
  | público | `study_review` | Gemini, Claude, OpenAI |
  | pessoal | todo o resto, e toda chamada que não diz o propósito | Claude, OpenAI, Gemini |

  Pôr um propósito em `PUBLIC_PURPOSES` é uma decisão de privacidade: só entra o que leva
  apenas texto público.
- **O propósito chega à corrente** por uma `ContextVar` (`for_purpose`, igual a `drafting` e
  `compacting`). Hoje é marcado no `complete_json`, por onde passa o `study_review`. Uma chamada
  sem marca fica na ordem pessoal, que é a segura.
- **O provedor é reconhecido** pelo nome ou pelo endereço da API de cada vaga do `.env`. Um
  provedor que a regra não conhece (Groq, OpenRouter) fica depois dos conhecidos, na posição em
  que foi configurado. Só entra na ordem o que está configurado.
- **Nada mais muda em cada passo.** O fallback continua só em falha, cada provedor pago passa
  pelo `BudgetGuard` (`llm_paid_daily_usd` e `llm_paid_monthly_usd`), o `FittingProvider` também
  se mantém, e o trabalho autônomo continua no `has_room` (`VISION_LLM_DAILY_BUDGET_USD`). Quando
  o Gemini fica sem cota, a revisão do estudo cai no Claude dentro desses tetos.
- **A pausa por cota fica no banco** (`integrations/llm/pause.py`, `SystemFlag`
  `llm_pause_v1`). A API e o worker veem a mesma pausa, que dura até o reset informado pelo
  provedor: `x-ratelimit-reset`, o `retryDelay` do Gemini ou meia-noite do Pacífico quando o
  Gemini diz que a cota diária acabou. Sem essa informação, valem os 15 minutos de antes. A
  pausa fica entre 1 minuto e 24 horas. Se o banco não responder, vale a pausa na memória do
  processo, e a ordem configurada.
- **Uma chave nova recomeça limpa.** O circuito do razão (3 falhas, 15 minutos) e a pausa por
  cota passam a ser da chave em uso: entra na identidade um hash dela
  (`credential_fingerprint`, 16 caracteres, nunca a chave). Caso real de 23/11/2026: uma chave
  colada errada abriu o circuito da OpenAI, e a chave certa esperou 15 minutos à toa.
- **Também conta como cota esgotada** um 429 `insufficient_quota` da OpenAI (conta sem crédito).
- **Não confundir com o `brain`** (`core/brain.py`). O "auto" do brain põe o modelo local do Mac
  atrás da nuvem. Este ajuste só ordena os provedores da nuvem, e os dois combinam.

## Fora desta decisão

- Mandar ao Gemini grátis qualquer coisa que leve dado do dono. Para isso seria preciso o nível
  pago do Gemini, que não treina, ou uma decisão nova do dono, com o `PRIVACIDADE.md`
  atualizado.
- Escolher pela dificuldade da mensagem. Só o propósito decide, e o propósito vem do código.
- Mudar a ordem pela conversa ("usa o Gemini"). Por enquanto, só em Ajustes.
