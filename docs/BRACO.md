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
   e tempo (o braço interrompe com SIGINT e depois SIGTERM).
5. **Token do aparelho revogável.** O braço se identifica com um token próprio, guardado só como
   hash no servidor. Apagar o aparelho na interface corta o braço na hora.

## Como roda o Claude Code

O braço chama `claude -p "<pedido>" --output-format json --permission-mode dontAsk
--allowedTools ... --max-turns N --max-budget-usd X` dentro da pasta do projeto e lê do JSON o
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

## Próximas fases

1. **Aprovação por ferramenta.** `--permission-prompt-tool` manda cada pedido de permissão fora
   da lista para o celular, em vez de negar.
2. **Seus assuntos:** email, agenda e arquivos, cada um como integração com permissão própria,
   leitura antes de escrita, e o mesmo portão de aprovação para qualquer coisa que envie, apague
   ou pague.
3. **Isolamento mais forte:** braço num usuário macOS só dele, ou o Claude Code no sandbox.
