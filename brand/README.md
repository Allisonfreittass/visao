# Marca: o corvo no eclipse (e o anel de rastros, que sai)

O Visão nasce sem nome. A marca não desenha um rosto: desenha o que ele deixa. Regras completas
(cor, tipo, forma, movimento, voz) em [DESIGN.md](../DESIGN.md).

- **Anel de rastros:** 24 marcas radiais, uma por hora; a falha no topo é o lugar do nome, vazia
  enquanto `chosen_name` for null. O ponto âmbar é a chamada ao modelo.
- **Muninn:** a forma de agora, o corvo da memória de Odin, dentro do anel
  ([muninn/](muninn/README.md)).
- **Corvo no eclipse:** o ícone do app e o avatar dele, em [`corvo/`](corvo/). Substitui o anel
  (identidade nova, [`docs/design/telas-visao/`](../docs/design/telas-visao/README.md)).
- **Uma luz só:** âmbar `#E39A2E` sobre tinta `#101214` e papel `#F6F4EF`.

## Arquivos

| Arquivo | Uso |
|---|---|
| `corvo/icone-grande-512.png`, `corvo/icone-pequeno-256.png` | O corvo no eclipse: o grande acima de 72 px, o pequeno (traço mais grosso) em 72 px ou menos. Fonte de todos os ícones do web. |
| `app-icon.png`, `app-icon-dark.png`, `app-icon-tinted.png` | Ícone do iPhone, ainda o anel (1024, sem cantos: o iOS arredonda). |
| `visao-wordmark.svg` | O codinome `VISÃO` em Geist Mono, em contornos (não precisa da fonte). |
| `og-image.png` | Imagem de compartilhamento 1200 × 630: Muninn no anel e "Nasce sem nome." |
| `muninn-512.png` | O Muninn no anel, para documentos. |
| `muninn/` | Ilustração mestre, traços da gênese e o Muninn em ASCII. |

No web (`apps/web/public/`): `favicon.ico` (16, 32 e 48, do desenho pequeno), `apple-touch-icon.png`
(180, de ponta a ponta), `icon-192.png` e `icon-512.png` (com os cantos arredondados do desenho),
`maskable-512.png` (de ponta a ponta) e `marca/corvo-256.png` e `marca/corvo-512.png` para o
`<Corvo>`. No app de Mac, `desktop/app/app-icon.png` (1024, o quadrado arredondado de 824 com sombra,
na grade da Apple), de onde `npx tauri icon` tira os tamanhos. A `og-image.png` ainda é a do anel.

## Regenerar

```bash
pip install pillow
python brand/generate_assets.py
```

Gera os ícones do web a partir dos dois desenhos de `corvo/` e escreve em `apps/web/public/`. O
ícone do iPhone, o wordmark, o `muninn-512.png` e a `og-image` não saem mais daqui: são os da
direção anterior e ficam como estão até o iPhone e o selo migrarem.
