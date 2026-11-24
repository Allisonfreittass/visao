# O Visão no mouse e no teclado

> Primeira versão em 24/11/2026 (braço versão 6, [ADR-0024](decisions/0024-mouse-e-teclado.md)).
> É o nível 3. O nível 1, só olhar a tela, está em [TELA.md](TELA.md).

## Como usar

1. No `braco.json` do PC, escreva `"mexer": true` e religue o braço. Só no Linux com X11, com o
   `xdotool` e o ImageMagick instalados.
2. No chat, escreva `/pc` e o pedido, por exemplo `/pc abre o YouTube e procura jazz para
   estudar`.
3. Ele avisa no PC e começa. Você vê o cursor se mexer. A cada passo ele olha a tela, decide uma
   ação e confere na tela seguinte se deu certo.
4. No fim, a resposta volta na conversa: "Mexi no seu PC." e o que ele fez.

**Para parar:** mexa o mouse, escreva `/pc parar` ou toque em **parar** na página Mac.

## O risco, dito claramente

Ele mexe no **seu desktop de verdade**, com tudo que você tem aberto e logado. A escolha foi sua,
em 24/11/2026.

- Não existe sandbox para o mouse.
- Se uma página aberta tiver uma instrução escondida, o modelo pode ser levado a clicar ou
  digitar onde não deve, dentro das suas contas, durante os 10 minutos da sessão.

O que limita isso:

- só você abre uma sessão, com `/pc`, e uma por vez;
- 10 minutos, 40 passos e US$ 0,50 por sessão, contados no servidor;
- você vê e para quando quiser, até só mexendo o mouse;
- os para-choques: ele não abre o terminal, não usa a tecla Super e não digita nada com cara de
  comando (`sudo`, `| sh`, `rm -rf`, `curl … |`);
- só Claude e OpenAI veem a tela;
- o prompt manda não digitar senhas, não comprar, não enviar mensagens e não apagar nada. Isso é
  instrução ao modelo, não garantia.

Para tirar o alcance às suas contas, dá para trocar por uma área de trabalho só dele, numa janela
(Xephyr, que este PC já tem).

## Peças

| Peça | Onde |
|---|---|
| Pedido (`/pc`), parar | `POST /arm/desktop`, `POST /arm/desktop/stop` em `apps/api/routes/arm.py`; `request_desktop`, `stop_desktop` em `core/arm/service.py` |
| Cada passo: limites, modelo, validação | `core/arm/desktop.py`, `POST /arm/device/tasks/{id}/desktop` |
| Captura, ação e para-choques no PC | `run_desktop`, `do_action` em `arm/visao_braco.py` |
| No chat e na página Mac | `parsePcCommand` em `apps/web/src/arm.ts`, `App.tsx`, `MacView.tsx` |
| `arm_tasks.stop_requested` | migração `0040` |
