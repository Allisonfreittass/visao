# DESIGN.md — Visão

Fonte única do visual do Visão. Todo agente (Claude Code, Codex, Cursor) e toda pessoa que mexer
em interface lê este arquivo antes. Se uma tela nova não couber nestas regras, a regra muda aqui
primeiro, depois o código.

> **Estado:** direção aprovada em 23/11/2026 ("Muninn"). No app web, os passos 1, 2 e 4 da
> [Migração](#migração) estão feitos: tokens e fontes do Muninn em todo o app
> (`apps/web/src/brand/tokens.css`, `fonts.css`) e o login no Muninn. Ainda da marca anterior: o
> mascote Ciclope (com o olho já em âmbar), as cores dos sensores, os ícones e o iPhone
> (`Theme.swift`). Telas novas já seguem este arquivo.

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
- Âmbar aparece no máximo em **um** bloco por tela além do olho (ex.: o cartão de pedido).
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

## 6. Movimento

A animação é onde o Visão se diferencia. Regras (base: skills `emil-design-eng`, `choreograph`):

- **Gênese** (login, primeira abertura, quando ele "acorda"), 14 s, não em loop dentro do app:
  1. 0 s: o ponto âmbar acende no peito.
  2. 0,4–6,4 s: os traços de `strokes.json` nascem em ordem, 0,55 s cada, `ease-out` cúbico,
     soltando faíscas (7% de chance por ponta; 15% delas âmbar).
  3. 6,2–8,4 s: a ilustração aparece por cima, tingida de papel → cinza; o olho acende.
  4. 8,4 s: o anel se fecha, marca a marca (50 ms entre elas); a falha do topo pisca em âmbar.
- Entradas usam `ease-out`; nada de `ease-in` em elemento que entra.
- Estados do anel no app: ocioso (hora local acesa), ouvindo (marcas em onda), pensando (um
  rastro percorre o anel em 1,6 s por volta: a marca da frente em âmbar, a cauda apagando em
  papel → cinza), fala primeiro (ponto sobe à falha), pede aprovação (falha acesa), pausado
  (ponto vazado), silêncio (tudo apagado).
- `prefers-reduced-motion`: mostrar o quadro final, sem movimento.
- Canvas 2D, `devicePixelRatio` até 2, um `requestAnimationFrame`, cancelado ao desmontar.

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
4. Login: Muninn grande + "Bem-vindo de volta." no lugar de "Identifique-se.". **Feito** no app
   web (`apps/web/src/muninn/`). O iPhone (`LoginView`) ainda não mudou.
5. Textos: seção 7.
6. `brand/generate-assets.swift`: regenerar ícones a partir do anel.

Referência visual completa (telas de computador e celular, estados, animação): canvas
"Visão — identidade" no Claude.

## 9. Skills de design no repositório

- Emil Kowalski, travadas em `skills-lock.json`: `emil-design-eng`, `choreograph`,
  `review-animations`, `animation-performance`, `learn-taste`. Instalar com
  `npx skills experimental_install`. Use `learn-taste` depois de corrigir um visual: ela transforma
  a correção em regra neste arquivo.
- Impeccable: rodar localmente `npx impeccable install` e `/impeccable init` (o download dela foi
  bloqueado no ambiente que abriu este PR). O `init` lê este DESIGN.md e o `PRODUCT.md`.
