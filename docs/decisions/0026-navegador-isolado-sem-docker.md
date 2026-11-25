# ADR-0026: Navegador isolado sem Docker, na máquina do dono

- Data: 2026-11-25
- Estado: aceita

## Contexto

No servidor, o Chromium roda no container `browser` do `deploy/docker-compose.yml`, sem segredos,
sem banco e numa rede só com a API e o worker ([NAVEGADOR.md](../NAVEGADOR.md)). Se uma página
maliciosa explorar o Chromium, ela fica presa num lugar sem nada de valor. A pesquisa de execução
local ([execucao_local.md](../research/execucao_local.md)) apontou que esse é o único ganho de
segurança real do Docker, e que ele precisava de um substituto antes de o Visão rodar na máquina
do dono (etapa 6).

Na máquina, com `VISION_BROWSER_EXECUTABLE_PATH`, a API abria o Chromium ela mesma, e isso tinha
três problemas:

- **O ambiente inteiro ia junto.** O Playwright passa ao navegador o ambiente do processo que o
  abre: `VISION_SECRET_KEY`, as chaves dos modelos, o token do GitHub.
- **A pasta pessoal inteira ficava ao alcance**: o `.env`, o banco SQLite, `~/.ssh`.
- **Sem o sandbox do próprio Chromium.** O Playwright o abre com `--no-sandbox` por padrão.

## Decisão

- **O Chromium local roda dentro do sandbox que o sistema já tem**, o mesmo que o braço usa para
  rodar os testes de uma tarefa (`arm/visao_braco.py`). O código fica em
  `integrations/browser/sandbox.py`.
  - **Linux: bubblewrap**, com namespaces novos para tudo, menos a rede. Só ficam montados `/usr`,
    `/etc`, a pasta do Chromium (só leitura) e a pasta de perfil que o Playwright escolheu (a
    única gravável). `/tmp` é vazio e só dele. A pasta pessoal não existe lá dentro.
  - **macOS: sandbox-exec.** Ler a pasta pessoal é negado, exceto a pasta do Chromium e o perfil.
    Gravar, só no perfil e nas pastas temporárias.
- **Ambiente limpo sempre**, com ou sem sandbox: o navegador recebe só `PATH`, `HOME` (a pasta
  temporária) e o idioma (`LANG`, `LC_ALL`, `TZ`). Nenhuma variável `VISION_*` chega a ele.
- **Como entra no Playwright.** O Playwright abre o navegador e escolhe a pasta de perfil
  (`--user-data-dir`), então ele recebe no lugar do Chromium um pequeno script. O script roda
  `sandbox.py` com `python -I`, só com a biblioteca padrão e fora do app. O `sandbox.py` lê os
  argumentos e troca de processo (`exec`) pelo Chromium dentro do sandbox. O caminho do servidor
  (`VISION_BROWSER_WS_URL`, o container) não muda.
- **Sem sandbox, sem navegador.** Se o sistema não tiver bubblewrap, o navegador local não abre:
  cada página volta com o motivo ("falta o bubblewrap"), e nunca abre sem isolamento. Desligar é
  uma escolha explícita: `VISION_BROWSER_SANDBOX=false`. Mesmo assim, o ambiente continua limpo.

## Consequências

- Uma página que explore o Chromium na máquina do dono não acha as chaves no ambiente nem os
  arquivos da pasta pessoal. O teste `tests/unit/test_browser_sandbox.py` prova isso com o
  bubblewrap de verdade: a página abre, e um arquivo da pasta pessoal dá `ERR_FILE_NOT_FOUND`
  dentro do sandbox, enquanto o mesmo arquivo abre fora dele.
- **O sandbox do próprio Chromium continua desligado.** Dentro do bubblewrap ele não consegue
  criar um segundo namespace ("No usable sandbox"). A parede é o bubblewrap, como no servidor é
  o container (a imagem do Playwright também roda sem o sandbox do Chromium).
- **Limite aceito: a rede é compartilhada.** O navegador precisa da internet para ler páginas,
  então os serviços em `127.0.0.1` da máquina (a própria API, por exemplo) são alcançáveis lá de
  dentro. O filtro de requisições (só HTTPS e só endereços públicos) continua valendo para tudo
  o que a página pede, mas um Chromium já explorado poderia contorná-lo. A API exige login. Um
  namespace de rede só com saída para a internet pediria uma ferramenta a mais (`slirp4netns` ou
  `pasta`) e fica para depois.
- **O sandbox-exec não foi testado num Mac de verdade**, só o perfil gerado. Antes de contar com
  ele, vale abrir uma página no Mac com o navegador local ligado.
- No Linux, o bubblewrap passa a ser necessário para ter páginas ao vivo na máquina
  (`apt install bubblewrap`). O servidor não precisa dele.
