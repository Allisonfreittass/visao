# ADR-0027: O app de Mac, com o servidor dentro, e a primeira conta numa tela

- Data: 2026-11-25
- Estado: aceita
- Etapa 7 de [research/execucao_local.md](../research/execucao_local.md)

## Contexto

As etapas 1 a 5 deixaram o Visão rodando na máquina do dono com um comando (`visao iniciar`),
um instalador e um serviço do sistema. Faltava o jeito de app: um ícone no Dock, uma janela, nada
de terminal. A pesquisa apontava o servidor congelado dentro de um app Tauri, como o OpenClaw faz
com o app de Mac dele.

Três escolhas eram do dono, e ele escolheu em 25/11/2026:

- **O app leva o servidor dentro**, em vez de ser só uma janela por cima do Visão instalado. Uma
  janela só seria quase o mesmo que "Adicionar ao Dock" do Safari em http://127.0.0.1:8000.
- **A primeira conta é criada numa tela do app**, em vez de um comando no Terminal.
- **Sem a assinatura paga da Apple por ora** (US$ 99 por ano).

## Decisão

- **O servidor é o próprio comando `visao`, congelado pelo PyInstaller no modo pasta**
  (`desktop/visao-servidor.spec`).
  - Não em arquivo único: um arquivo único se descompacta numa pasta temporária a cada início, o
    que é lento, e o macOS confere cada arquivo descompactado de novo.
  - Vão junto o build do web, as migrações e o `.env.example`. Vão também o README, os docs e o
    código-fonte, que o autoconhecimento lê (`core/identity/self_knowledge.py`).
  - Ficam de fora nesta versão a voz (os extras `tts` e `stt`, cerca de 2 GB) e o driver do
    Playwright (o navegador ao vivo). Os dois continuam no jeito instalado.
  - O pacote tem 120 MB.
- **Congelado, o `visao` guarda a configuração fora do app.** O `.env` fica em `~/.visao/.env` e é
  criado na primeira abertura, com uma chave secreta nova e o banco em `~/.visao/dados/visao.db`.
  É a mesma pasta do instalador e do serviço. O código do app fica só para leitura.
- **O app (Tauri, `desktop/app/`) faz pouco:**
  - abre uma janela com uma página de espera;
  - se já há um Visão respondendo na porta 8000 (o serviço da etapa 5, ou um `visao iniciar` no
    Terminal), só abre a janela nele e não o desliga ao fechar;
  - senão, sobe o servidor que leva dentro (`visao-servidor iniciar --porta 8000`, ou outra porta
    livre se a 8000 estiver ocupada por outra coisa) e espera ele responder;
  - mostra o web app na janela;
  - ao fechar, pede para o servidor parar (SIGTERM) e espera até 25 s antes de forçar.
- **A primeira conta numa tela.** Duas rotas novas: `GET /auth/first-run` diz se a tela vale, e
  `POST /auth/first-run` cria a conta e faz a gênese numa chamada só. Valem só com três travas
  juntas:
  - a opção `VISION_FIRST_RUN_SETUP`, desligada por padrão; só o `visao` local (com SQLite) e o
    app a ligam, e a borda da Cloudflare nunca a repassa;
  - um pedido da própria máquina (127.0.0.1 ou ::1), sem cabeçalho de proxy (`X-Forwarded-For`,
    `Forwarded`, `X-Real-IP`, `CF-Connecting-IP`);
  - nenhum usuário no banco. Depois da primeira conta a tela some: as rotas respondem 404 e não
    criam uma segunda.

  A senha segue a mesma regra do terminal (12 caracteres ou mais), e o registro de auditoria diz
  `via: first_run`.
- **Sem assinatura paga.** O app sai só com a assinatura ad-hoc (`signingIdentity: "-"`). Num Mac,
  ele abre na primeira vez depois de tirar a quarentena (`xattr -dr com.apple.quarantine`) ou com
  botão direito > Abrir. Assinar e notarizar depois não pede mudar nada além do CI.
- **O build é do CI**, num Mac com Apple Silicon (`.github/workflows/desktop.yml`, roteiro em
  `desktop/construir.sh`). Ele não só monta o app: abre o app com uma pasta pessoal vazia, confere
  que o servidor de dentro subiu e respondeu, e fecha o app conferindo que o servidor parou junto.
  O app sai como artefato da execução (`Visao-mac`).

## Consequências

- Um Mac sem Python, Node ou Docker abre o Visão com dois cliques. O mesmo `~/.visao` serve o app,
  o comando e o serviço: dá para trocar de um para o outro sem perder nada.
- **Só Apple Silicon por enquanto.** Um Mac Intel precisaria de outro build (outro runner do CI,
  ou um Python universal2 para o PyInstaller).
- **Sem voz e sem navegador ao vivo no app** nesta versão. A ligação por voz e as cotações ao vivo
  continuam no Visão instalado pelo script.
- **Fechar o app desliga o Visão que ele abriu**, e com ele o worker (pensar, estudar, painéis).
  Para ele ficar ligado o tempo todo, o caminho continua sendo o serviço (`visao servico
  instalar`). Com o serviço instalado, o app vira só a janela.
- **Forçar o encerramento** (Forçar Encerrar, `kill -9`) deixa o servidor rodando. Na próxima
  abertura, o app o encontra respondendo e só abre a janela nele.
- **O microfone na janela não foi testado num Mac.** O `Info.plist` traz a frase que o macOS mostra
  ao pedir o microfone, mas a voz nem vem no app ainda.
- **A rota de primeiro uso é backend novo.** O risco é alguém de fora criar a primeira conta antes
  do dono. Ele fica fechado pelas três travas, e a de "nenhum usuário" vale para sempre depois do
  primeiro uso.
