# Marca: anel de rastros e Muninn

O Visão nasce sem nome. A marca não desenha um rosto: desenha o que ele deixa. Regras completas
(cor, tipo, forma, movimento, voz) em [DESIGN.md](../DESIGN.md).

- **Anel de rastros:** 24 marcas radiais, uma por hora; a falha no topo é o lugar do nome, vazia
  enquanto `chosen_name` for null. O ponto âmbar é a chamada ao modelo.
- **Muninn:** a forma de agora, o corvo da memória de Odin, dentro do anel
  ([muninn/](muninn/README.md)).
- **Uma luz só:** âmbar `#F0A23B` sobre tinta `#101214` e papel `#F3F1EC`.

## Arquivos

| Arquivo | Uso |
|---|---|
| `app-icon.png`, `app-icon-dark.png`, `app-icon-tinted.png` | Ícone do iPhone (1024, sem cantos: o iOS arredonda). Copiados para o `AppIcon.appiconset`. |
| `favicon.svg` | Favicon: o anel em traço contínuo com a falha e o ponto âmbar. |
| `visao-wordmark.svg` | O codinome `VISÃO` em Geist Mono, em contornos (não precisa da fonte). |
| `og-image.png` | Imagem de compartilhamento 1200 × 630: Muninn no anel e "Nasce sem nome." |
| `muninn-512.png` | O Muninn no anel, para documentos. |
| `muninn/` | Ilustração mestre, traços da gênese e o Muninn em ASCII. |

No web (`apps/web/public/`): `favicon.svg`, `favicon.ico` (16 e 32 com o anel simples, 48 com as
marcas), `apple-touch-icon.png` (180), `icon-192.png`, `icon-512.png`, `maskable-512.png` (anel a
82 %, dentro da zona segura), `og-image.png`; `theme-color` `#101214`.

## Regenerar

```bash
pip install pillow fonttools brotli
python brand/generate_assets.py
```

Desenha tudo em Python a partir da mesma geometria do anel (e da ilustração do Muninn) e escreve
em `brand/`, `apps/web/public/` e no `AppIcon.appiconset`. Roda em qualquer sistema; substituiu o
antigo `generate-assets.swift`, que só rodava no macOS.
