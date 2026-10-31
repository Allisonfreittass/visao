# ADR-0009: Camada de decisão separada da expressão e ciclo autônomo com orçamento

- Data: 2026-10-31
- Estado: aceita

## Contexto

A auditoria da Fase 9 ([cognitive_audit.md](../research/cognitive_audit.md)) mostrou que o
sistema se comportava como chatbot reativo. Cinco causas:

1. O prompt fixo declarava incapacidades falsas ("sem acesso à internet, ferramentas ou voz").
2. O mecanismo de nome existia, mas nada o chamava.
3. Nada acontecia sem mensagem, a não ser após uma aprovação manual.
4. A continuidade entre sessões nunca entrava no contexto.
5. O LLM descrevia ações que não tinham sido executadas.

## Decisão

- **Capacidades** vêm de um manifesto construído em código a partir da configuração e do banco
  (`core/identity/capabilities.py`). O prompt só lista como ausente o que está ausente.
- **Turno:** cada turno passa por `run_turn` (`core/decision/pipeline.py`). As ações executadas
  viram fatos do turno e uma linha em `decisions`. O LLM só redige.
- **Nome:** a deliberação é um job próprio, com resultado escolher, adiar ou recusar, sem lista
  de nomes fornecida.
- **Ação sem mensagem:** o ciclo autônomo roda por agenda idempotente, nunca em laço contínuo.
  Respeita a pausa global, permissões permanentes (`auto_research`, desligada por padrão) e um
  orçamento diário só das ações autônomas.

## Alternativas descartadas

- **Só reescrever o prompt.** Removeria o texto falso, mas não daria capacidade real: o nome
  continuaria sem caminho de decisão e nada aconteceria entre sessões.
- **Agente com ferramentas livres (function calling).** Mais flexível, mas tira do código a
  decisão sobre o que pode ser feito, e o modelo gratuito atual é instável com ferramentas.
- **Laço contínuo de "pensamento".** Custo sem limite e sem gatilho real, o que viola a §19.

## Consequências

- **Auditoria:** toda ação, de turno ou autônoma, fica registrada.
- **Prompt:** o system prompt cresce, por causa do manifesto e da continuidade, e a latência
  mediana subiu cerca de 2,5 s.
- **Nome:** pode continuar `null` indefinidamente. Adiar é resultado válido.
