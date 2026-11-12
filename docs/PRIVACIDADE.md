# Política de privacidade do Visão

O Visão é um assistente pessoal de código aberto que roda no servidor do próprio dono e atende
uma única pessoa: quem o instalou. Não há outros usuários, anúncios nem venda de dados.

## O que ele acessa no Google

Só depois que o dono conecta a própria conta Google, e só nessa conta:

- **Gmail:** ler emails para responder às perguntas do dono e mandar emails que ele aprovou um a
  um. O Visão não apaga emails.
- **Google Agenda:** ver eventos e criar eventos que o dono aprovou um a um.

## Como os dados são usados

- Apenas para atender o dono: responder o que ele pergunta, lembrar de compromissos e preparar
  emails e eventos que só são enviados ou criados depois da aprovação dele.
- Trechos lidos podem ser enviados ao modelo de linguagem que gera as respostas (configurado pelo
  dono, hoje a API da Anthropic), apenas para produzir aquela resposta.
- Nada é compartilhado com terceiros para outros fins, vendido ou usado para publicidade, nem
  para treinar modelos.
- O uso de dados recebidos das APIs do Google segue a
  [Política de dados do usuário dos serviços de API do Google](https://developers.google.com/terms/api-services-user-data-policy),
  incluindo os requisitos de uso limitado.

## Como os dados são guardados

- A autorização do Google fica cifrada no banco de dados do dono.
- O conteúdo dos emails não é guardado; só o que aparece na conversa com o dono, que ele pode
  apagar.

## Como desfazer

- No app: Ajustes › Google › Desconectar. A autorização é apagada e revogada no Google.
- Na conta Google: [myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Contato

Pelas issues do repositório: [github.com/Allisonfreittass/visao](https://github.com/Allisonfreittass/visao).
