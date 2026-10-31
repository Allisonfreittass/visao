# VISÃO na nuvem

O frontend fica em Workers Assets. A API Python roda em um Container, acessado
por um único Durable Object (`primary`). Memórias, identidade, conversas, estudos,
consumo e fila ficam no PostgreSQL, no schema privado `visao` do Supabase.
O disco do Container é temporário e nunca deve guardar o banco.

## Agendamento e limites

O Cron do Cloudflare verifica trabalho a cada 15 minutos, mesmo sem navegador
aberto. A API agenda o ciclo cognitivo por hora e executa no máximo dois jobs por
verificação. Usa as permissões, pausa, limites de custo e leases do worker local.
Rodadas novas de estudo continuam sujeitas ao intervalo de seis horas e às cotas
diárias. Uma pesquisa inconclusiva por falta de fontes ou de resposta nos trechos
pode ter uma única retomada, uma hora após terminar. A retomada preserva a pergunta,
fica vinculada à tentativa anterior e deve usar consultas diferentes. Ela usa as
mesmas cotas de buscas, chamadas, tokens e custo; não ganha orçamento adicional.
Uma retomada também inconclusiva não dispara outra retomada em uma hora.
Uma verificação pode terminar sem produzir um estudo novo: cooldown, orçamento,
pausa ou falta de evidência são resultados possíveis.

A aba Estudos mostra a última verificação concluída pelo agendamento. A flag
`cloud_scheduler` registra horário UTC, resultado e estados dos jobs. Falhas de
inicialização anteriores à API aparecem nos logs do Worker/Container.

O Container pode dormir após dois minutos sem requisições. A primeira chamada
seguinte demora mais enquanto ele inicia. Esta implantação inclui texto e
estudos; modelos locais de voz não estão incluídos. Visitas frequentes à interface
mantêm o Container ativo e aumentam o consumo. Workers, Containers e provedor de
modelo têm cobranças próprias; o plano base não representa um teto de custo.

## Publicação

Requer Docker com build linux/amd64, Node 22+, Workers Paid e PostgreSQL.

1. `npm --prefix apps/web ci` e `npm --prefix apps/web run build`.
2. `npm --prefix infrastructure/cloudflare ci`.
3. Configure segredos em um JSON privado fora do Git. Inclua
   `VISION_DATABASE_URL` (SQLAlchemy psycopg, TLS), `VISION_SECRET_KEY`,
   `VISION_CLOUD_TICK_KEY` (32+ caracteres), credenciais dos modelos e seus limites.
   Preserve `VISION_SECRET_KEY` e os hashes de senha durante uma transferência.
4. Na pasta `infrastructure/cloudflare`, execute
   `npm run deploy -- --secrets-file /caminho/privado/segredos.json`.

As variáveis públicas ficam em `wrangler.jsonc`. A conexão deve usar o login
dedicado ao backend e `VISION_DATABASE_SCHEMA=visao`. As migrações executam na
inicialização. O schema não concede acesso a anon/authenticated, e as tabelas
habilitam RLS. O backend continua responsável pelo isolamento entre usuários com
a autenticação própria do VISÃO. Não publique chaves de banco na interface.

As rotas `/internal/*` e `/api/internal/*` são bloqueadas no Worker público.
O Cron invoca o Durable Object diretamente com um segredo separado dos tokens
dos usuários. O Worker limita tentativas de login antes de iniciar o Container.

## Transferência inicial e recuperação

Pare API e worker locais antes de criar o snapshot SQLite consistente. Guarde o
snapshot com permissões restritas, fora do Git. O comando abaixo migra apenas
para um schema vazio e verifica contagens; qualquer falha reverte a cópia inteira:

```sh
python -m infrastructure.deployment.copy_state \
  --source-snapshot /caminho/privado/snapshot.sqlite \
  --credentials-file /caminho/privado/credenciais.json
```

O arquivo de credenciais contém a chave `url`. Use `--check-only` para conferir a
compatibilidade sem inserir dados. Não execute esse utilitário sobre produção
já populada. Não mantenha o worker local ativo em paralelo à nuvem.

Após publicar, confira `/api/ready`, login, memórias e a aba Estudos. A rota de
estudos sem login deve retornar 401; rotas internas públicas devem retornar 404.
Confirme pelo menos uma verificação automática pelo horário na aba Estudos ou
pela flag no banco. Para pausar os estudos, use os controles de autonomia da
interface. Preserve o banco ao reverter uma versão do Worker e verifique a
compatibilidade das migrações antes de reverter código.

Mantenha backups do PostgreSQL conforme a retenção contratada no Supabase. O
snapshot local da transferência é uma cópia histórica, não um backup contínuo.

## CI, CD e evolução

O workflow `CD Cloudflare` publica automaticamente a revisão da `main` aprovada
pelo CI. O experimento de alterações autônomas usa esse mesmo caminho. Consulte
[CODE_EVOLUTION.md](CODE_EVOLUTION.md) para escopo, credenciais, limites e rollback.
