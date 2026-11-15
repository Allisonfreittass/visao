# ADR-0012: Painéis vivos no Início, recotados pelo worker

- Data: 2026-11-15
- Estado: aceita

## Contexto

Depois de uma cotação ao vivo, a Fase 1 oferece "deixar isso num painel no Início"
(`panel_offers`, [PAINEIS.md](../PAINEIS.md)), mas aprovar só escrevia uma página estática. O que
se quer é um card nativo no Início com o total, a distância da meta e os itens, que se confere
sozinho uma vez por dia e avisa quando algo relevante muda.

Já existem as peças para isso, sem precisar de sistemas paralelos:
- o navegador (`core/browse.py`, com o Chromium no container `browser`);
- a fila no banco e o worker (ADR-0007);
- o orçamento de autonomia e a pausa global (ADR-0009);
- o horário silencioso e o Web Push (`core/initiatives`);
- o razão do LLM (`integrations/llm/budget.py`).

## Decisão

### Modelo (migração `0029`, com RLS como as outras tabelas)

- **`panels`:** dono, conversa e projeto de origem (opcionais), a oferta que o criou, `kind`
  (por enquanto só `travel_quote`), `title`, `spec`, `snapshot`, `checked_at`, `next_check_at`,
  `status`, `version`, `check_note`, `last_alert_at`.
  - `status` pode ser `active`, `paused`, `error` ou `expired`.
  - `check_note` é o que o card diz quando não deu para conferir, por exemplo "o site pediu
    verificação de robô".
- **`panel_snapshots`:** o histórico de cada conferência (snapshot, total calculado, hora, as
  visitas que o sustentam), para mostrar a variação.
- **`panel_versions`:** cada edição pela conversa guarda a versão anterior do `spec` e do título,
  no mesmo espírito da adaptação versionada (ADR-0008).

### O `spec` e o `snapshot` são dados validados, não HTML

- **`spec`** (pydantic, `core/panels/model.py`): origem, destino, ida, volta, número de pessoas,
  preferências, bairro do hotel, moeda e `goal` (a meta).
  - A meta vem **das palavras do dono**, lida no código (`offers.goal_from`), nunca de um palpite
    do modelo.
- **`snapshot`:** a lista de itens (voo ou hospedagem). Cada item tem:
  - provedor, trecho ou endereço, datas e conexões;
  - preço, moeda e se o preço é por pessoa ou o total;
  - site, hora da leitura e o `visit_id` da página lida.

  O **total** e a **distância da meta** são calculados no servidor. Se faltar o preço de algum
  item, o total fica "a confirmar".

### Extração com saída estruturada (`core/panels/extract.py`)

- **Uma chamada curta** ao modelo, pelo `budget.py`, lê as páginas abertas e devolve JSON no
  esquema acima.
- **O código confere cada item:**
  - um item cujo `visit_id` não é de uma página lida agora é descartado;
  - um preço cujo número não aparece no texto daquela página é zerado, e o item fica "a
    confirmar".
- **Nunca há preço inventado.** Um campo que faltar fica vazio.
- **Testes:** contra páginas gravadas (`tests/fixtures/panels/`), sem rede.

### Criação e edição

- **Criar:** aprovar a oferta (toque, voz ou "pode") cria o painel com os mesmos dados da
  cotação. A página da Fase 1 deixa de ser criada.
  - **Criar o painel equivale a aprovar a recotação recorrente.** Isso fica na auditoria
    (`panel.create`, com `recurring_check: daily`).
  - O painel pode ser pausado ou apagado a qualquer momento (`PATCH`/`DELETE /panels/{id}`).
- **Editar:** um pedido sobre o painel na conversa ("melhora esse painel", "troca o hotel pra
  Providencia", "muda a meta pra R$ 5.500") edita o **mesmo** painel.
  - Uma chamada curta devolve só as mudanças do `spec`, validadas. A meta, de novo, vem das
    palavras.
  - A versão anterior é guardada, e uma mudança que afeta a busca agenda uma conferência agora.
  - A resposta confirma em uma ou duas bolhas o que mudou.

### Recotação diária no worker

- **A fila:** um job `panel_recheck` por painel, com `next_check_at` às 9h do horário local do
  dono no dia seguinte. A execução agenda a próxima (idempotente por dia).
- **Os endereços vêm do `spec`, em código** (os mesmos modelos de Google Voos e Hotéis do
  planejador), então não há chamada de planejamento. Há uma única chamada de extração, que conta
  como **autônoma**: o propósito `panel_extract` entra em `AUTONOMOUS_PURPOSES`, então respeita o
  teto diário de chamadas da autonomia e o teto em dólares.
- **Pausa global ou sem orçamento:** não confere. O card mostra a hora da última conferência e
  "não conferido hoje", e **nunca mostra um preço velho como atual**.
- **Limites** (`.env.example`):
  - `VISION_PANELS_MAX_ACTIVE` (padrão 3);
  - `VISION_PANEL_MAX_PAGES` (padrão 2 páginas por conferência);
  - `VISION_PANEL_ALERT_DROP_PERCENT` (padrão 10).

  O container `browser` continua com 700 MB, e as páginas abrem em série.
- **Verificação de robô:** o card mostra "não consegui conferir hoje" e tenta no dia seguinte.
  Nunca contorna.
- **Datas que já passaram:** o painel expira sozinho.
- **Avisos** (Web Push e, quando houver, push no iPhone), só quando:
  - o total caiu abaixo da meta;
  - o total caiu mais que X%;
  - ou um item sumiu.

  No máximo um aviso por painel por dia, e fora do horário silencioso (`deliver_after`).

### Rede do navegador

O worker passa a entrar na rede `browsing`, ao lado da API, para abrir as páginas da recotação. O
container `browser` continua sem segredos e sem banco: quem ganha acesso a ele é o worker, não o
contrário. Do lado do Chromium, o risco não muda.

### Início

- **Cards nativos** (React e SwiftUI, sem webview). Cada um mostra:
  - o título e o total em destaque;
  - a distância da meta ("R$ 555 acima da meta de R$ 6.000", ou abaixo, em verde);
  - os itens com preço, datas e conexões;
  - a hora da conferência e a variação desde a anterior.

  Tocar expande o histórico e os links dos sites.
- **Sem logos de terceiros:** usamos um monograma (a inicial do provedor), porque não há uma fonte
  de logos com licença clara.
- **Sugestões:** sem pendências nem painéis, aparecem até 3 sugestões tiradas das conversas e dos
  projetos recentes (títulos sobre viagem ou preço). Assuntos sensíveis ficam de fora, com o mesmo
  filtro da memória.

## Alternativas descartadas

- **Recotar com o planejador (LLM) toda vez:** custaria uma chamada a mais por dia e por painel
  só para refazer o mesmo endereço, que já é conhecido pelo `spec`.
- **Guardar o HTML ou o texto da página no painel:** o card precisa de números confiáveis e
  calculáveis, e o texto cru fica nas `browse_visits`, como já fica hoje.
- **Uma tabela de metas genérica para a recorrência:** a `goals` é para pesquisas com resultado
  final. O painel é ele mesmo o item aprovado e recorrente, com pausa e auditoria próprias.

## Consequências

- **Custo:** uma chamada de extração por painel ativo por dia, mais as páginas abertas. Detalhado
  no [COSTS.md](../COSTS.md).
- **O Início vira o lugar dos resultados vivos.** O chat continua o lugar de pedir.
- **Os modelos de URL do Google** estão no código. Se o Google mudar, a extração vira "a
  confirmar", e é preciso atualizar o modelo.
