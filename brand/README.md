# Marca: o corvo de olho âmbar (e o anel de rastros, que sai)

O Visão nasce sem nome. A marca não desenha um rosto: desenha o que ele deixa. Regras completas
(cor, tipo, forma, movimento, voz) em [DESIGN.md](../DESIGN.md).

- **Anel de rastros:** 24 marcas radiais, uma por hora; a falha no topo é o lugar do nome, vazia
  enquanto `chosen_name` for null. O ponto âmbar é a chamada ao modelo.
- **Muninn:** a forma de agora, o corvo da memória de Odin, dentro do anel
  ([muninn/](muninn/README.md)).
- **Corvo de olho âmbar:** o ícone do app e o avatar dele, em vetor em [`simbolo/`](simbolo/): o corvo
  em close, preto sobre papel, com o olho âmbar. Substitui o anel e o corvo no eclipse (o busto
  diante de um sol âmbar, que saiu em 25/11/2026). Telas em
  [`docs/design/telas-visao/`](../docs/design/telas-visao/README.md).
- **Uma luz só:** âmbar `#E39A2E` sobre tinta `#101214` e papel `#F6F4EF`.

## Arquivos

| Arquivo | Uso |
|---|---|
| `simbolo/corvo-olho-icone.svg`, `simbolo/corvo-olho-pequeno.svg` | O corvo de olho âmbar, em vetor: o ícone de 64 px para cima, o pequeno (corte fechado na cabeça, só o olho e o bico) até 48 px. Fonte de todos os ícones do app. |
| `app-icon.png`, `app-icon-dark.png`, `app-icon-tinted.png` | Ícone do iPhone, o corvo de olho âmbar (1024, sem cantos: o iOS arredonda): cópias do que vai em `apps/ios/Visao/Assets.xcassets/AppIcon.appiconset/`. O escuro é o mesmo corvo sobre papel; o tingido é o desenho em cinza, que o iOS colore pelo brilho. |
| `visao-wordmark.svg` | O codinome `VISÃO` em Geist Mono, em contornos (não precisa da fonte). |
| `og-image.png` | Imagem de compartilhamento 1200 × 630: Muninn no anel e "Nasce sem nome." |
| `muninn-512.png` | O Muninn no anel, para documentos. |
| `muninn/` | Ilustração mestre, traços da gênese e o Muninn em ASCII. |

No web (`apps/web/public/`): `favicon-16.png`, `favicon-32.png` e `favicon.ico` (16, 32 e 48), do
desenho pequeno; `apple-touch-icon.png` (180, de ponta a ponta: o iPhone arredonda), `icon-192.png` e
`icon-512.png` (com os cantos arredondados do desenho) e `maskable-512.png` (o desenho a 84 %, no
canto de baixo à esquerda, para a cabeça e o bico caberem no círculo seguro do Android). As URLs levam
`?v=olho` no `index.html` e no manifest: o Chrome só troca o ícone de um app instalado quando a URL
muda. No app de Mac, os ícones de `desktop/app/src-tauri/icons/` (o `icon.icns` e os PNGs que o
Tauri lê) e o `desktop/app/app-icon.png` (1024): o quadrado arredondado de 824/1024 do lado, com
sombra, na grade da Apple. Em 16 e 32 pt (listas do Finder, Spotlight, menus) vai o desenho pequeno,
também nos pixels 2x da tela Retina; de 128 pt para cima, o inteiro. A `og-image.png` ainda é a do
anel.

## Regenerar

```bash
uv venv /tmp/marca && uv pip install --python /tmp/marca/bin/python pillow cairosvg
/tmp/marca/bin/python brand/generate_assets.py
```

Cada tamanho sai direto do vetor (o cairosvg usa o libcairo do sistema), o `.icns` inclusive: não
precisa do `npx tauri icon`, que tiraria todos os tamanhos de uma imagem só. O wordmark, o
`muninn-512.png` e a `og-image` não saem daqui: são os da direção anterior e ficam como estão até o
selo migrar.
