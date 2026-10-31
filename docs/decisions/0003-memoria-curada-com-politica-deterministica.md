# ADR-0003: Memória curada com política determinística e consentimento explícito

- Data: 2026-10-31
- Estado: aceita

## Contexto

A hipótese central do projeto é que memória curada melhora consistência e utilidade em relação
ao mesmo LLM sem memória. O master prompt (seção 7) pede que o modelo decida o que propor
guardar, com regras determinísticas independentes para privacidade, consentimento e segurança,
e que decisões de guardar e descartar sejam registradas.

## Decisão

- **Consentimento opt-in por usuário**, desligado por padrão.
- **Curadoria por lote ao fim da conversa** (gatilho: abrir conversa nova, ou pedido manual),
  uma chamada de LLM por lote. Não por mensagem: custo e cota (50 req/dia no plano grátis).
- **LLM propõe em JSON; política em código decide.** Política versionada
  (`POLICY_VERSION`), sem chamar modelo, testável caso a caso.
- **Decisões append-only no banco** (trigger), guardando só códigos; o conteúdo fica na proposta,
  que pode ser limpa quando o usuário apaga a memória.
- **Toda memória com escopo de um usuário.** Memória global fica para quando houver
  consentimento específico para isso.
- **Recuperação lexical + recência + confiança** na 3a; relacional elegível sem sobreposição
  de palavras. Embeddings na 3b, quando houver provedor de embeddings definido e custo medido.
- Memórias entram no prompt como **dados marcados**, nunca como instruções; conteúdo com cara
  de instrução é barrado já na política.

## Alternativas consideradas

- **Guardar tudo** (memória passiva): é a variante B dos experimentos; serve de baseline, não de
  produto.
- **Curar a cada mensagem**: mais fresco, mas multiplica chamadas e custo.
- **Deixar o LLM decidir sozinho**: viola a separação pedida pela seção 7; regras de
  privacidade não podem depender de um modelo obedecer.
- **pgvector desde já**: exige provedor de embeddings, custo e mais uma dependência; adiado
  até a medição mostrar que a busca lexical é insuficiente.

## Consequências

- Recuperação perde paráfrases até a 3b.
- O usuário precisa ligar a memória para ela existir; sem isso o sistema se comporta como na
  Fase 1.
- Modelos de raciocínio precisam de limite de saída maior para a curadoria
  (`VISION_LLM_CURATION_MAX_OUTPUT_TOKENS`, padrão 4096): com 1024 o Nemotron gastou tudo
  pensando e devolveu texto vazio.
