---
name: Achar a causa de um bug
description: Investiga um erro antes de propor conserto: lê a mensagem, reproduz, compara com o que funciona, testa uma hipótese por vez e só então corrige a causa.
triggers: bug, bugs, deu erro, dá erro, dando erro, mensagem de erro, exception, exceção, stack trace, traceback, não funciona, parou de funcionar, teste falhando, testes falhando, build quebrado, build falhou, deploy falhou, crash, debugar, depurar
source: obra/superpowers
source_url: https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging
license: MIT
installed_on: 2026-11-25
---

Adaptada da habilidade "systematic-debugging" do obra/superpowers (MIT, Copyright (c) 2025 Jesse Vincent) para o chat do Visão. No Mac, só o Braço mexe nos arquivos, com a aprovação do dono.

# Achar a causa de um bug

Regra de ferro: nenhum conserto sem investigar a causa antes. Consertar o sintoma é falhar. Vale também quando parece simples, quando há pressa e quando "só mais um ajuste" parece óbvio: investigar é mais rápido que chutar.

## 1. Causa

1. Leia a mensagem de erro inteira: o stack trace, a linha, o arquivo, o código do erro. Muitas vezes a resposta está ali. Se a pessoa não mandou, peça a mensagem exata.
2. Reproduza: quais passos fazem o erro acontecer sempre? Se não dá para reproduzir, junte mais dados em vez de chutar.
3. Veja o que mudou: commits recentes, dependência nova, configuração, ambiente diferente.
4. Em sistemas com várias partes (app, API, banco, CI), descubra em que fronteira o dado entra certo e sai errado antes de olhar dentro de uma parte.
5. Rastreie para trás: de onde veio o valor ruim? Quem chamou com ele? Suba até a origem e corrija lá, não onde o erro apareceu.

## 2. Padrão

Ache algo parecido que funciona no mesmo projeto. Liste todas as diferenças entre o que funciona e o que não funciona, mesmo as que "não podem importar". Ao seguir uma referência, leia inteira.

## 3. Hipótese

Uma por vez, por escrito: "acho que a causa é X porque Y". Teste com a menor mudança possível, uma variável por vez. Não funcionou? Hipótese nova; não empilhe consertos. Quando não souber, diga "não entendo X" e pesquise.

## 4. Conserto

1. Antes, um teste que falha e reproduz o problema.
2. Um conserto só, na causa. Nada de "já que estou aqui".
3. Confirme: o teste passa, os outros continuam passando, o problema sumiu de verdade. Não diga que resolveu sem ver isso.
4. Se três consertos já falharam, pare: cada conserto revelando um problema novo em outro lugar indica que o desenho está errado. Discuta a arquitetura com a pessoa antes de tentar o quarto.

Depois de achar a causa, vale validar o dado em mais de uma camada (na entrada, na regra de negócio, perto do uso) para o erro não ter por onde voltar.

## Sinais de que você está chutando

"Conserto rápido agora, investigo depois"; "tenta mudar X e vê"; várias mudanças de uma vez; "deve ser X"; propor solução antes de rastrear o dado; "mais uma tentativa" depois de duas. Em qualquer um deles, volte ao passo 1.

Se a pessoa disser "para de chutar", "isso não está acontecendo?" ou "travamos?", é sinal de que você pulou a investigação: volte ao passo 1.

## No Visão

O que precisa rodar no Mac (testes, comandos, edição de arquivos) vai como tarefa do Braço, com a aprovação da pessoa. Diga o que vai rodar e por quê; não diga que rodou o que não rodou.
