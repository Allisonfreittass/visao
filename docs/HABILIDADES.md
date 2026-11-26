# Habilidades

Uma habilidade é um jeito de trabalhar que o Visão segue quando o pedido combina com ela: achar a
causa de um bug, escrever um documento por etapas, transformar uma ideia em plano. Fica na tela
**Habilidades**, onde o dono liga e desliga cada uma.

## O que é e o que não é

- **É só texto.** Cada habilidade é um arquivo `core/skills/library/<id>/SKILL.md`, escrito em
  português e guardado no código.
- **Nada roda.** Não há script nem dependência nas habilidades, e nada é baixado enquanto o Visão
  funciona. É a linha de [comparativo_agentes.md](research/comparativo_agentes.md) §3: nada de
  loja de plugins que rodam código.
- **Não muda as regras.** O texto da habilidade entra no contexto da resposta abaixo das regras de
  verdade, da voz e das aprovações. Uma habilidade não libera ação nenhuma: o que roda no Mac
  continua passando pelo Braço com a aprovação do dono.

## Como uma habilidade entra na resposta

1. O código, não o modelo, compara a mensagem com os `triggers` de cada habilidade ligada
   (frases inteiras, sem acento e sem diferença de maiúsculas). Ganha a que acerta mais frases;
   no empate, a de frases mais longas ("design doc" ganha de "design").
2. Se a mensagem não acerta nenhuma, valem as três últimas mensagens do dono na mesma conversa,
   das duas últimas horas. Assim um documento escrito seção por seção não perde a habilidade
   quando o dono responde "1: sim, 3: não".
3. Entra no máximo uma por resposta, até 7.000 caracteres, no contexto opcional (o modo compacto
   a corta primeiro: [MODO_COMPACTO.md](MODO_COMPACTO.md)).
4. O passo "Seguindo a habilidade …" aparece no chat, e a decisão do turno registra
   `skill_used` com o id.

O manifesto de capacidades (`core/identity/capabilities.py`) lista os nomes das que estão ligadas,
para ele saber dizer o que sabe fazer.

## No Braço

As habilidades com `arm: sim` no cabeçalho também vão para as tarefas de código no Mac, com os
dois executores: Achar a causa de um bug, Design de telas e Revisar código.

- **Executor do Visão** ([ADR-0023](decisions/0023-executor-de-codigo-proprio.md),
  `core/arm/coder.py`): a habilidade entra no prompt de cada passo, montado no servidor.
- **Claude Code:** o servidor manda a habilidade junto com a tarefa (`skill` em
  `GET /arm/device/next`, só nas tarefas de trabalho), e o braço a acrescenta, até 8.000
  caracteres, ao texto que já passava em `--append-system-prompt`. Vai como um único valor, nunca
  como flag, e não muda o que pode rodar: as permissões e o sandbox continuam os mesmos. Precisa
  do braço 7 no Mac; um braço mais velho ignora o campo e roda sem a habilidade.

- A escolha usa os mesmos gatilhos, só sobre a tarefa que o dono aprovou, e é a mesma em todos os
  passos da tarefa. Entra no máximo uma, e só se estiver ligada.
- O texto vai no fim do prompt de sistema, depois das regras do braço, com um aviso: ele já está
  no Mac, numa tarefa aprovada; onde a habilidade fala em perguntar ao dono, ele usa as
  ferramentas que tem e deixa no resumo do `terminar` o que só o dono decide.
- As que pedem conversa (Escrever documentos, Comunicados, Ideias) ou o e-mail e a agenda não vão:
  no meio de uma tarefa o braço não pergunta nada. "Ideias" ainda travaria a tarefa já aprovada
  esperando a aprovação de um desenho.
- Não vale para mouse e teclado ([MEXER.md](MEXER.md)) nem para desfazer uma tarefa.

## Ligar e desligar

- `GET /skills`: cada habilidade com `id`, `name`, `description`, `origin` (`instalada`), `source`,
  `source_url`, `license`, `installed_on` e `enabled`.
- `PUT /skills/{id}` com `{"enabled": true|false}`. Fica guardado no `SystemFlag` `skills`
  (`{"off": [ids]}`), sem tabela nova, e cada troca vai para o registro de auditoria
  (`skill.toggle`).
- Toda habilidade instalada começa ligada.

## As instaladas

| Habilidade | De onde veio | Licença |
|---|---|---|
| Achar a causa de um bug (`achar-bugs`) | `obra/superpowers`, systematic-debugging | MIT |
| Comunicados e relatórios de status (`comunicados`) | `anthropics/skills`, internal-comms | Apache-2.0 |
| Design de telas (`design-de-telas`) | `anthropics/skills`, frontend-design | Apache-2.0 |
| Escrever documentos junto (`escrever-documentos`) | `anthropics/skills`, doc-coauthoring | Apache-2.0 |
| Transformar ideia em plano (`ideias`) | `obra/superpowers`, brainstorming | MIT |
| Triagem do e-mail (`triagem-email`) | `anthropics/knowledge-work-plugins`, inbox-manager | Apache-2.0 |
| Preparar uma reunião (`preparar-reuniao`) | `anthropics/knowledge-work-plugins`, meeting-briefing | Apache-2.0 |
| Resumir uma reunião (`resumo-reuniao`) | `anthropics/knowledge-work-plugins`, call-summary | Apache-2.0 |
| Pesquisa a fundo (`pesquisa-a-fundo`) | `anthropics/knowledge-work-plugins`, knowledge-synthesis | Apache-2.0 |
| Ler um contrato antes de assinar (`ler-contrato`) | `anthropics/knowledge-work-plugins`, contract-review | Apache-2.0 |
| Revisar código (`revisar-codigo`) | `anthropics/knowledge-work-plugins`, code-review | Apache-2.0 |
| Fechar e planejar a semana (`revisao-semana`) | `anthropics/knowledge-work-plugins`, weekly-wrap | Apache-2.0 |

O dono escolheu as cinco primeiras em 25/11/2026. As sete do `knowledge-work-plugins` vieram no
mesmo dia, quando ele pediu as melhores para ter "um Jarvis": a coleção da Anthropic para trabalho
do dia a dia (Apache-2.0, a maior e mais mantida que achamos). Foram tiradas do contexto de
empresa, vendas e CRM e reescritas para o que o Visão tem: o Gmail e a Agenda que ele lê, os
rascunhos que só saem com o Aprovar, o GitHub no servidor, o Mac, os painéis e as páginas. Cada uma aponta, no `source_url`, para o commit exato
que foi lido. As licenças estão em `core/skills/library/LICENSE-*`.

Ficaram de fora:

- **pdf, xlsx, docx, pptx, webapp-testing, skill-creator:** dependem de rodar scripts.
- **discernment-nudge:** termina as respostas com perguntas, contra a regra de voz.
- **As de marca e arte da Anthropic e a claude-api:** não servem ao uso do dono.
- **task-management e memory-management (knowledge-work-plugins):** dependem de arquivos
  (`TASKS.md`, `CLAUDE.md`) que o Visão não tem; as anotações dos projetos e a memória já fazem
  esse papel.
- **As de vendas, CRM, finanças de empresa, RH e as do Zoom:** são de empresa, não de uma pessoa.
- **ComposioHQ/awesome-claude-skills:** a lista mais popular, mas o repositório não declara
  licença, então nada dele pode ser copiado nem adaptado.

## Instalar uma nova

1. Leia a habilidade inteira, no commit exato, e descarte as que dependem de rodar código.
2. Traduza e adapte ao chat: sem arquivos, sem subagentes, sem ferramentas que o Visão não tem.
3. Crie `core/skills/library/<id>/SKILL.md` com o cabeçalho `name`, `description`, `triggers`,
   `source`, `source_url` (com o commit), `license` e `installed_on`, e um corpo que começa com
   "Adaptada da habilidade …".
4. Prefira gatilhos de várias palavras: "não faço ideia" não pode chamar a de ideias.
5. Atualize `APPROVED` em `tests/unit/test_skills.py`, junte um caso de mensagem que chama a
   habilidade e outro que não chama, e registre em [NOVIDADES.md](NOVIDADES.md).

## Ainda não

- **Habilidades que ele propõe** ("Já conferi preços 9 vezes do mesmo jeito. Guardo como
  habilidade?"), com aprovar e recusar: issue #9.
