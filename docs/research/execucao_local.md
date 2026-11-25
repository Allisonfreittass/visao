# Rodar o Visão na máquina do dono: Docker, "npm" e performance

Data: 25/11/2026. Base: `main` em `599b85a`. Pergunta do dono: o Visão roda em Docker; passar para
"npm" não seria melhor, como fazem os agentes em que ele se baseou, já que um dia ele vai rodar
local?

**Método:**
- Três pesquisas em paralelo: como o Visão roda hoje (lendo o código), como os agentes de
  referência são instalados (documentação oficial) e números de performance para uma máquina
  local (fontes no fim).
- As duas afirmações em que a recomendação mais se apoia foram conferidas de novo nas fontes:
  como o OpenClaw e o Hermes instalam e mantêm o serviço ligado.
- A memória da API e do worker foi medida aqui. O resto dos números vem de outro hardware e está
  marcado.

## Resposta curta

- **"npm" não é o caminho, mas a ideia por trás dele é.** O OpenClaw se instala com `npm` porque é
  escrito em Node. O Visão é Python. O equivalente direto é o que o **Hermes** faz, e ele também é
  Python: um script que instala o `uv`, põe o comando no PATH e registra um serviço no sistema.
  Reescrever o Visão em Node não traria ganho e jogaria fora o que funciona.
- **Docker fica só para o servidor na nuvem** (Lightsail hoje, Oracle depois). Nenhum dos cinco
  agentes usa Docker como instalação principal na máquina do usuário. Num Mac de 8 GB, o Docker
  Desktop reserva por padrão até metade da RAM (4 GB) só para a máquina virtual dele.
- **O Visão já roda sem Docker** em desenvolvimento (`make setup` e `make start`, com SQLite). O
  que falta para virar "instalação local" é pouco e está listado na seção 5.

## 1. Como os agentes de referência fazem

| Agente | Linguagem | Instalação recomendada | Fica ligado como | Dados | Docker |
|---|---|---|---|---|---|
| OpenClaw | Node | `npm i -g openclaw` ou script curl; app de Mac | serviço do launchd (Mac) ou do systemd (Linux), com `openclaw gateway install` | SQLite e arquivos Markdown | opcional, para servidor e para isolar comandos (desligado por padrão) |
| Hermes (Nous) | **Python** | script curl que instala o `uv`, o Python e um Chrome for Testing | serviço do launchd ou do systemd, com `hermes gateway install` | SQLite (FTS5) e Markdown | opcional, para isolar o terminal |
| Goose (Block) | Rust | Homebrew, zip, app desktop (Electron) | enquanto o app está aberto | SQLite | não |
| OpenCode | TypeScript (Bun) | Homebrew, script curl, npm | um servidor por usuário, aberto pelo cliente | SQLite | só como imagem pronta |
| Grok Build (xAI) | não documentado | script curl | não tem serviço | `~/.grok/` | não documentado |

**O padrão que domina:**
- Um script de instalação (curl, ou Homebrew/npm como alternativa) põe um comando no PATH do
  usuário.
- Um servidor local, só em `127.0.0.1`, serve a API e a interface web.
- Quem precisa ficar ligado o tempo todo (OpenClaw e Hermes) se registra como serviço do sistema.
- Os dados ficam em SQLite e arquivos numa pasta do usuário (`~/.<nome>/`).
- Ninguém usa Postgres por padrão.
- Para o navegador, ou o agente baixa um Chromium fixo, ou usa o Chrome do usuário.

## 2. Como o Visão roda hoje

No servidor (`deploy/docker-compose.yml`), num Lightsail de 2 GB:

| Peça | O que faz |
|---|---|
| `api` | FastAPI (uvicorn, um processo), sem voz instalada |
| `worker` | o processo que fica ligado 24 h: pensa a cada 20 min, ciclo de autonomia a cada 60 min, estudo a cada 6 h, painéis |
| `browser` | servidor do Playwright com Chromium, numa rede separada, sem segredos, até 700 MB |
| `caddy` | HTTPS, serve o site (build estático) e encaminha `/api` para a API |
| banco | Supabase (Postgres externo), não é container |

**O que o Docker dá hoje:**
- **Isolamento do navegador.** Se uma página maliciosa escapar do Chromium, ela fica presa num
  container sem segredos e sem banco (`docs/NAVEGADOR.md`). É o único ganho de segurança real, e
  é o que precisa de substituto no local.
- **Build reproduzível.**
- **Deploy com volta automática** se a versão nova não responde.

**Na máquina, hoje, sem Docker:**
- `make start` sobe a API, o worker e o Vite, com SQLite (`dev.db`).
- O `pgvector` está instalado no Postgres mas **não é usado por nenhum código**: a busca de
  memória é por palavras. Então não há motivo para levar Postgres para a máquina local.
- No SQLite, a única perda é a trava entre processos: o lock por conversa que o Postgres dá entre
  a API e o worker (`core/conversation/turn_lock.py`).
- O braço do Mac já é o modelo de instalação local que dá certo: um arquivo Python que usa só a
  biblioteca padrão e um `launchd` com `KeepAlive` (`arm/instalar-mac.sh`), sem portas abertas.

## 3. Quanto pesa cada peça

**Medido aqui (Linux, Python 3.12):**

| Peça | RAM | Disco | Carrega em |
|---|---|---|---|
| API | 140 a 150 MB | | cerca de 3 s |
| Worker | 120 MB | | cerca de 5 s |
| Chromium completo | | 408 MB | |
| Chromium só headless | | 277 MB | |
| Ambiente Python (`.venv`) | | 361 MB | |

**De outras fontes ou de medições antigas do projeto:**

| Peça | RAM | Fonte |
|---|---|---|
| Kokoro (voz própria, fp32) | 870 a 900 MB | medido num M1 de 8 GB em `docs/research-log/2026-10-31-fase-2b-tts.md` |
| Piper (voz mais leve) | cerca de 350 MB | mesma medição |
| faster-whisper `base` (ouvir) | cerca de 500 MB | ADR-0005 |
| Chromium headless, no pico | cerca de 700 MB | datawookie, 2025 |
| qwen3:4b no Ollama | cerca de 2,5 GB | biblioteca do Ollama |

**Conta para um Mac de 8 GB.** É uma estimativa, a medir no próprio Mac:

| O que | Memória |
|---|---|
| macOS e um navegador | 3 a 4 GB |
| Visão (API e worker juntos) | cerca de 0,3 GB |
| Chromium, enquanto lê uma página | cerca de 0,7 GB |
| Kokoro, enquanto fala | cerca de 0,9 GB |
| qwen3:4b, se ligado | cerca de 3 GB |

Tudo ao mesmo tempo não cabe. Cabe se o navegador, a voz e o modelo local **carregarem só quando
usados e saírem da memória depois**.

## 4. O que melhora a performance, por ordem de impacto

1. **Nada de Docker no Mac.** Os processos nativos economizam a máquina virtual inteira (até 4 GB
   reservados no Docker Desktop, que leva 3 a 10 s para acordar depois de 5 min parada).
2. **Um processo só, em vez de dois.** O worker é um laço simples (`while` com `time.sleep`, em
   `apps/worker/main.py`). Ele pode rodar numa thread dentro do processo da API, ligado no
   arranque. Economiza um interpretador inteiro (cerca de 120 MB), o modelo de voz não carrega
   duas vezes, e a trava entre processos que o SQLite não tem deixa de fazer falta.
3. **Configurar o SQLite.** Hoje `infrastructure/database/session.py` não liga nada. Faltam:
   - `journal_mode=WAL`, para quem lê não esperar quem escreve;
   - `busy_timeout=5000`, para esperar a trava em vez de falhar com "database is locked";
   - `synchronous=NORMAL`;
   - `foreign_keys=ON`.

   É uma mudança pequena, e vale até no desenvolvimento de hoje.
4. **Navegador só quando precisa:**
   - um Chromium headless (instalado com `playwright install --only-shell`, 277 MB), aberto na
     primeira leitura e fechado depois de alguns minutos parado;
   - uma aba nova (contexto) por tarefa, nunca um navegador por tarefa.
5. **Voz só quando precisa.** Carregar o Kokoro e o modelo de ouvir na primeira fala e descarregar
   depois de um tempo parado. No Mac com chip Apple, o `faster-whisper` não usa a GPU. O
   `mlx-whisper` e o `whisper.cpp` com Core ML são de 5 a 7 vezes mais rápidos num clipe curto. A
   qualidade em português precisa ser testada antes de trocar.
6. **Modelo local sob demanda.** O Haiku na nuvem continua sendo o padrão. O modelo do Mac (1,7B a
   4B) só quando pedido, com `keep_alive` curto. Nunca junto com o navegador e a voz.
7. **Um endereço só.** A API passa a servir o site (o `dist` do Vite) em `127.0.0.1`. Na máquina
   local, não precisa de Caddy nem de Node rodando.

## 5. O que fazer, em etapas

| Etapa | O que | Tamanho |
|---|---|---|
| 1 | Configurar o SQLite (item 3 acima). **Feito** (#15) | pequeno; vale já |
| 2 | Worker como thread da API, com uma opção para continuar separado no servidor. **Feito** (`VISION_WORKER_IN_API`): 149 MB num processo, contra 269 MB em dois, medido aqui | médio |
| 3 | API servindo o site e um comando `visao` (iniciar, parar, estado). **Feito** (`VISION_WEB_DIR`, `apps/visao_cli.py`) | médio |
| 4 | Navegador e voz carregados sob demanda e descarregados depois de parados. **Feito**: a voz sai da memória depois de 10 min sem uso (`VISION_VOICE_IDLE_MINUTES`); o navegador já abria e fechava a cada leitura | médio |
| 5 | Instalador nos moldes do Hermes e do braço: um script que instala o `uv`, o Visão em `~/.visao` e um serviço do launchd (Mac) ou do systemd do usuário (Linux). **Feito** (`scripts/instalar.sh`, `visao servico`, [INSTALAR.md](../INSTALAR.md)): 21 s numa máquina com o cache do uv, testado aqui com o systemd de verdade | médio |
| 6 | Isolar o navegador sem Docker: o Chromium como processo separado, sem as chaves no ambiente, dentro do `sandbox-exec` no Mac e do `bubblewrap` no Linux, que o braço já usa. **Feito** ([ADR-0026](../decisions/0026-navegador-isolado-sem-docker.md), `VISION_BROWSER_SANDBOX`): testado aqui com o bubblewrap de verdade; o sandbox-exec ainda não num Mac | médio, pede ADR |
| 7 | Mais tarde, se quiser um app de Mac: o servidor congelado (PyInstaller no modo pasta, não arquivo único) dentro de um app Tauri. Pede assinatura da Apple (US$ 99 por ano). **Feito** ([APP_MAC.md](../APP_MAC.md), [ADR-0027](../decisions/0027-app-de-mac.md)): 120 MB, montado e testado no CI num Mac; sem a assinatura paga, sem voz e sem navegador ao vivo nesta versão | grande |

As etapas 1 a 4 também deixam o servidor na nuvem mais leve. Elas valem para a migração para a
Oracle, que tem prazo (o acesso à AWS acaba em 22/04/2027).

## 6. O que não fazer

- **Reescrever em Node para instalar com npm.** O ganho é só a forma de instalar, e o `uv` dá o
  mesmo em Python.
- **Docker Desktop como forma de rodar no Mac de 8 GB.**
- **Levar Postgres para a máquina local.** Nada usa o `pgvector`. Quando vier a busca por sentido,
  o `sqlite-vec` resolve nessa escala (10 mil vetores em cerca de 3,6 ms), mas ele ainda não
  chegou à versão 1.
- **Usar o perfil do Chrome do dono como navegador do Visão.** Desde o Chrome 136, a depuração
  remota não funciona no perfil padrão. Além disso, misturaria as contas logadas do dono com
  páginas que o Visão abre sozinho.
- **PyInstaller em arquivo único** para um servidor: ele descompacta a cada início e, dentro de um
  app, deixa o servidor órfão quando o app fecha.

## 7. Limites deste estudo

- Os números de RAM do navegador, da voz e do modelo local vêm de outras máquinas. Antes da
  etapa 5, vale medir tudo no Mac de 8 GB.
- A memória da API e do worker foi medida só carregando o código, sem conversa nem tarefa rodando.
- Nada dos agentes de referência foi instalado ou executado: tudo vem da documentação oficial.
- O custo de memória do OrbStack e do Colima (alternativas ao Docker Desktop) só aparece em blogs,
  e eles discordam entre si.

## Fontes

- OpenClaw: [instalação](https://docs.openclaw.ai/install), [gateway](https://docs.openclaw.ai/gateway), [app de Mac](https://docs.openclaw.ai/platforms/mac/bundled-gateway), [Docker](https://docs.openclaw.ai/install/docker), [memória](https://docs.openclaw.ai/concepts/memory), [navegador](https://docs.openclaw.ai/tools/browser)
- Hermes: [instalação](https://hermes-agent.nousresearch.com/docs/getting-started/installation), [Nix e serviço](https://hermes-agent.nousresearch.com/docs/getting-started/nix-setup), [arquitetura](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture), [memória](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory), [segurança](https://hermes-agent.nousresearch.com/docs/user-guide/security), [navegador](https://hermes-agent.nousresearch.com/docs/user-guide/features/browser)
- Goose: [instalação](https://goose-docs.ai/docs/getting-started/installation), [arquitetura](https://goose-docs.ai/docs/goose-architecture/), [sessões](https://goose-docs.ai/docs/guides/sessions/session-management), [permissões](https://goose-docs.ai/docs/guides/goose-permissions)
- OpenCode: [docs](https://opencode.ai/docs/), [CLI](https://opencode.ai/docs/cli/), [servidor](https://opencode.ai/docs/server/), [permissões](https://opencode.ai/docs/permissions/)
- Grok Build: [visão geral](https://docs.x.ai/build/overview)
- Docker Desktop: [ajustes de memória](https://docs.docker.com/desktop/settings-and-maintenance/settings/), [Resource Saver](https://docs.docker.com/desktop/use-desktop/resource-saver)
- SQLite e vetores: [sqlite-vec](https://github.com/asg017/sqlite-vec), [benchmarks](https://coderdayton.github.io/SimpleVecDB/benchmarks)
- Empacotar Python: [como entregar um app Python](https://pydevtools.com/handbook/explanation/how-do-i-ship-a-python-application-to-end-users/), [o lançador não é o processo](https://timetobuildbob.github.io/blog/the-launcher-is-not-the-process/), [python-build-standalone](https://docs.astral.sh/python-build-standalone/)
- Navegador: [peso do Playwright](https://datawookie.dev/blog/2025/06/playwright-browser-footprint/), [navegadores do Playwright](https://playwright.dev/docs/browsers), [Chrome 136 e depuração remota](https://developer.chrome.com/blog/remote-debugging-port)
- Voz: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [whisper.cpp](https://github.com/ggml-org/whisper.cpp), [comparação no Mac](https://github.com/anvanvan/mac-whisper-speedtest), [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)
- Modelo local: [qwen3 no Ollama](https://ollama.com/library/qwen3), [MLX no Ollama](https://ollama.com/blog/mlx-apple-silicon), [keep_alive](https://docs.ollama.com/faq)
