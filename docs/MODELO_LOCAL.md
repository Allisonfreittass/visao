# Modelo local: o Visão pensando com um modelo no seu Mac

> Primeira versão em 2026-11-18. Motivo: quando a cota da nuvem acaba, o Visão não pode ficar
> mudo, e você quer poder trocar de modelo só pedindo.

## A ideia

O Visão mora no servidor, na nuvem ([LIGHTSAIL.md](LIGHTSAIL.md)). O modelo local roda no seu
Mac, com o [Ollama](https://ollama.com). O servidor não alcança o Mac, porque nenhuma porta é
aberta em casa. Quem leva a pergunta é o **braço** ([BRACO.md](BRACO.md)), que já fala com o
servidor de dentro para fora:

```
Visão (servidor) ── grava a pergunta ──> arm_llm_calls
braço (Mac) ── pega a pergunta (long poll) ──> Ollama no próprio Mac ──> devolve só o texto
```

Para o resto do servidor, o modelo local é só mais um provedor (`LocalModelProvider` em
`core/arm/local_llm.py`), com preço zero.

## Os três modos (`core/brain.py`)

| Modo | Conversa | Trabalho de fundo (curadoria, estudo, pensamentos) |
|---|---|---|
| **Nuvem** (padrão) | só a nuvem, como antes | nuvem |
| **Local** | modelo do Mac primeiro, nuvem de reserva | pausado (o worker adia e tenta depois) |
| **Automático** | nuvem primeiro, modelo do Mac se ela falhar | nuvem |

Um Mac desligado, dormindo ou sem modelo falha na hora com `network`, e a próxima opção responde.
O Visão nunca fica esperando um Mac que não está lá.

O trabalho de fundo fica pausado no modo Local porque ele pede respostas em formato rígido (JSON),
e um modelo pequeno erra isso com frequência.

## Como trocar

- **No chat:** "usa o modelo local", "volta pro Claude", "modo automático", "troca para a nuvem",
  ou `/modelo local|nuvem|auto`. Só `/modelo` responde qual está em uso. A frase é reconhecida em
  código, sem chamar modelo nenhum, então a troca funciona mesmo com a cota zerada. Perguntas
  ("o que é um modelo local?") e frases longas ("usa o qwen pra resumir isso") não são ordens.
- **Em Ajustes > Modelo**, no web e no iPhone. A tela mostra se o Mac está oferecendo o modelo.

As respostas escritas pelo modelo local aparecem como **"Visão · local"** no chat do web.

## Montando no Mac

1. Instale o Ollama e baixe o modelo:
   ```bash
   brew install ollama
   ollama pull qwen3:4b
   ```
   No M1 com 8 GB, o Qwen3 4B (uns 2,5 GB) é o tamanho que cabe com folga. Modelos de 7–8B rodam,
   mas apertados.
2. Deixe o Ollama aberto (o app, ou `brew services start ollama`).
3. No `~/.config/visao/braco.json`, acrescente:
   ```json
   "modelo_local": { "modelo": "qwen3:4b", "endereco": "http://127.0.0.1:11434", "contexto": 16384 }
   ```
4. Reinicie o braço (`launchctl kickstart -k gui/$(id -u)/digital.visao.braco`, ou rode
   `arm/instalar-mac.sh` de novo). Ele avisa no log: `Modelo local: qwen3:4b`.

## Segurança

- **As perguntas levam suas conversas.** Por isso o braço só aceita um endereço do próprio Mac
  (`127.0.0.1` ou `localhost`), e recusa qualquer outro ao carregar a configuração.
- O braço só devolve texto. O texto volta para o mesmo caminho de uma resposta da nuvem: nada do
  que o modelo escreve vira comando no Mac.
- Só o aparelho que pegou a pergunta pode respondê-la. Uma resposta atrasada, depois de o servidor
  ter desistido, é descartada.
- A troca de modo fica registrada na auditoria (`brain.mode`, com `via: chat` ou `ajustes`).

## Limites

- **Qualidade:** um modelo de 4B é bem mais fraco que o Claude. Serve para conversa e resumos, mas
  erra mais em raciocínio, contas e formatos.
- **Contexto curto:** o servidor manda no máximo `VISION_LOCAL_LLM_CONTEXT_CHARS` (40 mil
  caracteres): as mensagens de sistema e os turnos mais recentes que couberem. O braço pede ao
  Ollama um contexto de 16 mil tokens (`contexto`).
- **Sem imagens:** com foto na mensagem, a pergunta vai direto para a nuvem.
- **Tempo:** o servidor espera até `VISION_LOCAL_LLM_TIMEOUT_SECONDS` (120 s) e então passa para a
  nuvem. A velocidade no M1 ainda não foi medida.
- **Só a conversa:** o trabalho do braço nos projetos continua com o Claude Code. Um modelo de 4B
  não consegue fazer esse trabalho.
