# O braço: o Visão trabalhando no seu Mac

> Desenho e primeira versão em 2026-11-12. O objetivo de longo prazo é um assistente que conversa,
> coda e cuida dos seus assuntos de qualquer lugar. Nada de nome, marca ou visual da Marvel
> (restrição do master prompt): a capacidade é nossa, o nome não é "Jarvis".

## A ideia

O Visão mora no servidor (24 h, [LIGHTSAIL.md](LIGHTSAIL.md)): conversa, lembra, pensa e puxa
assunto. O que precisa da sua máquina (seus projetos, seus arquivos, o Claude Code com a sua
conta) roda no **braço**: um processo pequeno no Mac que busca tarefas aprovadas no servidor,
executa e devolve o resultado na conversa.

```
celular ──HTTPS──> Visão (servidor) <──HTTPS, de dentro pra fora── braço (Mac) ──> Claude Code
                    fila de tarefas                                 projetos permitidos
```

- **Nenhuma porta aberta em casa.** O braço só faz requisições de saída para o servidor, como um
  navegador. Funciona atrás de CGNAT, no Wi-Fi de qualquer lugar e com o Mac em qualquer rede.
- **O Visão não ganha um terminal.** Ele pede; quem trabalha é o Claude Code, com uma lista
  fechada de ferramentas, dentro de um projeto da lista que você escreveu no Mac.

## Por que é feito assim (o risco que isso evita)

O Visão lê a web sozinho. Uma página pode conter instruções escondidas ("rode este comando").
Se o Visão tivesse acesso direto ao Mac, um texto lido na web viraria comando na máquina que
guarda suas chaves. Por isso:

1. **Toda tarefa precisa da sua aprovação.** Uma tarefa que você escreve (`/mac` no chat) já é
   a aprovação. Uma que o Visão propõe fica parada até você tocar em Aprovar. O servidor só
   entrega ao braço tarefas aprovadas, e só o seu login aprova; o agente não tem esse poder.
2. **O braço decide o que é permitido, não o servidor.** Os projetos (nome → pasta), as
   ferramentas do Claude Code e os limites ficam em `~/.config/visao/braco.json`, no Mac. Mesmo
   um servidor comprometido só consegue pedir trabalho nesses projetos, com essas ferramentas.
3. **Claude Code em `dontAsk`.** Tudo que não está na lista de ferramentas é negado, nunca
   perguntado; `--dangerously-skip-permissions` nunca é usado. O padrão permite ler, buscar,
   editar dentro do projeto e rodar `git status`/`git diff`/testes; nada de `curl`, `rm`, `sudo`
   ou `git push` sem você acrescentar.
4. **Limites por tarefa:** número de turnos (`--max-turns`), custo estimado (`--max-budget-usd`)
   e tempo (o braço interrompe com SIGINT e depois SIGKILL).
   - Desde a versão 3, cada tarefa roda num grupo de processos só dela. Quando o Claude Code
     termina, ou passa do tempo, o grupo inteiro acaba junto, inclusive um servidor de teste ou um
     watcher que ele tenha deixado rodando. A saída vai para arquivos, não para pipes, e com isso
     um processo deixado em segundo plano não segura mais o braço até o timeout.
5. **Token do aparelho revogável.** O braço se identifica com um token próprio, guardado só como
   hash no servidor. Apagar o aparelho na interface corta o braço na hora.
6. **Uma tarefa não muda o que vale para as próximas** (desde 23/11/2026, braço versão 2).
   - O Claude Code roda isolado, com `--restricted --strict-mcp-config --tools …`:
     - ignora as configurações do projeto (`.claude/`) e as suas;
     - não carrega servidores MCP;
     - prende as ferramentas de arquivo à pasta do projeto;
     - não deixa gravar arquivos de configuração e de git sem uma pessoa aprovar.
   - Num Claude Code mais antigo, sem `--restricted`, o braço usa `--setting-sources user` com os
     hooks desligados e `--strict-mcp-config`. Sem nenhuma das duas opções, ele não roda nada e
     pede `claude update`.
   - Além disso, editar ou criar `.claude/**`, `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md` e
     `.git/**` fica sempre negado, mesmo que o `braco.json` libere.
   - Conferido de verdade em 23/11/2026 com o Claude Code 2.1.330: o pedido de criar
     `.claude/settings.local.json` foi negado, e o `nota.txt` do mesmo pedido foi criado.
7. **O resultado não se perde.**
   - O braço grava o resultado em `~/.config/visao/saida/` antes de enviar e só apaga quando o
     servidor recebe. Se a rede cair, ele reenvia na rodada seguinte; o servidor aceita a
     repetição sem duplicar a mensagem.
   - Se o Mac desligar ou o braço reiniciar no meio, a tarefa volta como "interrompida" e
     **nunca é refeita sozinha**, porque pode ter mexido em arquivos pela metade.
   - Durante a tarefa, o braço manda sinal de vida a cada minuto dizendo em qual tarefa está.
     Com isso, um Mac que some faz a tarefa falhar em 10 minutos, e não em 3 horas.
   - Um resultado que chegue depois disso ainda entra e substitui a falha.
   - Braços da versão 1 não mandam esse sinal e continuam com o prazo de 3 horas.

8. **Todo comando roda no sandbox do Claude Code** (desde 23/11/2026, braço versão 3).
   - Com `Edit` e um comando de teste liberados, uma tarefa pode mudar um teste, o `Makefile` ou o
     `package.json` e rodar o que quiser. Comando exato não resolve, porque o código que ele roda
     foi a própria tarefa que escreveu. O que limita é o sandbox.
   - O braço passa `--settings` com `sandbox.enabled`, e todo `Bash` da tarefa roda dentro dele:
     - grava só na pasta do projeto e na pasta temporária;
     - não tem rede;
     - não lê `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/Library/Keychains` nem `~/.config/visao` (onde
       ficam o token do braço e as fotos);
     - não tenta de novo fora do sandbox (`allowUnsandboxedCommands: false`);
     - não roda nada se o sandbox não subir (`failIfUnavailable: true`).
   - Conferido de verdade em 23/11/2026 com o Claude Code 2.1.330, num Linux em que o sandbox não
     consegue subir: a tarefa rodou `make test` com um `Makefile` que tentava acessar a rede,
     gravar fora do projeto e ler `~/.ssh`, e o Claude Code recusou o comando em vez de rodá-lo
     sem proteção. Nada saiu do projeto.
   - **No Mac ainda não foi visto funcionando.** No macOS o sandbox usa o Seatbelt do sistema.
     Depois de atualizar, peça uma tarefa que rode os testes e confira se eles rodam. Se os seus
     testes precisam de rede ou do Docker, eles vão falhar dentro do sandbox.
9. **O braço confere o que mudou e sabe desfazer** (versão 3).
   - Antes e depois de cada tarefa, ele tira uma foto do projeto num git só dele, em
     `~/.config/visao/fotos/<projeto>.git`. O `.git` do projeto não é tocado.
   - A lista de arquivos novos, mudados e apagados entra no resultado como fato medido pelo braço,
     e não como relato do Claude.
   - Na página Mac, uma tarefa com arquivos mudados ganha **desfazer**. O toque é a aprovação.
   - O braço então volta esses arquivos ao que eram, sem chamar o Claude. Se algum deles mudou de
     novo depois da tarefa, ele não mexe em nada e diz quais foram.
   - O que o `.gitignore` do projeto ignora (`node_modules`, `.env`) não entra na foto, então não
     aparece na lista e não é desfeito.
10. **Até os testes passarem** (versão 3).
    - Escreva no pedido "até os testes passarem" (ou "até passar nos testes"), por exemplo
      `/mac visao conserta o login até os testes passarem`. Quem reconhece a frase é o código.
    - O comando de testes é você quem define, no Mac, por projeto, no `braco.json`:
      `"visao": {"pasta": "~/workspace/visao", "testes": "make check"}`. Sem ele, o braço recusa
      antes de gastar qualquer coisa.
    - Quem diz se passou é o código de saída desse comando, não o Claude.
    - Enquanto falhar, o braço continua na mesma sessão do Claude, mandando o final da saída.
      Todas as tentativas ficam dentro da mesma aprovação e do mesmo limite de custo e de tempo.
    - O máximo é `test_attempts` tentativas (3 por padrão). Cada rodada dos testes tem limite de
      `test_timeout_minutes` (10 por padrão).
    - Os testes rodam dentro de um sandbox do macOS (`sandbox-exec`), com os mesmos limites do
      item 8, mas com rede liberada para o próprio Mac (`localhost`). Fora do macOS eles não rodam.
    - Desfazer e "até os testes passarem" só vão para braços da versão 3. Um braço antigo trataria
      o desfazer como um pedido ao Claude.

   **Para atualizar o Mac:** rode `bash arm/instalar-mac.sh` de novo, de dentro do repositório. O
   `braco.json` é mantido.

**O que ainda não está coberto:**
- **Leitura fora do projeto.** O sandbox bloqueia gravação e rede, mas comandos ainda leem a
  maior parte do disco, exceto as pastas de chaves listadas acima. O que for lido só pode sair no
  resumo que volta para você.
- **Arquivos ignorados pelo git** não entram na foto, então não aparecem na lista nem são
  desfeitos.

## Como roda o Claude Code

O braço chama `claude -p --restricted --strict-mcp-config --tools … --settings '{"sandbox": …}'
--output-format json
--permission-mode dontAsk --allowedTools ... --disallowedTools ... --max-turns N
--max-budget-usd X`, com o pedido pela entrada padrão, dentro da pasta do projeto e lê do JSON o
resultado (`result`), o custo estimado (`total_cost_usd`) e a sessão (`session_id`). Uma tarefa
pode continuar a anterior com `--resume <session_id>`.

Autenticação: o braço usa o login do Claude Code no Mac (sua assinatura) ou `ANTHROPIC_API_KEY`,
se você preferir pagar por uso. A documentação do Agent SDK pede chave de API para produtos de
terceiros; para uso pessoal seu, no seu Mac, o login comum é o caminho mais simples. Confirme os
termos se um dia isso for oferecido a outras pessoas.

## Primeira versão (feita)

- Servidor: aparelhos (`arm_devices`) e tarefas (`arm_tasks`), migração `0017`; rotas `/arm/*`
  para você (parear, listar, aprovar, recusar, cancelar) e para o braço (pegar a próxima, mandar
  resultado, sinal de vida).
- Chat: `/mac <projeto> <pedido>` cria a tarefa já aprovada. O resultado volta como mensagem na
  mesma conversa, com aviso push se o app estiver fechado.
- Mac: `arm/visao_braco.py` (só biblioteca padrão do Python) e `arm/instalar-mac.sh`, que deixa o
  braço rodando pelo `launchd` e reiniciando sozinho.
- Interface: página Mac (parear, ver tarefas) e Pendências (aprovar/recusar).
- O Visão propõe sozinho (2026-11-12): um pensamento pode sugerir uma tarefa
  (`propose_mac` em `core/mind/think.py`). Ela nasce `proposed`, avisa no celular e só roda depois
  do seu sim. Limites no código: só projetos que o Mac liberou, nada com a autonomia pausada, uma
  proposta esperando por vez, no mínimo 8 h entre propostas, no máximo 2 por dia (1 com confiança
  baixa, nenhuma com cautela alta; veja Temperamento em [MIND.md](MIND.md)).
- Pedido em linguagem normal (2026-11-12): "roda os testes do visao" vira uma tarefa esperando um
  toque numa barra logo acima do campo de escrever (`core/arm/intent.py`), sem `/mac`. Uma
  conferência em código vem antes (a mensagem precisa citar um projeto liberado ou o Mac e ter um
  verbo de ação); só então uma chamada curta extrai o projeto e o pedido. Como foi ele que
  interpretou, a tarefa nasce `proposed` e nada roda antes do seu sim.

- Modelo local (2026-11-18): o braço também leva perguntas para um modelo rodando no Mac
  (Ollama), numa segunda linha separada das tarefas. Veja [MODELO_LOCAL.md](MODELO_LOCAL.md).
- Ele sabe o que o braço fez (2026-11-13): toda resposta leva o registro do braço tirado do banco
  (`work_record` em `core/arm/service.py`: os Macs, se estão ligados, e as últimas tarefas com
  pedido, situação e resultado) e a regra de que o que consta ali rodou de verdade. Antes disso
  ele via o próprio "Terminei no Mac" no histórico, não sabia distinguir de uma invenção e chegou
  a pedir desculpas por um `git status` que tinha rodado.

## Próximas fases

1. **Aprovação por ferramenta.** `--permission-prompt-tool` manda cada pedido de permissão fora
   da lista para o celular, em vez de negar.
2. **Seus assuntos:** email e agenda já estão feitos ([GOOGLE.md](GOOGLE.md)). Faltam arquivos
   (Drive), com o mesmo portão de aprovação para qualquer coisa que envie, apague ou pague.
3. **Isolamento mais forte:** braço num usuário macOS só dele (o sandbox já está ligado desde a
   versão 3).
