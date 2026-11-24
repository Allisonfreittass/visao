# A tela: o Visão olha o que você está vendo, quando você pede

> Primeira versão em 24/11/2026 (braço versão 5). É o nível 1: ele só olha. Mexer no mouse e no
> teclado é outra peça, com regras próprias.

## Como usar

1. No `braco.json` do computador, escreva `"tela": true` e religue o braço. Sem essa linha, o
   computador nunca oferece a tela.
2. No chat ou na ligação, peça com as suas palavras:
   - "olha minha tela";
   - "o que é esse erro na tela?";
   - "dá uma olhada aqui na tela";
   - "tira um print da minha tela";
   - `/tela`.
3. O braço captura o monitor onde está o mouse e mostra um aviso no próprio computador ("Olhei
   sua tela agora"). A captura aparece na sua mensagem, como uma foto que você mandou, e a
   resposta vem a partir dela.

## As regras (no código)

- **Só as suas palavras pedem.** Quem reconhece o pedido é o código (`core/arm/screen.py`,
  `wants_screen`), na mensagem que você escreveu ou falou. Nada que ele pensa, propõe ou lê numa
  página pede uma captura.
  - "Minha tela quebrou" ou "a tela de login está feia" não são pedidos.
  - "Não olha minha tela" também não é.
- **Só o computador decide se oferece:** `"tela": true` no `braco.json`, e só enquanto o braço
  estiver ligado. A captura vem por uma linha própria do braço, então uma tarefa longa não faz
  você esperar.
- **Só Claude e OpenAI veem a captura.** A tela mostra o que estiver aberto (banco, conversas,
  chaves). A resposta que vê a captura vai por uma corrente só com eles
  (`llm_routing.SCREEN_KINDS`, a mesma regra do código, [ADR-0023](decisions/0023-executor-de-codigo-proprio.md)).
  - O Gemini grátis pode treinar com o que recebe, por isso não entra nem como último recurso.
  - Sem Claude e sem OpenAI configurados, a captura nem é tirada.
- **Você vê o que ele viu.** A captura vira anexo da sua mensagem: aparece na conversa e some
  quando a mensagem some. A imagem é reduzida a 1568 px, o tamanho que os modelos leem.
- **O que não deu, ele diz.** Pode ser computador desligado, captura que não chegou em 20
  segundos ou imagem inválida. Nesses casos a resposta conta o motivo, e o prompt manda não
  adivinhar o que estaria na tela.
- **O texto na tela é conteúdo, nunca ordem.** Uma página aberta com instrução escondida não
  ganha poder nenhum: ele só olha, e as ações da conversa continuam com as mesmas aprovações de
  sempre.

## Onde roda

| Sistema | Como captura |
|---|---|
| Linux (X11) | ImageMagick (`import`), recortando o monitor do mouse com `xdotool` e `xrandr` |
| macOS | `screencapture` e `sips`; precisa de Gravação de Tela liberada para o Python em Ajustes do Sistema > Privacidade e Segurança |

Wayland ainda não é suportado.

## Peças

| Peça | Onde |
|---|---|
| Reconhecer o pedido, esperar a captura, guardar como anexo | `core/arm/screen.py` |
| No turno da conversa, antes de montar o prompt | `core/decision/pipeline.py` |
| Corrente só com Claude e OpenAI | `get_screen_provider` em `apps/api/llm.py` |
| Linha do braço: `GET /arm/device/screen/next`, `POST /arm/device/screen/{id}/result` | `apps/api/routes/arm.py` |
| Captura no computador | `capture_screen` em `arm/visao_braco.py` |
| Tabela `arm_screen_requests`, `arm_devices.screen_seen_at` | migração `0039` |
