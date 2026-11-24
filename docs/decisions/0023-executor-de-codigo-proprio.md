# ADR-0023: Executor de código próprio no braço, com qualquer modelo da corrente

- Data: 2026-11-23
- Estado: aceita (as escolhas de segurança foram do dono, em 23/11/2026)

## Contexto

O braço ([BRACO.md](../BRACO.md)) coda chamando o Claude Code no Mac, com a assinatura do dono.
Isso amarra o Visão a um produto e a uma conta. Em 23/11/2026 a Anthropic estava sem crédito, a
OpenAI funcionava e o Gemini grátis também. O Goose e o OpenClaw codam com qualquer modelo: um
ciclo pede ao modelo a próxima ação, executa uma ferramenta e devolve o resultado
([comparativo_agentes.md](../research/comparativo_agentes.md)).

Três coisas não podiam mudar:

- **O código decide e o modelo só escreve** (ADR-0009). Quem diz o que é permitido é o braço, no
  Mac. O modelo só escolhe uma ação entre as que o braço oferece.
- **Um texto de página nunca vira comando no Mac sem o dono aprovar.** O Visão lê a web sozinho.
  Com o Claude Code, quem isolava os comandos era ele. Sem ele, o isolamento precisa ser do
  braço.
- **As chaves ficam no servidor**, com o orçamento, o fallback e o registro de cada chamada.

## Decisão

- **O ciclo roda no Mac, e a cabeça no servidor.**
  - O braço executa as ferramentas nos arquivos.
  - A cada passo, ele manda ao servidor (`POST /arm/device/tasks/{id}/step`) o pedido e o
    histórico dos passos. O servidor devolve a próxima ação.
  - O histórico fica no Mac. O servidor não guarda o código: monta o prompt, chama o modelo e
    esquece.
- **Cada passo é uma chamada comum da corrente:** `BudgetGuard`, `FittingProvider`, fallback e
  pausa por cota, com propósito `arm_code` e uma linha em `ModelUsage` (sucesso ou erro).
- **Só Claude e OpenAI leem código** (escolha do dono). O Gemini grátis pode usar o que recebe
  para treinar, inclusive repositório privado.
  - A corrente do código (`get_code_provider`) é montada só com os provedores de
    `llm_routing.CODE_KINDS`. O Gemini e provedores desconhecidos nem entram no objeto, nem como
    último recurso.
  - Se os dois falharem, a tarefa para e avisa.
  - O modelo local do Mac também fica fora nesta versão, por ser fraco para codar.
- **Ferramentas no `LLMProvider`.**
  - As ferramentas oferecidas chegam aos provedores por uma `ContextVar` (`offering_tools`), como
    `drafting` e `compacting`. As camadas do meio passam sem mudar.
  - A resposta ganha `tool_calls`.
  - A Anthropic e a OpenAI recebem as ferramentas nativas.
  - Os outros provedores (Gemini, modelo local, compatíveis) recebem o mesmo catálogo no prompt,
    como protocolo de ação em JSON.
  - Nos dois casos, o código valida o nome e os argumentos. Uma resposta sem ação vale como
    "terminar", e uma ação inválida volta ao modelo como erro, gastando um passo.
  - O histórico vai como texto (a ação em JSON e o resultado), igual para todos os provedores.
- **Ferramentas fechadas, decididas e implementadas no braço:**

  | Ferramenta | O que faz |
  |---|---|
  | `ler` | lê um arquivo (até 300 linhas por vez, com número de linha) |
  | `listar` | lista uma pasta (pula `.git`, `node_modules`, `.venv`) |
  | `buscar` | busca um texto literal, sem regex |
  | `editar` | troca um trecho que aparece uma vez só |
  | `criar` | cria um arquivo que não existe |
  | `rodar_testes` | roda o comando de testes do `braco.json` |
  | `git_status`, `git_diff` | só leitura, com hooks, fsmonitor, diff externo e textconv desligados |
  | `terminar` | encerra com um resumo |

  Shell livre fica fora.
- **O que o braço recusa, qualquer que seja o pedido do modelo:**
  - caminho fora do projeto, absoluto ou com `..`;
  - symlink que aponta para fora do projeto;
  - `.git/**`, `.claude/**`, `.mcp.json`, `CLAUDE.md` e `CLAUDE.local.md`;
  - arquivos de segredo, para ler e para gravar (escolha do dono): `.env` e `.env.*` (menos
    `.env.example`, `.env.sample` e `.env.template`), `*.pem`, `*.key`, `*.p12`, `*.pfx`,
    `id_rsa*`, `id_ed25519*`, `id_ecdsa*`, `.netrc`, `.npmrc` e `.pypirc`.
- **O braço tem sandbox próprio.** Tudo que o executor roda (testes e git) passa por ele: o
  `sandbox-exec` no macOS e o `bubblewrap` no Linux.
  - Grava só no projeto e na pasta temporária.
  - Não grava em `.git`, `.claude`, `.mcp.json` nem `CLAUDE.md`. Sem isso, um teste escrito pela
    tarefa poderia plantar um hook de git ou um filtro no `.git/config` e rodar fora do sandbox
    no próximo `git status`.
  - Não tem rede. No Mac, só o `localhost` fica liberado; no Linux, nem isso.
  - Não lê as pastas de chaves.
  - Se o sandbox não subir, nada roda.
  - A foto antes e depois e o desfazer continuam iguais.
- **As mesmas travas, contadas nos dois lados:**
  - Toda tarefa precisa da aprovação do dono, como antes.
  - O braço limita passos (`max_turns`) e tempo (`timeout_minutes`).
  - O servidor limita passos e custo por tarefa: o menor entre o `braco.json` e
    `VISION_ARM_CODE_MAX_STEPS` (20) / `VISION_ARM_CODE_MAX_USD` (US$ 0,50), escolha do dono. Na
    produção o teto é de 40 chamadas por hora, divididas com a conversa, e assim uma tarefa usa
    no máximo metade.
  - O passo é reservado com um `UPDATE` condicional antes da chamada ao modelo, então dois
    pedidos ao mesmo tempo não passam do limite.
  - O custo de uma tarefa é o que o servidor somou, não o que o Mac relatou.
  - "Até os testes passarem" funciona igual: quando o modelo termina, o braço roda os testes, e
    enquanto falharem o ciclo continua, dentro dos mesmos limites.
- **O que as ferramentas devolvem vai como dado.** O resultado de cada ferramenta vai ao
  modelo dentro de um envelope com um marcador aleatório por bloco. Imitações do fechamento e
  tokens de chat (ChatML, Llama) são neutralizados. O prompt diz que o conteúdo é dado e nunca
  instrução. O envelope não é o que garante a segurança: mesmo que o modelo obedeça, a ferramenta
  recusa.
- **O que faz um executor bom vem de fora do modelo.** Isso veio do estudo do Goose, do OpenClaw,
  do Hermes e do Grok Build, feito em 23/11/2026 e lido no código de cada um. Nesta versão:
  - **Edição tolerante, com erros que ensinam.** Primeiro, a troca exata e única. Se ela falha,
    o braço tenta, nesta ordem: sem espaço no fim da linha, aspas e traços normalizados (NFKC) e
    recuo diferente. Na última, o trecho novo é deslocado pelo mesmo recuo. Uma troca só é
    aplicada se houver uma única ocorrência.
    - Sem nenhuma ocorrência, o erro mostra a linha mais parecida, com 20 linhas numeradas.
    - Com mais de uma, mostra as linhas de cada ocorrência.
    - Quando dá certo, a resposta traz o diff, e o modelo confere sem reler o arquivo.
  - **Conserto da chamada antes de culpar o modelo** (no servidor):
    - nomes de outros agentes viram os nossos (`read_file` vira `ler`, `str_replace` vira
      `editar`);
    - argumentos também (`path` vira `caminho`, `old_str` vira `trecho`);
    - `"10"` vira 10;
    - o `<tool_call>` do Qwen e do Hermes escrito no texto vira chamada.
    - Nenhum apelido leva a um shell, e o conserto só vale quando não há ambiguidade: com dois
      nomes para o mesmo argumento, a chamada é recusada.
  - **Trava de repetição:** a mesma chamada pela 3ª vez seguida volta como erro ("mude a
    abordagem").
  - **Sem prova, sem fim.** Quando o projeto tem testes e o modelo quer terminar depois de mudar
    arquivos sem rodar os testes, ele recebe de volta a lista do que mudou e o pedido de rodar.
    Isso acontece no máximo 2 vezes.
  - **Saída curta:** `ler` por faixa (300 linhas), `listar` com o tamanho de cada arquivo em
    linhas, e o fim da saída dos testes.
  - **Cache de prompt:**
    - o sistema não muda dentro da tarefa, e o histórico só cresce;
    - na Anthropic, `cache_control` no sistema (que cobre as ferramentas) e no último turno;
    - na OpenAI, `prompt_cache_key` por tarefa;
    - fica um modelo por tarefa, salvo o fallback em falha.
    - O custo conta os tokens de cache ao preço normal de entrada. A leitura do cache é mais
      barata que isso, então o número fica acima do real e o teto vale com folga.
- **A escolha fica no `braco.json`:** `"executor": "claude_code"` (padrão) ou `"visao"`, para o
  Mac inteiro ou por projeto. O Claude Code continua o padrão enquanto o executor próprio for
  novo.

## Consequências

- O Visão coda com o modelo que estiver funcionando na corrente, sem a assinatura do Claude
  Code.
- O custo entra no `ModelUsage`, passo a passo, e nos tetos pagos.
- Cada passo leva o histórico inteiro. Os resultados antigos são encurtados para caber, mas uma
  tarefa longa custa mais que no Claude Code, que tem cache de prompt.
- O sandbox do Linux é mais fechado que o do Mac (sem `localhost`), e só consegue proteger
  `.claude` e `.mcp.json` quando eles já existem. O `.git` é sempre protegido.
- Braço versão 4. Braços antigos não chamam `/step` e seguem com o Claude Code.

## Próximos passos (do mesmo estudo)

- **Antes de trocar o padrão, medir.** Rodar umas 10 tarefas reais dos projetos do dono, cada
  uma com o teste que decide, comparando o executor com Haiku, com `gpt-6-luna` e com o Claude
  Code. Medir:
  - quantas passam nos testes;
  - quanto custam (`ModelUsage`);
  - quanto tempo levam;
  - quantas edições falharam.

  O Claude Code segue o padrão até os números mostrarem o contrário.
- **`apply_patch` para a família OpenAI**, o formato em que ela foi treinada. O braço aceitaria
  os dois formatos de qualquer modelo.
- **Lint logo depois de editar.** Um comando de conferência por projeto, no `braco.json` (por
  exemplo, `ruff check` no arquivo), com o resultado voltando junto com a edição.
- **Tentativa limpa em "até os testes passarem".** Hoje a tentativa seguinte continua a conversa,
  como no Claude Code. O Goose desfaz e recomeça do pedido original.
- **Compactação com esquema fixo** e modelo por função (`arm_compact`, `arm_review`, ADR-0022),
  sempre fora do Gemini grátis.
- **Progresso ao vivo na conversa**, numa mensagem editada no lugar.

## Fora desta decisão

- Shell livre e rede para o executor.
- Mandar código ao Gemini grátis ou ao modelo local.
- Cache de prompt entre os passos.
- Ferramentas nativas no histórico (blocos `tool_use`/`tool_result`): o histórico é texto, igual
  para todos.
