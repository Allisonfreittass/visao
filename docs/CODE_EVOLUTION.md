# Evolução autônoma de código

Experimento autorizado pelo proprietário: o VISÃO pode propor, testar e publicar
alterações na versão em uso sem aprovação individual de cada mudança.

## Primeiro escopo

O modelo pode editar somente `core/study/strategy.py` (consultas de pesquisa) e
`core/conversation/style.py` (clareza da expressão). São funções pequenas; um
validador fixo restringe a sintaxe, os contratos e o tamanho da mudança. Não há
acesso de edição a banco, autenticação, permissões, orçamento, identidade,
controlador, testes, dependências, workflows ou credenciais. Ampliar o escopo
exige uma alteração humana no controlador.

Isso é modificação de código versionado, não treinamento do modelo. Os testes e
os limites sintáticos não provam a qualidade semântica de toda alteração.

## Fluxo real

1. O workflow `VISÃO code evolution` roda diariamente às 14h23 UTC, ou por disparo
   manual. Precisa da variável de repositório `VISAO_CODE_ENABLED=true`.
2. O executor envia somente os dois arquivos permitidos e seus hashes para a API
   protegida do VISÃO. Não envia credenciais, conversas ou memórias.
3. O próprio backend produz uma proposta ou registra que não encontrou uma
   melhoria útil. Há uma única tentativa por dia UTC, inclusive se ela falhar.
   A chamada é registrada em `model_usage` e usa as cotas atuais de autonomia,
   tokens e dinheiro, sem orçamento extra.
4. O executor revalida o escopo e testa a proposta em um container descartável,
   sem rede, sem credenciais de produção e com limites de memória/CPU/processos.
5. Se os testes passarem e a autonomia continuar liberada, ele verifica que a
   `main` não avançou, commita como VISÃO e envia sem force push. O registro de
   motivação fica em `.visao/changes/<data>.json`.
6. Como pushes com `GITHUB_TOKEN` não disparam outro workflow automaticamente,
   o executor dispara explicitamente o CI por `workflow_dispatch`.
7. O CD publica somente o SHA da `main` testado pelo CI, após sucesso. Propostas
   de forks, PRs e SHAs antigos não entram no CD de produção.
8. O CD confere a revisão realmente carregada pela API, o banco e o frontend.
   Se falhar, solicita rollback do Worker anterior e verifica a recuperação. Para
   uma alteração autônoma, também reverte o commit se a `main` não tiver avançado.

O histórico aparece na aba Estudos. Uma proposta não é apresentada como mudança
publicada. A pausa global impede novas propostas e a publicação de uma mudança
autônoma pendente. Desativar `VISAO_CODE_ENABLED` desliga o agendamento de código.
O estudo de conteúdo continua tendo seu próprio agendamento.

## Credenciais e CD

O GitHub guarda somente `VISION_CODE_AUTONOMY_KEY` (acesso à API do executor) e
`CLOUDFLARE_API_TOKEN` (publicação). As chaves do modelo, JWT e banco permanecem no
Cloudflare. O token do GitHub é temporário e limitado a este repositório.

O token Cloudflare precisa das permissões de publicação de Workers e Containers,
limitado à conta onde está o VISÃO. Não use Global API Key nem copie uma sessão
OAuth pessoal do Wrangler para o CI. Segredos não entram no Git nem no código
fornecido ao modelo.

O CD também publica commits humanos da `main` depois do CI. Ele preserva os
segredos já configurados no Worker e informa `VISION_BUILD_SHA` para conferir o
servidor em execução. A troca de imagem verifica a imagem e o rótulo de revisão
do Container, mesmo quando ele estava ativo no momento do deploy.

A reversão automática restaura o Worker/Container, não desfaz migrações de banco.
Mudanças humanas com migrações precisam considerar compatibilidade de versões.
O escopo autônomo não inclui migrações.
