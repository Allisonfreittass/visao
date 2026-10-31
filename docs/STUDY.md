# Estudo autônomo e caderno de pesquisa

O estudo é uma atividade opcional, separada da memória pessoal e das pesquisas que respondem
às mensagens. É ativado no caderno de estudos. O controle grava `auto_study` nas permissões do
dono e agenda um ciclo. A pausa global interrompe o estudo. Publicar acesso à aplicação não é
necessário para pesquisar: a instalação local usa conexões de saída à Wikipédia e ao modelo.

## Uma rodada

1. No máximo uma tentativa a cada seis horas por dono (até quatro por 24 horas). Uma chave
   única por dono/janela evita duplicação por dois workers. Erros também consomem a rodada;
   não há tentativa infinita. Ativação repetida não cria uma nova rodada na mesma janela.
2. O modelo recebe até oito memórias curadas válidas e cinco lacunas de fatos públicos,
   somente com consentimento de memória. Também recebe seu caderno anterior, incluindo
   próximas perguntas. Sem contexto, pode escolher uma pergunta geral sobre conhecimento,
   pesquisa ou aprendizagem. Não recebe transcrições brutas.
3. Propõe tema, pergunta, consulta e motivo. Referências de origem devem existir e pertencer
   ao mesmo dono. Temas privados/sensíveis, credenciais e URLs na consulta são recusados.
4. Uma busca pública de até três resultados usa o adaptador existente da Wikipédia em
   português. Se ficar vazia, há uma segunda consulta pelo tema curto, somente se houver
   saldo no orçamento compartilhado de pesquisas. Nenhuma URL sugerida pelo modelo é buscada.
5. O modelo revisa apenas os trechos recuperados. Um achado precisa citar números de fontes
   válidos; a aplicação resolve as URLs a partir das fontes reais. Registra incerteza e uma
   próxima pergunta. Os achados continuam provisórios; uma enciclopédia não representa
   confirmação por fontes independentes. Falta de evidência aparece como inconclusiva.
6. Apenas descobertas avaliadas como relevantes podem gerar aviso, sujeito à pausa, aos
   horários de silêncio e ao limite de cinco avisos por 24 horas. Cada estudo fica no caderno
   mesmo se não gerar aviso. Notas relevantes podem voltar ao contexto da conversa.

## Limites e continuidade

As chamadas `study_plan` e `study_review` usam os limites diários de chamadas e tokens da
**autonomia inteira**, além do teto diário em dólares. Há conferências antes de cada chamada,
leitura e entrega; desligar o estudo ou pausar durante a geração impede a etapa seguinte.
Uma chamada já iniciada pode consumir seu custo/tokens antes da próxima conferência, como nas
outras chamadas do projeto. O limite de duração é verificado entre as etapas; não interrompe
uma chamada já em curso. Reservam-se duas chamadas disponíveis antes de começar uma rodada.
As buscas compartilham a quota com chat e retomadas de pesquisa, contando tentativas vazias.

O resultado é persistido em `study_entries`, com evidências e ligação à rodada anterior.
Não modifica os pesos do modelo, não cria consciência, não altera a personalidade e não
promove textos da web automaticamente a memórias pessoais. Interesses podem ser observados
nas escolhas de perguntas; permanecem comportamento registrado e revisável.

## Operação

- Aplicar `alembic upgrade head` (revisão `0010`, aditiva).
- Reiniciar API e worker para carregar o código. `npm start` já aplica migrações ao iniciar.
- O worker precisa continuar rodando. O ciclo periódico (padrão uma hora) executa a próxima
  rodada elegível; seis horas é o intervalo mínimo, não promessa de execução no segundo exato.
- `GET /study`: estado, próxima oportunidade e últimas doze rodadas, só do dono autenticado.
- `PUT /study/settings {"enabled": true|false}`: consentimento e agendamento inicial.
- Estado inconclusivo ou falha é preservado. Não há reexecução imediata que esconda o erro.
- O painel tem abas de conversa e estudos; desligar não apaga o histórico de pesquisa.
- Fontes continuam restritas à Wikipédia. Ampliação para outras fontes exige outro adaptador
  e políticas específicas; páginas são dados, nunca instruções para o agente.
