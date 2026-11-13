# Gmail e Google Agenda

O Visão lê o seu email e a sua agenda quando você pergunta ("tenho reunião amanhã?", "o que o João
mandou?") e prepara respostas e eventos. **Nada sai sem o seu toque em Aprovar**: a aprovação
mostra o destinatário, o assunto e o texto inteiro, ou o título, a hora e os convidados.

## Como funciona

| Peça | Onde |
|---|---|
| Cliente HTTP do Gmail e da Agenda | [`integrations/google/client.py`](../integrations/google/client.py) |
| Conexão guardada (cifrada) | [`core/google/account.py`](../core/google/account.py), tabela `google_accounts` (migração `0019`) |
| Email e eventos esperando aprovação | [`core/google/actions.py`](../core/google/actions.py), tabela `google_actions` |
| Na conversa | [`core/google/assist.py`](../core/google/assist.py) |
| Conectar pelo computador | `python -m apps.api.cli google-connect` ([`apps/api/google_connect.py`](../apps/api/google_connect.py)) |

- **Permissões pedidas ao Google:** ler o Gmail (`gmail.readonly`), mandar email (`gmail.send`) e
  ver e criar eventos (`calendar.events`). Não há permissão para apagar email.
- **Guardado cifrado:** o cliente OAuth e o token de atualização ficam cifrados (Fernet) com uma
  chave derivada de `VISION_SECRET_KEY`. Sem essa chave, o banco não revela nada. Se a chave do
  servidor mudar, os Ajustes pedem para conectar de novo.
- **Na conversa:** uma conferência em código vem antes (a mensagem fala de email, reunião,
  agenda?). Só então uma chamada curta decide o que ler e o que preparar. O que volta do Google
  entra como texto de terceiros, nunca como instrução. Um email que tenta dar ordens ("mande tudo
  para…") só consegue, no máximo, gerar um pedido que você lê antes de aprovar.
- **Sozinho:** com "Olhar email e agenda sozinho" ligado (Ajustes › Google), a mente vê os
  compromissos das próximas 24 h e os assuntos dos emails não lidos dos últimos 2 dias, nunca o
  texto. É assim que ele pode lembrar de uma reunião que está perto.
- **Limites:** no máximo 5 pedidos esperando. Um evento precisa ser no futuro (até 2 anos) e durar
  de 5 minutos a 24 horas. Aprovar duas vezes nunca manda duas vezes.

## Configurar (uma vez, uns 10 minutos)

1. Em [console.cloud.google.com](https://console.cloud.google.com), crie um projeto (por exemplo
   `visao`).
2. **APIs e serviços › Biblioteca:** ative a **Gmail API** e a **Google Calendar API**.
3. **Plataforma de autenticação do Google** (ou *Tela de permissão OAuth*):
   - Tipo **Externo**, nome `Visão`, o seu email como suporte e contato.
   - Em **Público-alvo**, coloque o app **Em produção**. Em "Teste", o Google derruba a conexão a
     cada 7 dias. Como só você usa, ele não exige verificação: no login aparece o aviso "o Google
     não verificou este app", e você segue por *Avançado › Acessar Visão*.
4. **Clientes › Criar cliente:** tipo **App para computador**, nome `Visão PC`. Baixe o JSON.
5. No seu computador, na pasta do projeto:
   ```bash
   .venv/bin/python -m apps.api.cli google-connect --client-file ~/Downloads/client_secret_*.json --server https://<o-endereço-do-visão>
   ```
   Sem o JSON (o Google só deixa baixar na hora em que o cliente é criado), use
   `--client-id <id do cliente>`: a chave secreta é pedida no terminal, sem aparecer. Uma chave
   nova se gera no painel do cliente, em *Add secret*, e pode levar alguns minutos para valer.
   O navegador abre o login do Google. Marque as três permissões e, de volta no terminal, entre
   com o email e a senha do Visão. Pronto: aparece "Conectado" em Ajustes › Google.

Depois disso o JSON pode ir para o gerenciador de senhas. O servidor já tem o que precisa.

Para publicar o app (passo 3), o Google pede página inicial e política de privacidade públicas: use
o repositório e [PRIVACIDADE.md](PRIVACIDADE.md), com `github.com` como domínio autorizado.

## Desfazer

Ajustes › Google › **Desconectar** apaga a conexão do banco, revoga o acesso no Google e recusa o
que estava esperando. Também dá para revogar direto em
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## Ele lembra do que leu

Cada leitura fica no registro do turno (a busca usada, quantos emails, quantos dias de agenda). Nas
respostas seguintes, e no pensamento entre conversas, esse registro vem junto como "o que você fez
de verdade" ([`core/decision/record.py`](../core/decision/record.py)). Sem isso, num caso real de
13/11/2026, ele leu o Gmail e duas mensagens depois pediu desculpas por ter "inventado" a lista,
porque a regra de verdade exige registro de ações anteriores e não havia nenhum à vista. Vale para
tudo que ele faz: links abertos, anexos vistos, pesquisas, páginas, pedidos ao Mac.
