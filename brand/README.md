# Marca: Ciclope Sentinela

Metal grafite, um sensor vermelho aceso, texto de sistema. O V.I.S.A.O. é um assistente-máquina
que vigia: frio, seco, sem caricatura.

## Regras

- **Tema:** só o escuro é exposto. O claro continua no código (`apps/web/src/brand/theme.ts`,
  `Appearance.forced` no iPhone), escondido.
- **Vermelho `#FF3B30` é raro:** olho do mascote, botão principal, foco, indicador de aba ativa,
  **uma** palavra de destaque por tela e erros de verdade. Texto sobre vermelho usa `#0B0B0D`,
  nunca branco. Atenção é âmbar `#F5B544`; sucesso é verde `#4ADE80`; o resto é grafite e cinza.
- **Tipografia:** Space Grotesk 600/700 (títulos, saudação, wordmark), Inter Tight (texto),
  JetBrains Mono 12 px só em metadados. Escala 12 / 13 / 15 / 16 / 20 / 30 / 44.
- **Forma:** raios 10 / 12 / 16 / 999, sem sombras (a borda de 1 px separa), sem gradiente em
  botões e cartões.
- **Fundo:** grade de pontos a cada 24 px e o brilho vermelho do sensor, que respira com o estado.
- **Tom:** frases curtas de sistema, sem exclamação nem emoji. "Identifique-se.", "Sistemas
  prontos.", "Executando no Mac."

Tokens: `apps/web/src/brand/tokens.css` (web) e `apps/ios/Visao/Theme.swift` (iPhone).

## O mascote

`<Ciclope>` (`apps/web/src/ciclope/Ciclope.tsx`) e `SentinelaView` (iPhone): corpo de metal,
olho-sensor vermelho, pálpebra de metal (neutra, alerta em V, fresta, fechada), LED e grade de
alto-falante. Estados: `idle`, `listening`, `thinking`, `speaking`, `working`, `error`,
`offline` (e `interrupted`, uma piscada e a pose de ouvir). Abaixo de 32 px some o LED e a grade.
Para ver todos: abra o web com `?orb=demo`. A abertura de boot: `?intro`.

Os **sensores** (`Family.tsx`, `SensorView`) são a família: Mac `#3B6BFF`, WhatsApp `#18C27A`,
E-mail `#E0A800`, Caderno `#9B87FF`; o olho apaga quando a integração está desconectada.

## Arquivos

| Arquivo | Uso |
|---|---|
| `app-icon.png`, `app-icon-dark.png`, `app-icon-tinted.png` | Ícone do iPhone (1024, sem cantos: o iOS arredonda). Copiados para o `AppIcon.appiconset`. |
| `favicon.svg` | Favicon simples (corpo, olho, núcleo). |
| `visao-wordmark.svg` | Wordmark em contornos (Space Grotesk 700, tracking .04em), pontos cinza e o último vermelho. |
| `og-image.png` | Imagem de compartilhamento 1200 × 630. |
| `sentinela-512.png` | O mascote sozinho, para documentos. |

No web (`apps/web/public/`): `favicon.svg`, `favicon.ico` (16/32/48), `apple-touch-icon.png`
(180), `icon-192.png`, `icon-512.png`, `maskable-512.png` (margem de 20%), `og-image.png`;
`theme-color` `#09090B`.

## Regenerar

```bash
swift brand/generate-assets.swift
```

Desenha tudo com CoreGraphics a partir da mesma geometria do mascote e escreve em `brand/`,
`apps/web/public/` e no `AppIcon.appiconset`.
