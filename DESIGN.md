# DESIGN.md — Visão

Fonte única do visual do Visão. Todo agente (Claude Code, Codex, Cursor) e toda pessoa que mexer
em interface lê este arquivo antes. Se uma tela nova não couber nestas regras, a regra muda aqui
primeiro, depois o código.

> **Identidade nova (24/11/2026), com o ícone trocado em 25/11/2026: o corvo de olho âmbar.** O
> corvo no eclipse, o busto diante de um sol âmbar, durou um dia e saiu. O mockup em
> [`docs/design/telas-visao/`](docs/design/telas-visao/README.md) é a referência de pixel; o app web
> está migrando por etapas (seção 8, "Telas do VISAO"). Onde este arquivo e o mockup discordarem, vale
> o mockup e este arquivo é corrigido. O que está marcado **sai** continua no código até a etapa
> que o substitui.
>
> **Estado anterior:** direção aprovada em 23/11/2026 ("Muninn"). No app web, os passos 1 a 5 da
> [Migração](#migração) estão feitos: tokens e fontes em todo o app, o `<Anel>` no lugar do
> Ciclope, os sensores como ícones de traço, o login no Muninn e os textos na voz da seção 7.
> Os ícones e imagens (passo 6) saíam do anel; hoje saem do corvo (seção 5). Falta o iPhone
> inteiro (`Theme.swift`, `LoginView`). Telas novas já seguem este arquivo.

## 1. Ideia

O Visão nasce sem nome (`chosen_name = null`) e o modelo só existe durante uma chamada. O que o faz
continuar mora em volta: memória que a pessoa autoriza, interesses, versões reversíveis.

- **Muninn** é a forma que ele usa agora: o corvo da memória de Odin, que voa pelo mundo e volta
  para contar o que viu. É o que o Visão faz: pensa entre conversas, estuda e abre o papo.
- **O corvo de olho âmbar** é o ícone: o corvo em close, preto sobre papel, com o olho âmbar. É o
  ícone do app, o logo da barra lateral, o avatar das mensagens dele e a imagem grande da ligação.
- **O corvo com sol saiu** (25/11/2026): o busto diante de um sol âmbar, sobre tinta, foi o ícone
  por um dia. Não volta em tela, ícone nem texto.
- **O selo** é o campo âmbar com "VISAO" em Six Caps preenchendo o quadrado atrás do busto. Só no
  login e em material de marca; não mudou com o ícone.
- **O anel de rastros** (**sai**): 24 marcas radiais, uma por hora, com a falha do nome no topo.
  Era a marca da direção "Muninn"; o corvo toma o lugar dele em cada tela.
- **Não é vigia.** Nada de câmera, "vigilância", "dê uma ordem". O olho âmbar é o do corvo, parte
  do desenho: não encara a pessoa. Quem supervisiona é a pessoa.

## 2. Cor

Uma luz só. Âmbar `#E39A2E` é dele; nada mais é colorido.

Três temas, trocados na hora em Ajustes › Aparência e guardados no aparelho. Papel é o padrão.
Os valores vivem em `apps/web/src/brand/tokens.css` (`data-theme` no `<html>`):

| Token | Papel (claro) | Tinta (escuro) | Rótulo (creme e azul) | Uso |
|---|---|---|---|---|
| `--bg` | `#F6F4EF` | `#101214` | `#F3E9D2` | Fundo da janela |
| `--surface` | `#FFFFFF` | `#1A1D20` | `#FBF5E6` | Barra lateral, rodapé, cartões, compositor |
| `--surface-2` (`--chip`) | `#EEEAE1` | `#24282C` | `#EADCBB` | Item ativo, chips, balão do código inline |
| `--border` | `#E3DFD6` | `#2C3136` | `#D9C9A3` | Bordas de 1 px, divisórias |
| `--text` | `#101214` | `#F3F1EC` | `#1D2B4F` | Texto; fundo do botão principal |
| `--text-muted` | `#5B6066` | `#9AA1A8` | `#56607C` | Texto secundário, dados |
| `--code` / `--code-text` | `#101214` / `#F3F1EC` | `#0B0C0E` / `#F3F1EC` | `#1D2B4F` / `#F3E9D2` | Bloco de código |

O cinza do Rótulo é um tom mais escuro que o do mockup (`#5A6480`) para passar de 4,5:1 sobre
`--surface-2`. Todo o texto passa de AA nos três temas; a borda de campo (`--border-strong`) passa
de 3:1.

Regras:

- Botão principal é **a cor do texto com o fundo por cima** (tinta sobre papel no Papel). O
  secundário é contorno. Nunca vermelho, nunca âmbar sólido em "Aprovar": aprovar é calmo.
- Âmbar é só dele: o olho do corvo, o filete dos pensamentos, o pedido de aprovação, o ponto de
  atividade pulsando e o aviso de versão. Nunca em botões comuns, nunca de fundo (fora o selo), nunca em texto
  da interface. Nos temas claros o âmbar tem pouco contraste (cerca de 2:1): é ponto, borda e
  desenho, nunca a única pista de algo.
- A gênese conta como presença: o ponto do peito, as faíscas e o lampejo da falha são dele.
- Sem degradê em botão, cartão ou fundo. O único degradê permitido é o da revelação do Muninn
  (papel → cinza, de cima para baixo).
- Verde `#2E9E5B` só no ponto de "conectado" e de "servidor ok". Erro usa texto, não cor de fundo.
- O login e a abertura ficam em Tinta até a tela nova do login (etapa 4); a ligação é sempre tinta.

## 3. Tipografia

| Papel | Fonte | Onde |
|---|---|---|
| Voz dele | **Newsreader** 300, itálico para falas; 400 em números grandes | Saudações, títulos, o que ele pensa, o nome quando existir |
| Interface | **Geist** 400/500/600 | Texto corrido, botões, rótulos |
| Dados | **Geist Mono** 400/500, 11–13 px | Datas, horários, status, metadados, código, a barra de status |
| Marca | **Six Caps** | Só o nome `VISAO` (logo da barra lateral e selo) |

- Todas servidas pelo próprio app (`apps/web/public/fonts/`), sem Google Fonts.
- O nome `VISAO` é Six Caps (token `--font-marca`). O antigo codinome `VISÃO` em Geist Mono
  caixa-alta **sai**. O nome do agente, quando vier, é Newsreader itálico.
- Fala dele em bloco: Newsreader itálico com filete âmbar de 2 px à esquerda.
- Não usar Inter, Space Grotesk ou JetBrains Mono em telas novas.

## 4. Forma e layout

- Raios: 12 (campos), 16–18 (blocos), 999 (botões e chips). Sem sombra; a borda de 1 px separa.
- Toque mínimo de 44 px em tudo que é clicável.
- **Não aninhar cartões.** Um bloco com borda nunca fica dentro de outro bloco com borda.
- Sem ícone decorativo em cima de título. Ícones só em navegação e botões, traço 1.5 px.
- Computador, a janela: barra lateral de 248 px (`--surface`, borda à direita) | área principal com
  a barra da página de 52 px em cima (título do lugar ou da conversa, ações à direita) e o conteúdo
  embaixo | barra de status de 28 px no rodapé, de ponta a ponta, em Geist Mono 11 px.
- Barra lateral: logo, Nova conversa e lupa, navegação (Início, Chat, Projetos, Caderno, Rotinas,
  Mac, Agentes, Canais, Habilidades), conversas Fixadas e Recentes, cartão de versão nova, você e
  Ajustes. Abaixo de 900 px ela vira gaveta, e a barra da página e o rodapé somem.
- Ícones: os traços do mockup, grade de 20, em `apps/web/src/components/Icon.tsx`.
- Composer: pílula `--grafite` com microfone, campo "Fala comigo…", anexar e enviar (papel).

## 5. O corvo de olho âmbar e o Muninn

O ícone tem dois desenhos em vetor, em `brand/simbolo/`, e nenhum é redesenhado à mão:

- `corvo-olho-pequeno.svg`, o corte fechado na cabeça (só o olho e o bico), de 16 a 48 px;
- `corvo-olho-icone.svg`, o corvo inteiro em close, de 64 px para cima.

Os dois trazem o próprio fundo de papel (`#F3F1EC`) e os cantos arredondados (22,5% do lado).

- **No app:** `<Corvo size>` (`apps/web/src/brand/Corvo.tsx`) escolhe o desenho pelo tamanho
  (pequeno até 48 px) e lê os SVGs de `apps/web/public/marca/`.
  - Nos temas claros leva um contorno de 1 px em tinta (`box-shadow: 0 0 0 1px
    rgba(16,18,20,0.12)`), para o papel do desenho não sumir no papel da página.
  - No Tinta e na ligação não leva contorno.
  - É decorativo ao lado do nome dele. Sozinho, o texto alternativo é "O corvo do VISAO, de olho
    âmbar".
- **Ícones:** `brand/generate_assets.py` gera, direto do vetor (como rodar em
  [`brand/README.md`](brand/README.md)):
  - o favicon (16, 32 e `.ico`);
  - o `apple-touch-icon` (180);
  - os ícones do PWA (192 e 512);
  - o `maskable-512` (o desenho a 84%, no canto de baixo à esquerda, para a cabeça e o bico caberem
    no círculo seguro do Android);
  - os ícones do app de Mac, com o desenho pequeno em 16 e 32 pt (também nos pixels 2x da
    tela Retina) e o inteiro de 128 pt para cima;
  - o ícone do iPhone (1024, de ponta a ponta: o iOS arredonda), nas três aparências. O escuro é o
    mesmo corvo sobre papel, como nas páginas escuras do app; o tingido é o desenho em cinza, que o
    iOS colore pelo brilho (o papel pega a cor, o corvo fica escuro).
- **A imagem de compartilhamento** (`og-image.png`, 1200 × 630), do mesmo gerador: o corvo sobre
  papel saindo pela esquerda e por baixo, VISAO em Six Caps, "Nasce sem nome." e a fala dele em
  itálico, com o filete âmbar.

A gênese do Muninn (abaixo) continua sendo a animação do login até a etapa 4 decidir o que fica.

Arquivos em `brand/muninn/`:

- `muninn-lineart.png`: ilustração mestre (traço branco sobre preto, 1254 px).
- `trace.py` → `strokes.json`: 1.965 traços extraídos dela (esqueleto de 1 px, simplificado), em
  coordenadas de 0 a 1000, já escalados para caber no anel e ordenados do peito para fora.

Uso estático: a ilustração a 76% do tamanho do anel, centralizada (+1,4% no eixo y), com
`mix-blend-mode: screen` e o olho em âmbar em (51,6%; 35,7%).

No app web, a ilustração sai de `apps/web/public/muninn/` em dois tamanhos, gerados da mestre:
`muninn-720.webp` e `muninn-1024.webp`. O canvas usa a de 1024 quando a ilustração passa de
720 px de tela (tamanho × `devicePixelRatio` × 0,76), e a de 720 nos outros casos. Cada uma tem
um `.json` ao lado dizendo de onde veio. `strokes.json` fica na mesma pasta.

Tamanhos (direção anterior, **sai** com o anel): acima de 120 px, Muninn + anel. Entre 32 e 120 px,
só o anel. Abaixo de 32 px, anel sem as marcas apagadas.

Onde ele aparece no app web hoje:

| Tela | Forma | Tamanho |
|---|---|---|
| Entrada (login) | o selo | até 560 px |
| Abertura depois do login e a do dia | Muninn + anel, gênese curta (1,8 s) | 180 px; 132 px no celular |
| Carregando, antes do app abrir | o anel, com os estados da seção 6 | 200 px |
| Primeira vez | o corvo | 260 px; 120 px no celular |
| Início, no topo | o corvo (no celular não aparece: o corvo já está na barra de cima) | 92 px |
| Pedido de aprovação | o corvo pequeno | 20 px |
| Ligação | entre os turnos, o corvo grande; durante um passo, Muninn + anel com os nanorrobôs (seção 6) | até 380 px |
| Avatar das respostas no chat | o corvo pequeno | 30 px |
| Logo do menu lateral e da barra do celular | o corvo pequeno + VISAO | 30 e 26 px |

Sensores (Mac, e-mail, Caderno, projetos) são ícones de traço, nunca o corvo.

### Muninn em ASCII

Para o terminal e o README: `brand/muninn/muninn_ascii.py` (só biblioteca padrão) toca a gênese
em caracteres, 120 × 60, rampa ` .:-=+*#%@`, papel com âmbar no olho, no ponto inicial e no
`null`. Roda no `make start` e quando o Braço é iniciado à mão num terminal; sem terminal, com
`NO_COLOR` ou `VISAO_NO_ANIM=1`, mostra só o quadro final ou nada. `ascii_build.py --gif` refaz o
JSON e o `muninn-ascii.gif` a partir da ilustração.

## 6. Movimento

A animação é onde o Visão se diferencia. Regras (base: skills `emil-design-eng`, `choreograph`):

- **Gênese** (login, primeira abertura, quando ele "acorda"), 14 s, não em loop dentro do app:
  1. 0 s: o ponto âmbar acende no peito.
  2. 0,4–6,4 s: os traços de `strokes.json` nascem em ordem, 0,55 s cada, `ease-out` cúbico,
     soltando faíscas (7% de chance por ponta; 15% delas âmbar).
  3. 6,2–8,4 s: a ilustração aparece por cima, tingida de papel → cinza; o olho acende.
  4. 8,4 s: o anel se fecha, marca a marca (50 ms entre elas); a falha do topo pisca em âmbar.
- **Gênese curta** (abertura depois do login e a do dia, `T_CURTA`), 1,8 s, a mesma história: o
  ponto no peito, os traços até 0,85 s, a ilustração e o olho em 1,0 s, o anel fechado em 1,43 s
  e um piscar da falha; aos 1,5 s o nome é digitado ao lado.
- Entradas usam `ease-out`; nada de `ease-in` em elemento que entra.
- Estados do anel no app: ocioso (hora local acesa), ouvindo (marcas em onda), pensando (um
  rastro percorre o anel em 1,6 s por volta: a marca da frente em âmbar, a cauda apagando em
  papel → cinza), fala primeiro (ponto sobe à falha), pede aprovação (falha acesa), pausado
  (ponto vazado), silêncio (tudo apagado).
- No app web os estados moram em `<Anel estado=…>` (`apps/web/src/anel/`), em SVG com CSS (uma
  linha de avatares não roda script; só a voz usa um `requestAnimationFrame`). O que liga cada um:
  - silêncio: sem conexão com o servidor;
  - ouvindo: em ligação, logo depois de ser interrompido, ou com a voz dele tocando; a onda
    segue o volume da voz (a do dono ou a dele);
  - pensando: escrevendo a resposta, ou uma tarefa rodando no Mac;
  - fala primeiro: só uma conversa que ele abriu e o dono ainda não leu;
  - pede aprovação: algo preparado esperando sim (Mac, e-mail, agenda, painel);
  - pausado: autonomia pausada em Ajustes; o anel muda no toque do botão, e a checagem de 15 s
    só confirma.
  Sem conexão vence tudo. O que acontece agora vence o que espera; parado, a ordem é Mac,
  aprovação, pausa, abertura.
  Em volta do Muninn o olho fica no lugar e um segundo ponto sobe à falha.
- `prefers-reduced-motion`: mostrar o quadro final, sem movimento.
- Canvas 2D, `devicePixelRatio` até 2, um `requestAnimationFrame`, cancelado ao desmontar.

### Nanorrobôs

Só na ligação (`CallView`), onde o Muninn já é grande: quando ele usa uma ferramenta, as
partículas do corpo dele viram a forma dela e voltam a ser o corvo quando termina. Código em
`apps/web/src/muninn/` (`nanorrobos.logic.ts` puro e testado, `Nanorrobos.tsx` o canvas,
`MuninnDaLigacao.tsx` a escolha da forma).

- **De onde vem a forma.** Cada passo do turno (`core/conversation/progress.py`, no `/progress` e
  no stream) pode ter um `kind`:

  | `kind` | Passos | Forma |
  |---|---|---|
  | `gmail` | "Procurando no seu Gmail" | envelope |
  | `agenda` | "Olhando sua agenda" | calendário |
  | `pesquisa` | "Pesquisando …", "Procurando …" (pesquisa e busca do navegador) | lupa |
  | `site` | "Abrindo …", "Cotando voos", "Olhando hotéis", "Lendo site", "… recusou robôs", "Conferindo os preços de novo" | janela de navegador |
  | `mac` | "Montando o pedido ao Mac", "Olhando sua tela" | notebook |
  | `arquivo` | "Lendo arquivo", "Olhando a foto", "Lendo o próprio código" | página |

- **O desenho.** Canvas 2D com 3.000 partículas (2.000 abaixo de 400 px de largura de tela). O
  corvo sai amostrado de `strokes.json`, ao longo dos traços. As seis formas são desenhos de traço
  simples feitos em código, centralizados no anel.
- **A transformação.** Os pontos de cada forma são ordenados pelo ângulo em volta do centro, e a
  partícula i vai para o ponto i. Cada partícula anda em 1,6 s, `ease-in-out` cúbico, com atraso
  aleatório de até 0,5 s e uma curva lateral: deslocamento perpendicular × sin(πt) × 0,22 × um
  valor fixo da partícula entre -1 e 1. 2,5% das partículas são âmbar, as mesmas em todas as
  formas. Paradas, tremem 0,6 px.
- **O corvo.** Quando as partículas assentam no corvo, a ilustração aparece por cima delas (0,8 s)
  e elas somem, como na gênese; depois o olho acende. Ao sair do corvo, a ilustração e o olho se
  apagam em 0,3 s.
- **Regras.**
  - Só muda com um `kind` real; um passo sem `kind` mantém a forma.
  - "Pensando", "Escrevendo a resposta" e o fim do turno voltam ao corvo.
  - Cada forma fica no mínimo 1,2 s depois de formada (1,6 s + o atraso). Se vierem passos
    rápidos nesse meio-tempo, vai direto para o último.
  - O anel em volta continua com os estados de sempre (ouvindo, pensando): o `<Anel vazio>` desenha
    as marcas e o ponto, o canvas desenha o Muninn por baixo.
  - Em repouso no corvo nada se mexe e o `requestAnimationFrame` para; numa forma de ferramenta as
    partículas tremem.
- **`prefers-reduced-motion`:** sem transformação. O corvo e um ícone de traço da ferramenta (o
  mesmo desenho) trocam com um fade de 200 ms, o único movimento mantido.
- O texto do passo continua embaixo do nome, com `aria-live`.

## 7. Voz

Fala como alguém que anota: curto, sem prometer o que não fez, sem fingir sentir.

| Diz | Não diz |
|---|---|
| "Anotei. Quer que eu guarde isso?" | "Vou lembrar disso pra sempre!" |
| "Não sei ainda. Posso procurar e trazer a fonte." | "Com certeza é assim." |
| "Preparei a resposta. Só sai se você aprovar." | "Já enviei pra você ✨" |
| "Ainda não escolhi um nome." | "Pode me chamar de Visão!" |
| "Fala comigo…" / "Acompanhar um preço" | "Dê uma ordem" / "Vigiar um preço" |

Sem exclamação, sem emoji.

## 8. Migração

1. Tokens: trocar `apps/web/src/brand/tokens.css` pelos da seção 2 (e `Theme.swift` no iPhone).
   **Feito** no web; os nomes antigos (`--accent`, `--red`…) apontam para a paleta nova.
2. Fontes: Newsreader, Geist e Geist Mono no lugar de Space Grotesk, Inter Tight e JetBrains Mono.
   **Feito** no web, servidas pelo app (`public/fonts/`), sem Google Fonts.
3. Mascote: `<Ciclope>` vira `<Anel estado=…>` (estados da seção 6) e `<Muninn>` (gênese).
   **Feito** no web: os sensores viraram ícones de traço 1,5 px na cor do texto (`<Sensor>`), os
   nomes antigos de cor saíram de `tokens.css` e a abertura de 2,4 s fecha o anel em vez de acordar
   o Ciclope.
4. Login: Muninn grande + "Bem-vindo de volta." no lugar de "Identifique-se.". **Feito** no app
   web (`apps/web/src/muninn/`). O iPhone (`LoginView`) ainda não mudou.
5. Textos: seção 7. **Feito** no web: "Acompanhando…", "Fala comigo…", "Acompanhar um preço";
   saíram "Nada sob vigilância ainda", "Sistemas prontos" e "Pronto para a ordem"; avaliar uma
   resposta é "Ajudou" / "Não ajudou", sem emoji.
6. Ícones e imagens a partir do anel. **Feito** e depois substituído: `brand/generate_assets.py`
   (Python, no lugar do `generate-assets.swift`) gerava do anel o ícone do iPhone, os do PWA, o
   favicon, o wordmark `VISÃO`, o `muninn-512.png` e a `og-image`. Desde 25/11/2026 ele gera só os
   ícones do web, do Mac e do iPhone e a `og-image`, a partir do corvo de olho âmbar (seção 5); os
   outros arquivos ficaram como estavam em `brand/`.

Referência visual da direção "Muninn": canvas "Visão — identidade" no Claude.

### Telas do VISAO (identidade nova)

Prompt e ordem em [`docs/design/telas-visao/PROMPT_CLAUDE_CODE.md`](docs/design/telas-visao/PROMPT_CLAUDE_CODE.md),
na branch `design/telas-visao`:

Todas as etapas estão **feitas** no web (24/11/2026):

1. Base: três temas, fontes novas, ícones a partir do corvo, janela com barra da página e rodapé.
2. Barra lateral: corvo e VISAO, Nova conversa e lupa, nove lugares, Recentes. **Fixadas não
   aparece**: o servidor não guarda conversa fixada.
3. Barra de status: servidor, Braço, rotinas, silêncio, uso das últimas 24 h (não o dia do
   calendário: é o que `/cognition/metrics` mede) e o modelo, que abre a troca nuvem/Mac/automático.
4. Login com o selo; primeira vez em quatro passos (quem responde, memória, Mac, silêncio).
5. Início: corvo, saudação, pensamento, pedido de aprovação com o carimbo APROVADO, painel.
6. Chat: passos em cartões (Resumido ou Técnico), ponto âmbar de atividade, coluna Agora / O que fiz
   de verdade, ler em voz alta, compartilhar em Markdown e PDF. **O link privado espera o
   servidor.**
7. Paleta de comandos (Ctrl/⌘+K). 8. Caderno em cinco abas. 9. Rotinas, Mac, Painel, Projetos
   (grade de cartões; a linha sob o nome é a primeira anotação do projeto, porque o servidor não
   tem descrição) e Ajustes.
10. Ligação. 11. Celular com abas embaixo.
12. Agentes, Canais e Habilidades com estado vazio honesto; o autorretrato é o texto dele (o
    desenho não existe no servidor) e o aviso de versão não aparece (não há rota de novidades).

**Saiu** do app web: o anel como avatar e logo, o `<Lockup>` na barra lateral, o `MindPanel` (virou
as abas do Caderno) e a seção Integrações da barra lateral. A gênese do Muninn e o
`MuninnEntrance` continuam no código, sem uso no login, até decidirmos o que fazer com eles.

## 9. Skills de design no repositório

- Emil Kowalski, travadas em `skills-lock.json`: `emil-design-eng`, `choreograph`,
  `review-animations`, `animation-performance`, `learn-taste`. Instalar com
  `npx skills experimental_install`. Use `learn-taste` depois de corrigir um visual: ela transforma
  a correção em regra neste arquivo.
- Impeccable: rodar localmente `npx impeccable install` e `/impeccable init` (o download dela foi
  bloqueado no ambiente que abriu este PR). O `init` lê este DESIGN.md e o `PRODUCT.md`.
