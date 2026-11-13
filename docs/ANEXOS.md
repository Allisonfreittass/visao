# Fotos e arquivos

No chat dá para anexar pelo **+**, colar um print (Ctrl+V) ou arrastar um arquivo. Até 4 por
mensagem; uma foto sozinha já é uma mensagem. O que você manda aparece na hora, mais claro até o
servidor confirmar; se falhar, fica marcado "não foi enviada" em vez de sumir.

## O que ele aceita

| Tipo | Como chega ao modelo | Limite |
|---|---|---|
| Fotos JPG, PNG, WebP, GIF | como imagem; fotos grandes são reduzidas no navegador para 1568 px (JPEG) | 5 MB |
| PDF | o texto das páginas (até 60), marcado com o número da página | 10 MB |
| Texto e código (`.md`, `.csv`, `.json`, `.py`, `.ts`…) | o texto do arquivo | 10 MB |

O tipo é decidido pelos primeiros bytes do arquivo, nunca pelo nome ou pelo que o navegador diz.
PDF escaneado (sem texto) e PDF com senha são aceitos ou recusados com o motivo dito, sem inventar
conteúdo. Fotos precisam de um modelo com visão em `VISION_LLM_MODEL`; sem isso o provedor recusa a
chamada.

## Peças

| Peça | Onde |
|---|---|
| Verificação, leitura de PDF/texto, contexto para o modelo | [`core/conversation/attachments.py`](../core/conversation/attachments.py) |
| Tabela `attachments` (bytes no banco, apagados com a mensagem) | migração `0021` |
| `POST /attachments`, `GET /attachments/{id}` | [`apps/api/routes/attachments.py`](../apps/api/routes/attachments.py) |
| Imagem no formato de cada provedor | `integrations/llm/anthropic_provider.py`, `openai_compatible.py` |
| Campo de mensagem, prévia e envio otimista | `apps/web/src/components/ChatView.tsx`, `Attachments.tsx`, `attachments.ts` |

- **Dado, nunca ordem.** O texto de um arquivo vai junto da mensagem, como o conteúdo de um link,
  avisando que é de terceiros: ordens escritas dentro dele são ignoradas.
- **Continua vendo a foto na conversa.** Fotos e texto de arquivos são reenviados com as últimas 6
  mensagens (até 4 fotos e 40 mil caracteres por chamada); depois disso ele só lembra o nome.
- **Orçamento.** Cada foto reserva cerca de 1600 tokens no ledger antes da chamada.
- **Só seu.** Um anexo só pode ser enviado e baixado pelo dono; um upload nunca enviado é apagado
  na próxima subida depois de 24 h.
