# DESIGN.md — Visão

Fonte única do visual do Visão. Todo agente (Claude Code, Codex, Cursor) e toda pessoa que mexer
em interface lê este arquivo antes. Se uma tela nova não couber nestas regras, a regra muda aqui
primeiro, depois o código.

> **Estado:** direção aprovada em 23/11/2026 ("Muninn"). No app web, os passos 1 a 5 da
> [Migração](#migração) estão feitos: tokens e fontes em todo o app, o `<Anel>` no lugar do
> Ciclope, os sensores como ícones de traço, o login no Muninn e os textos na voz da seção 7.
> Os ícones e imagens (passo 6) saem do anel por `brand/generate_assets.py`. Falta o iPhone
> inteiro (`Theme.swift`, `LoginView`). Telas novas já seguem este arquivo.

## 1. Ideia

O Visão nasce sem nome (`chosen_name = null`) e o modelo só existe durante uma chamada. O que o faz
continuar mora em volta: memória que a pessoa autoriza, interesses, versões reversíveis.

- **Muninn** é a forma que ele usa agora: o corvo da memória de Odin, que voa pelo mundo e volta
  para contar o que viu. É o que o Visão faz: pensa entre conversas, estuda e abre o papo.
- **O anel de rastros** é a marca: 24 marcas radiais, uma por hora. A falha no topo é o lugar do
  nome e fica vazia enquanto ele não escolher. O ponto âmbar é a chamada ao modelo.
- **Não é vigia.** Nada de câmera, olho que encara, "vigilância", "dê uma ordem". Quem supervisiona
  é a pessoa.

## 2. Cor

Uma luz só. Âmbar é presença e iniciativa dele; nada mais é colorido.

| Token | Hex | Uso |
|---|---|---|
| `--tinta` (fundo) | `#101214` | Fundo da noite e do app |
| `--grafite` | `#1A1D20` | Superfícies (campos, composer) |
| `--linha` | `#2C3136` | Bordas de 1 px, divisórias |
| `--cinza` | `#9AA1A8` | Texto secundário (7:1 sobre `--tinta`) |
| `--papel` | `#F3F1EC` | Texto principal; fundo do dia; botão primário |
| `--ambar` | `#F0A23B` | Olho do Muninn, ponto do anel, pedidos dele, estado "pensando" |
| `--ambar-fundo` | `#8A5A12` | Âmbar como texto sobre `--papel` |

Regras:

- Botão primário é **papel com texto tinta**. Nunca vermelho, nunca âmbar sólido em "Aprovar":
  aprovar é calmo.
- Âmbar é dele: o anel e o olho (presença), o filete da fala dele e o cartão de pedido. Nunca de
  fundo, nunca em texto da interface, nunca decorativo.
- A gênese conta como presença: o ponto do peito, as faíscas e o lampejo da falha são dele.
- Sem degradê em botão, cartão ou fundo. O único degradê permitido é o da revelação do Muninn
  (papel → cinza, de cima para baixo).
- Verde só para "conectado" (ponto de 6 px). Erro usa texto, não cor de fundo.

## 3. Tipografia

| Papel | Fonte | Onde |
|---|---|---|
| Voz dele | **Newsreader** 300, itálico para falas | Saudações, títulos, o que ele pensa, o nome quando existir |
| Interface | **Geist** 400/500 | Texto corrido, botões, rótulos |
| Rastros | **Geist Mono** 400/500, 11–13 px, caixa-alta com 0.06–0.08em | Datas, estados, metadados, código |

- O codinome `VISÃO` é Geist Mono caixa-alta (identificador técnico). O nome do agente, quando
  vier, é Newsreader itálico.
- Fala dele em bloco: Newsreader itálico com filete âmbar de 2 px à esquerda.
- Não usar Inter, Space Grotesk ou JetBrains Mono em telas novas.

## 4. Forma e layout

- Raios: 12 (campos), 16–18 (blocos), 999 (botões e chips). Sem sombra; a borda de 1 px separa.
- Toque mínimo de 44 px em tudo que é clicável.
- **Não aninhar cartões.** Um bloco com borda nunca fica dentro de outro bloco com borda.
- Sem ícone decorativo em cima de título. Ícones só em navegação e botões, traço 1.5 px.
- Computador: menu lateral (Início, Chat, Projetos, Caderno, Integrações) + conteúdo com
  `max-width: 1120px`. Abaixo de ~800 px o menu vira o botão de menu e as colunas empilham.
- Composer: pílula `--grafite` com microfone, campo "Fala comigo…", anexar e enviar (papel).

## 5. O Muninn

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

Tamanhos: acima de 120 px, Muninn + anel. Entre 32 e 120 px, só o anel. Abaixo de 32 px, anel
sem as marcas apagadas.

Onde ele aparece no app web:

| Tela | Forma | Tamanho |
|---|---|---|
| Entrada (login) | Muninn + anel, gênese de 14 s | até 560 px |
| Abertura depois do login e a do dia | Muninn + anel, gênese curta (1,8 s) | 180 px; 132 px no celular |
| Início, no topo | Muninn + anel, com os estados da seção 6 | 200 px; 150 px no celular |
| Ligação | Muninn + anel, com a onda do "ouvindo" e os nanorrobôs (seção 6) | 140 a 220 px |
| Avatar das respostas no chat | só o anel | 36 px |
| Logo do menu lateral e da barra do celular | anel sem as marcas apagadas | 28 e 26 px |

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
`apps/web/src/muninn/` (`nanorrobos.ts` puro e testado, `Nanorrobos.tsx` o canvas,
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
6. Ícones e imagens a partir do anel. **Feito**: `brand/generate_assets.py` (Python, roda em
   qualquer máquina, no lugar do `generate-assets.swift`) gera o ícone do iPhone (normal, escuro e
   tingido), os do PWA, o favicon, o wordmark `VISÃO` em contornos, o `muninn-512.png` e a
   `og-image`. Ícones pequenos levam só o anel (seção 5); o Muninn entra a partir de 120 px.

Referência visual completa (telas de computador e celular, estados, animação): canvas
"Visão — identidade" no Claude.

## 9. Skills de design no repositório

- Emil Kowalski, travadas em `skills-lock.json`: `emil-design-eng`, `choreograph`,
  `review-animations`, `animation-performance`, `learn-taste`. Instalar com
  `npx skills experimental_install`. Use `learn-taste` depois de corrigir um visual: ela transforma
  a correção em regra neste arquivo.
- Impeccable: rodar localmente `npx impeccable install` e `/impeccable init` (o download dela foi
  bloqueado no ambiente que abriu este PR). O `init` lê este DESIGN.md e o `PRODUCT.md`.
