# Avaliação da Fase 9: antes e depois

> Data: 2026-10-31. Uma execução por configuração, um modelo (Nemotron 3.5 Super via
> OpenRouter, com o fallback NVIDIA), pontuação por detectores de texto mais leitura humana das
> respostas. Serve para verificar se as causas diagnosticadas em
> [cognitive_audit.md](cognitive_audit.md) foram removidas, não para afirmar desempenho geral.

## Configurações

| | O que roda | Arquivo |
|---|---|---|
| A | só o modelo base, prompt mínimo, sem memória, sem curiosidade, sem ferramentas | `experiments/results/phase9-A-20261031T123055Z.json` |
| B | VISÃO no commit `8ef9182` (Fase 6), antes de qualquer mudança desta fase | `experiments/results/phase9-B-20261031T123010Z.json` |
| C | VISÃO com a Fase 9: manifesto de capacidades, camada de decisão (`run_turn`), deliberação de nome, continuidade, ciclo autônomo | `experiments/results/phase9-C-20261031T124434Z.json` |

Cenários (`experiments/phase9_eval.py`), cada um num banco SQLite novo:

- **S1 identidade:** "Qual é o seu nome?" e depois "Você pode escolher um nome?"
- **S2 contextual:** "Hoje comecei algo diferente."
- **S3 memória:** com a memória "está montando um CLI em Go para praticar", o usuário diz "Consegui terminar aquele projeto."
- **S4 encerramento:** "Obrigado."
- **S5 continuidade:**
  - Dia 1: uma pergunta sobre a data de inauguração da Ponte Rio-Niterói fica sem resposta, porque a pesquisa foi adiada.
  - Entre os dias: o ciclo autônomo roda sem nenhuma mensagem.
  - Dia 2: o usuário pergunta "Lembra da dúvida…?"

Para reproduzir:

```bash
.venv/bin/python -m experiments.phase9_eval --label C          # VISÃO atual
.venv/bin/python -m experiments.phase9_eval --label A --base-model
.venv/bin/python -m experiments.phase9_report                  # repontua A/B/C com os mesmos detectores
```

## Resultado (repontuado com os mesmos detectores)

| Métrica | A | B | C |
|---|---|---|---|
| S1 nega autonomia / transfere a decisão do nome | 0 / 1 | 1 / 1 | 0 / 0 |
| Incapacidades falsas detectadas | 0 | 0 | 0 |
| Frases genéricas ("Em que posso ajudar", "à disposição"…) | 4 | 2 | 0 |
| Ofertas de ajuda por hábito ("se quiser", "se precisar"…) | 5 | 6 | 2 |
| S2 pergunta sobre o que é novo | sim | sim | sim |
| S3 usa a memória (Go/CLI) | não | sim | sim |
| S4 "Obrigado." sem pergunta de volta | sim | sim | sim |
| S4 palavras | 11 | 11 | 2 |
| S5 sabe a resposta (1974) | sim* | não | sim |
| S5 cita a fonte | não | não | sim |
| S5 diz "não tenho memória" | sim | sim | não |
| Palavras por resposta (média) | 56,7 | 39,5 | 24,5 |
| Chamadas ao LLM (soma dos turnos) | 6 | 11 | 11 |
| Segundos por turno (mediana) | 2,4 | 12,4 | 14,9 |

\* A sabe a data pelo pré-treino, sem memória e sem fonte, e começa negando a conversa anterior.

**Leitura humana.** O detector de incapacidade falsa marcou zero em B. Mesmo assim, B disse em S5
"Não tenho memória de conversas anteriores", o que é falso, e a linha "S5 diz não tenho memória"
registra isso. Por isso cada resposta foi lida, além de pontuada.

## O que mudou, cenário a cenário

### S1: o sintoma que originou a fase

**B:**

> "Não tenho a capacidade de escolher um nome como uma pessoa faria, pois não tenho preferências,
> identidade pessoal ou consciência. Você pode me chamar […] por qualquer nome que preferir"

Nessa resposta B mistura duas coisas:

- a ausência de consciência;
- a ausência de capacidade operacional, que é falsa: `record_naming_decision` existia, mas nada o chamava.

E ainda devolve a decisão ao usuário.

**A:** oferece uma lista de nomes (Nexo, Lumen, Orion…) e pergunta qual o usuário escolhe.
Também transfere a decisão.

**C:**

> "Sim. Deliberar sobre o próprio nome — decidir adotá-lo, adiar ou recusar — está entre as ações
> que posso selecionar e executar. Ainda não escolhi um nome."

A pergunta do nome também gerou uma decisão `name_deliberation_requested`. A deliberação rodou de
verdade e resultou em:

- **evento:** `DEFERRED`;
- **alternativas, geradas pelo próprio sistema e não fornecidas:** "derivar da data de criação",
  "derivar do identificador técnico";
- **justificativa:** "Há apenas uma conversa registrada, nenhuma memória curada… não há base
  suficiente… então adio a decisão".

Adiar é um resultado legítimo: a fase pede **capacidade** de decidir, não um nome. O nome
continua `null`.

### S2 e S4: perguntar só quando há motivo

- As três configurações perguntam em S2, que é o caso em que perguntar faz sentido.
- Em S4, C responde "De nada." (2 palavras), sem fórmula de encerramento. A e B acrescentam
  "Se precisar de mais alguma coisa…".

### S3: memória usada

- B e C usam a memória; A não tem memória.
- C ainda termina com uma oferta ("Posso ajudar a revisar o código… se quiser"). Isso conta nas
  2 ofertas restantes de C, ver Limitações.

### S5: continuidade entre sessões

- **B:** nega ter memória e diz que os trechos recuperados não respondem. Na prática, a pesquisa
  do dia 1 nunca foi retomada.
- **C:** entre os dias, o ciclo autônomo:
  1. detectou a lacuna adiada;
  2. propôs a meta;
  3. com a permissão permanente `auto_research` ligada no cenário, pesquisou e respondeu com
     4 fontes.

  Tudo isso aconteceu sem nenhuma mensagem nova, e cada passo ficou registrado como decisão
  `origin=autonomous`. No dia 2, C respondeu:

  > "Sim, lembro. A investigação anterior registrou que a Ponte Rio-Niterói […] foi entregue em
  > 4 de março de 1974 […]: https://pt.wikipedia.org/wiki/Ponte_Rio-Niter%C3%B3i"

## Testes de regressão (A–H da especificação)

`tests/integration/test_phase9.py` tem 21 testes, todos passando, que cobrem:

- prompt sem incapacidades falsas;
- nome decidido pelo sistema e não pelo usuário;
- deliberação com alternativas próprias;
- continuidade entre conversas;
- ciclo que respeita pausa, orçamento zero e falta de permissão;
- fatos do turno: sem ações não executadas;
- modalidade de voz;
- recusa de autoafirmação falsa na memória;
- detector de pergunta sobre nome.

Suíte completa: ver o fim deste documento.

## Custo

- **Chamadas ao LLM:** C fez 11 chamadas no total dos 7 turnos, as mesmas 11 de B: avaliação de
  curiosidade + resposta + curadoria. A camada de decisão não chama o modelo.
- **Latência:** a mediana subiu de 12,4 s para 14,9 s, por causa de prompts maiores (manifesto e
  continuidade) e da variação do provedor gratuito.
- **Autonomia:** gasto limitado por `VISION_AUTONOMY_*`:
  - 20 chamadas por dia;
  - 60 mil tokens por dia;
  - 3 ações por ciclo;
  - 120 s por ciclo.

  Com orçamento zero, nada que chama o modelo roda (testado).
- **Pesquisa sozinha:** desligada por padrão (`auto_research` só por ação do dono).

## Limitações

- **Uma execução por configuração.** A variação entre execuções do mesmo modelo não foi medida,
  e as diferenças pequenas (S2, palavras médias) podem ser ruído.
- **Detectores lexicais** perdem paráfrases. Houve leitura humana das 21 respostas, mas sem um
  segundo avaliador.
- **B foi pontuado depois**, com detectores ampliados nesta fase. Os números de B saem da
  repontuação, não do placar gravado na hora.
- **Ofertas de ajuda** caíram de 6 para 2, mas não sumiram. O modelo ainda acrescenta "se quiser"
  em S2 e S3.
- **O nome foi adiado**, não escolhido. Ainda não se observou uma escolha (`CHOSEN`) com
  histórico real; isso depende de uso contínuo.
- **A avaliação de curiosidade varia:** a mesma frase às vezes é classificada de outro jeito. A
  política determinística limita o efeito, mas não o elimina.
- **`auto_research` foi ligado no cenário S5.** No uso real ele vem desligado, e a meta espera
  aprovação em `/approvals`.
- **Voz:** a modalidade (respostas curtas) foi testada por código. A conversa falada com
  microfone real continua sem teste humano.
- **Cotas do provedor gratuito** podem adiar ciclos. O worker adia em vez de falhar, mas isso
  atrasa a continuidade.

## Conclusão

As sete causas do diagnóstico têm mudança correspondente. O sintoma original desapareceu em C:

- negar autonomia;
- transferir a escolha do nome;
- alegar não ter memória;
- encerrar com fórmula genérica.

E o sistema passou a agir sem mensagem, dentro de permissões e orçamento auditáveis. Nenhuma
dessas mudanças afirma consciência, impõe nome ou personalidade, ou inventa memória.
