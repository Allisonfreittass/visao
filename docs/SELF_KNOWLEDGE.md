# Autoconhecimento: ele lê o próprio código

Ele consegue explicar como funciona, e por que algo falhou, a partir do código e da documentação
do repositório em que roda. Antes, a pergunta "por que sua notificação não chegou?" recebia um
palpite: nada no prompt descrevia como ele é feito.

## O que ele tem

- **Mapa, sempre no prompt** (`overview` em `core/identity/self_knowledge.py`): as pastas e os
  módulos, montado da árvore de arquivos. Um módulo novo aparece sozinho.
- **Trechos, quando a conversa pede** (`context_block`): se a mensagem é sobre ele (cita código,
  funcionalidade, notificação, memória, um arquivo, uma função, ou pergunta "como você..."), a
  resposta recebe até 4 trechos: seções destes documentos, o resumo de um módulo, ou o código de
  uma função ou classe, com o caminho do arquivo.
- **Estado de agora** (`core/identity/capabilities.py`): o que está ligado, se o servidor tem as
  chaves de Web Push, quantos aparelhos recebem aviso, se a autonomia está pausada.

A busca é por palavras, sem chamada de modelo: palavras raras pesam mais, o nome de um arquivo ou
de uma função pesa muito, e um pequeno dicionário liga o português da conversa ao inglês do código
("notificação" também procura `notification` e `push`). O índice é montado uma vez por processo,
em menos de um segundo.

## Limites

- **Só leitura.** Ele não edita nem executa nada por aqui. Alterar código continua sendo o
  experimento separado e restrito de [CODE_EVOLUTION.md](CODE_EVOLUTION.md).
- **Só o que está no Git**: `apps/api`, `apps/worker`, `arm`, `core`, `integrations`, `infrastructure`,
  `apps/web/src`, `README.md` e `docs/`. O `.env`, o banco, os testes e as dependências ficam de
  fora, então nenhuma chave entra no prompt.
- **Só o que couber**: cerca de 4 mil caracteres por resposta. Ele é instruído a dizer que não leu
  uma parte, em vez de supor.
- **Código da versão em execução.** Depois de mudar o código, é preciso reiniciar (ou publicar)
  para ele ler a versão nova.
- Conversa sobre a sua vida não puxa código: sem sinal de que a pergunta é sobre ele, nada entra.
