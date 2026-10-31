# ADR-0008: Estado comportamental versionado por interlocutor e lições com evidência repetida

- Data: 2026-10-31
- Estado: aceita

## Contexto

Seções 8, 8.2 e 10: medir tendências observáveis, adaptar por regras versionadas, testáveis e
reversíveis, não tomar autodescrições do LLM como prova, não transformar uma falha isolada em regra
permanente, refletir comparando esperado e observado.

## Decisão

- Métricas calculadas em código sobre cada resposta, com a versão do estado em vigor.
- Estado = parâmetros de comunicação derivados por regras de retorno repetido (≥ 3) e de lições
  ativas; versões append-only com evidência; reverter cria versão nova.
- Escopo por interlocutor (evita levar preferência de uma pessoa para outra).
- Reflexão por conversa encerrada, só com evidência; lições provisórias até duas mensagens
  diferentes as sustentarem; lições de personalidade rejeitadas.

## Alternativas consideradas

- **Pedir ao modelo para descrever o próprio estilo:** proibido como evidência pela seção 8.
- **Ajuste global, para todos os interlocutores:** mistura gostos e vaza informação relacional.
- **Ajustar a cada retorno:** um clique viraria regra; contraria a seção 10.

## Consequências

- Mudanças lentas por construção (3 retornos iguais).
- O efeito depende de o modelo seguir as instruções; foi medido (−69% de palavras) mas não é
  garantido para outros modelos.
- A avaliação expôs respostas cortadas por limite de tokens em modelo de raciocínio: agora são
  marcadas como interrompidas e o limite padrão local subiu para 3072.
