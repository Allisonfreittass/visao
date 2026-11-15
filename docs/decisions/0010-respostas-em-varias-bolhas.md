# ADR-0010: Respostas curtas, em até 3 bolhas, numa mensagem só

- Data: 2026-11-15
- Estado: aceita

## Contexto

No vídeo de 14/11/2026, as respostas no iPhone vinham em blocos longos: estimativas que ninguém
pediu, ressalvas, uma lista de fontes e "Como foi essa resposta?" embaixo de toda mensagem.
Mesmo quando a resposta chegava rápido, parecia lenta. Num assistente que responde em 2 ou 3
bolhas curtas, cada bolha se lê de relance.

Uma resposta, porém, é uma unidade para o resto do sistema: a memória cura mensagens, o
Responder (↩) cita uma mensagem, a avaliação e a adaptação versionada (ADR-0008) ligam o retorno
a uma mensagem, e o `model_usage` liga o custo a ela.

## Decisão

- **Tamanho:** a orientação de estilo (`core/conversation/style.py`, o arquivo que a evolução de
  código pode reescrever) pede uma mensagem de celular: de 2 a 4 frases curtas, até umas 60
  palavras, nunca mais de 3 parágrafos, sem estimativas, faixas, ressalvas ou fontes não
  pedidas. Código, planos e pedidos de detalhe podem ser longos.
- **O que nunca encurta:** o site e a hora de um preço ao vivo. Essa exigência fica no bloco do
  navegador (`core/browse.py`), fora do alcance da evolução de código.
- **Bolhas:** o modelo separa as partes naturais (confirmação, resultado, próximo passo) com uma
  linha só com `[[+]]`. O servidor (`core/conversation/parts.py`) tira os marcadores:
  - `messages.content` guarda o texto inteiro, partes unidas por linha em branco. Memória,
    citação, avaliação, voz e a checagem das regras leem esse texto, como antes;
  - `messages.parts` (JSON, migração `0026`) guarda as mesmas partes separadas. `null` é uma
    bolha só. A API devolve `parts` em cada mensagem.
- **Limites:** no máximo 3 partes (o que passar disso entra na última). Um `[[+]]` dentro de um
  bloco de código não quebra e nunca aparece. Na voz não há partes; no rascunho falado, o
  marcador vira pausa.
- **Checagem das regras do dono:** ela confere o texto sem os marcadores. Se reescrever, a
  reescrita vai numa bolha só (as quebras eram da versão anterior).
- **Na interface:** cada parte é uma bolha, uma depois da outra. Menu de contexto, Responder,
  avaliação e fontes valem para a mensagem inteira e ficam na última bolha.

## Alternativas descartadas

- **Uma mensagem por bolha no banco.** Quebraria a citação, a avaliação, a cobrança e a curadoria,
  que contam mensagens.
- **Separar no cliente por parágrafo.** Toda resposta de 2 parágrafos viraria 2 bolhas, inclusive
  código e listas. A quebra precisa ser escolhida por quem escreve.

## Consequências

- Mensagens antigas e clientes antigos continuam funcionando: `parts` nulo é uma bolha só, e
  `content` não mudou de forma.
- Medido com `experiments/eval_brevity.py` (modelo real, prompt com a mente ligada, ver
  [EVALUATION.md](../EVALUATION.md)): de 82,2 para 45,6 palavras médias por resposta de conversa
  (−45%); o pedido de código, que é o controle, não encolheu (42 → 61 palavras).
