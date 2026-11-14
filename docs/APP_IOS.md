# App do iPhone (SwiftUI)

O cliente nativo do iPhone fica em `apps/ios/`. Ele fala com a **mesma API** do web (FastAPI atrás
do Caddy, em `/api`); nada no servidor muda por causa dele.

| Pasta | O que tem |
|---|---|
| `apps/ios/VisaoKit/` | Pacote Swift com o que dá para testar sem tela: cliente da API, tipos, Keychain, a fila de envio do chat e o Markdown. Testes em XCTest. |
| `apps/ios/Visao/` | As telas em SwiftUI (login, conversas, chat). A pasta é sincronizada com o projeto: arquivo novo aqui entra no app sozinho. |
| `apps/ios/Config/` | `Visao.xcconfig` (no git), `Local.xcconfig` (seu, fora do git) e o `Info.plist`. |
| `apps/ios/Visao.xcodeproj` | O projeto do Xcode. |

O app se chama **V.I.S.A.O.** na tela inicial, com o bundle id `io.github.allisonfreittass.visao`
(em `Config/Visao.xcconfig`) e o ícone do PWA. O bundle id não precisa ser criado em lugar
nenhum: com assinatura automática, o Xcode registra na Apple sozinho na primeira vez que roda no
iPhone.

iOS 18 ou mais novo, Swift 6, Observation, async/await e URLSession. Uma dependência de terceiros, aprovada: soniqo/speech-swift (só o Kokoro e a Supertonic), para as vozes no iPhone.

## Antes da primeira vez

1. **Termine a instalação do Xcode.** Se o Xcode nunca foi aberto neste Mac (ou foi atualizado),
   rode uma vez, com a sua senha:

   ```bash
   sudo xcodebuild -runFirstLaunch
   ```

   Sem isso o `xcodebuild` e o simulador não carregam (`CoreSimulator.framework` não encontrado).
   Abrir o Xcode e aceitar a instalação de componentes faz o mesmo.

   O fundo de pinheiros é um shader Metal, e o Xcode não traz mais o compilador de Metal junto.
   Uma vez por instalação do Xcode:

   ```bash
   xcodebuild -downloadComponent MetalToolchain
   ```

   (Xcode → Settings → Components também instala.) Sem ele o build para em `Sky.metal` com
   "missing Metal Toolchain".

2. **Entre com o seu Apple ID no Xcode**: Xcode → Settings → Accounts → + → Apple ID. Isso cria
   o seu "Personal Team", e o Team ID dele vai no `Local.xcconfig`.

3. **Crie o seu `Local.xcconfig`:**

   ```bash
   cp apps/ios/Config/Local.example.xcconfig apps/ios/Config/Local.xcconfig
   ```

   e preencha:

   | Chave | O que é |
   |---|---|
   | `VISAO_DEVELOPMENT_TEAM` | O Team ID do passo 2 (o do "Personal Team"). |
   | `VISAO_API_BASE_URL` | Onde a API responde. Produção: `https:/$()/seu-endereco/api`. API no Mac: `http:/$()/seu-mac.local:8000`. O `$()` é obrigatório: num `.xcconfig`, `//` começa um comentário. |

   O endereço também dá para trocar na tela de login, em "Servidor"; o que você digita ali fica
   guardado no aparelho (não é segredo) e vale até você trocar de novo.

## Rodar no iPhone pelo cabo (Apple ID grátis)

1. Abra `apps/ios/Visao.xcodeproj` no Xcode.
2. Ligue o iPhone no cabo e desbloqueie. Na primeira vez: "Confiar neste computador" no iPhone, e
   ative o **Modo de Desenvolvedor** (Ajustes → Privacidade e Segurança → Modo de Desenvolvedor;
   o iPhone reinicia).
3. No topo do Xcode, escolha o esquema **Visao** e o seu iPhone como destino. ⌘R.
4. Na primeira instalação o iOS bloqueia o app de um desenvolvedor desconhecido: Ajustes → Geral →
   VPN e Gerenciamento de Dispositivo → seu Apple ID → Confiar.

**A cada 7 dias o app para de abrir**: o perfil do Apple ID grátis vence. Ligue o cabo e rode de
novo pelo Xcode (⌘R); os dados e o login continuam. Outros limites do Apple ID grátis: até 3 apps
seus instalados por vez e 10 ids de app novos por semana.

### Testes

```bash
cd apps/ios/VisaoKit && swift test
```

Roda no Mac, sem simulador. No Xcode, ⌘U no esquema Visao roda os mesmos testes.

O que está coberto: login em formulário OAuth2 (a senha vai no corpo e é escapada por inteiro),
token Bearer, 401 que derruba a sessão, erros do FastAPI (texto e lista de validação), corpo do envio
igual ao do web, datas sem fuso e com microssegundos lidas como UTC, a fila (a mensagem aparece na
hora, o que você escreve enquanto ele responde vai junto como uma mensagem só), Parar (pelo app e
pelo servidor), o passo ao vivo só com a tela visível, mensagem que falhou continua visível, e o
Markdown (código sem fechar, só links http/https, HTML como texto). Da etapa 2: upload em multipart (nome
com aspas não quebra o cabeçalho), foto grande vira JPEG de 1568 px e foto pequena vai como está,
limite de 4 anexos, o motivo de um anexo recusado, foto sozinha como mensagem, página "Criando…"
que fica pronta e apagar página, e as cores do céu iguais às do web nas horas-chave. Da etapa 3:
só trabalho proposto do Mac vira cartão, o corpo do email aparece, `via=toque`/`via=voz` na rota, e
decisão recusada pelo servidor não some nem é dada como feita. Da etapa 5: os vereditos de voz
com os mesmos casos do `approval.test.ts`, o texto falado do `speakable.test.ts`, cada pedido lido
uma vez, resposta só dentro de 3 minutos e só para o pedido ainda esperando, e `modality=voice`.

## O que o app tem

### Etapa 1: conversa

- **Login** com e-mail e senha; o token fica no **Keychain** (só este aparelho, depois do primeiro
  desbloqueio), nunca em UserDefaults. Um 401 em qualquer chamada volta para o login.
- **Conversas**: na gaveta (rotuladas pela data, como no web), com + para começar outra. O app
  abre direto na conversa mais recente; uma conversa nova só é criada no servidor com a primeira
  mensagem.
- **Chat**: envio otimista; o que você escreve enquanto ele responde aparece mais apagado ("na
  fila") e vai junto depois da resposta. O passo atual vem de `/conversations/{id}/progress` a
  cada 0,9 s, **só com o app na frente** (com a tela bloqueada o servidor percebe e manda o aviso,
  ver [STATUS.md](STATUS.md)); × para o turno. O que ele diz por conta própria aparece sozinho
  (a cada 15 s com a conversa aberta).
- **Responder**: arraste a mensagem para a direita (vibra leve ao armar) ou toque e segure →
  Responder. A citação na mensagem leva até a original.
- **Markdown** nas respostas: parágrafos, títulos, listas, `código` e blocos de código com a
  linguagem, rolagem lateral e Copiar. Links só http/https.
- **Teclado**: o campo fica colado no teclado e arrastar a conversa para baixo fecha o teclado.
- **Dynamic Type** (todo tamanho de letra segue o do iPhone) e VoiceOver com ação "Responder".

### Etapa 2: o visual do web, fotos, arquivos e páginas

- **Neblina**, a aparência do web ([`ceu.css`](../apps/web/src/ceu.css)): a floresta de pinheiros
  com neblina atrás de tudo, que é o shader de [`sky.ts`](../apps/web/src/sky/sky.ts) portado para
  Metal ([`Sky.metal`](../apps/ios/Visao/Sky.metal)), com as mesmas cores por hora do dia
  (`SkyLook` no VisaoKit, testado contra as horas-chave do web). Vidro fosco claro de dia e escuro
  à noite, como o web troca: o teclado e as folhas do sistema acompanham. As respostas dele em
  bolha sólida à esquerda, as suas em vidro à direita; a orbe com a lanterna ao lado do campo.
- **Noite**: o tema escuro liso da marca, quando "Floresta com neblina ao fundo" está desligado
  em Ajustes.
- **Leve**: a neblina é desenhada em meia resolução e a 20 quadros por segundo, e para com Reduzir
  Movimento, Modo de Pouca Energia, app em segundo plano ou "Neblina em movimento" desligado
  (continua seguindo a hora).
- **Fontes do web**: Instrument Serif, Inter Tight e JetBrains Mono, do Google Fonts, com as
  licenças OFL em `apps/ios/Visao/Fonts/`.
- **Anexos** pelo + do campo: **Fotos**, **Câmera** e **Arquivos**, nos limites de
  [ANEXOS.md](ANEXOS.md): até 4 por mensagem, foto até 5 MB, PDF e texto até 10 MB. Cada um sobe
  assim que é escolhido e mostra se falhou e por quê; uma foto sozinha já é uma mensagem. Fotos
  viram JPEG de até 1568 px antes de subir (HEIC da câmera sempre, porque o servidor não aceita
  HEIC); GIF vai como está.
- Fotos e arquivos das mensagens abrem no **Quick Look**, que já tem o botão de compartilhar.
- **Páginas** ([ARTEFATOS.md](ARTEFATOS.md)): o cartão embaixo da resposta passa de "Criando…" para
  Abrir (o app confere a cada 3 s, só com a tela visível). A página abre numa folha com
  **WKWebView sem JavaScript e sem cookies**; links vão para o Safari. Na folha: compartilhar pela
  folha nativa, abrir no Safari, copiar o link e apagar (o link para de funcionar).

### Etapa 3: aprovar ali mesmo

- Os pedidos que esperam o seu sim viram **cartões com Recusar e Aprovar**, como no web:
  email a enviar e evento a marcar (`/google/actions`, [GOOGLE.md](GOOGLE.md)) e trabalho que ele
  propôs para o Mac (`/arm/tasks` com status `proposed`, [BRACO.md](BRACO.md)). **Nada roda sem o
  toque.** O email mostra o corpo inteiro antes de você aprovar.
- Na conversa de onde o pedido veio, o cartão fica embaixo das mensagens. Todos também aparecem
  em **Início → Pendências**, inclusive os que não são de nenhuma conversa.
- O toque vai com `?via=toque` (a ligação da etapa 5 usa `via=voz`), e o servidor registra no
  audit. Se o servidor recusar (já decidido, expirado), o cartão continua e o motivo aparece; o app
  nunca diz que foi feito antes da resposta do servidor. Depois de aprovar um email ou evento, a
  mensagem dele dizendo o que fez aparece na conversa.
- A lista de pedidos é atualizada ao abrir, depois de cada resposta e a cada 15 s com o app na
  frente.

### Rolagem do chat

O chat abre no fim da conversa e só desce sozinho se você já está no fim (ou acabou de mandar
algo): lendo mais acima, nada puxa a lista. A pilha não é preguiçosa (as mensagens antigas eram
medidas só ao aparecer, e a lista pulava); são desenhadas as últimas 60, com "Mostrar mensagens
anteriores". Cada mensagem só é redesenhada quando muda, o Markdown é lido uma vez por resposta,
e as bolhas não têm desfoque ao vivo por cima da floresta, que era refeito a cada quadro.

### A mesma estrutura do web

O app segue as telas do web (`SkyNav.tsx`, `Rail.tsx`, `InboxView.tsx`, `ProjectsView.tsx`,
`MacView.tsx`, `SettingsView.tsx`), não um app de sistema com lista e navegação do iOS:

- **Barra de topo**: o botão redondo da gaveta, a pílula **Início · Chat · Projetos** (com o número
  de pendências em vermelho no Início) e o avatar com a inicial dele, que abre Ajustes. A seleção
  da pílula é uma gota que **desliza** até a aba com mola; dá para **arrastar** a gota de uma aba
  para outra, com um toque leve de vibração em cada uma, como na barra de abas do iOS 26.
- **As telas deslizam** para o lado da aba. Em Início e Projetos, arrastar para o lado troca de
  aba (no chat, arrastar uma mensagem continua sendo responder). O chat fica montado enquanto você
  visita as outras telas: uma resposta a caminho continua e você volta onde estava.
- **Liquid Glass** (iOS 26 em diante) nos controles que flutuam: os botões da barra, a pílula, o
  campo de mensagem, a orbe e a gaveta. Antes do iOS 26, o vidro fosco do web.
- **Gaveta** de vidro pela esquerda: a marca, Conversa, Pendências, Projetos, Caderno, Mac e Ajustes, as
  conversas com + e "Conectado" embaixo. Arrastar para a esquerda ou tocar fora fecha.
- **Chat** é a tela de entrada, como no web.
- **Início → Pendências**: "Nada esperando por você." ou o que precisa de você, em grupos: No Mac,
  Email e agenda, Metas que eu quero seguir e Avisos (Responder abre a conversa, Dispensar marca
  como lido). As aberturas dele não contam: já estão no chat e são marcadas como lidas ao abrir.
- **Projetos**: sem nenhum, a frase grande em serifa sobre a floresta com o campo para criar; com
  projetos, os cartões; dentro de um, nova conversa aqui, trazer a conversa aberta, renomear,
  apagar e as conversas, páginas e arquivos dele.
- **Caderno** ("O que eu fiz enquanto você não estava."): o que ele sabe de você e o que aprendeu
  com as suas correções (desfazer e apagar), temperamento, o que quer te perguntar, como se
  descreve (desfazer), interesses, pensamentos e o caderno de estudo com achados e fontes, e a
  chave do estudo autônomo. Atualiza a cada 15 s com a tela aberta.
- **Mac**: os Macs pareados (ligado ou não, projetos liberados), desconectar, **parear** (o token
  aparece uma vez, com Copiar) e o que ele fez lá. `/mac projeto pedido` no chat pede ao Mac.
- **No chat**: "Como foi essa resposta?" embaixo das respostas dele (polegar e etiquetas, como no
  web) e a **Bancada** no botão do canto: o passo atual, as páginas, os sites lidos ao vivo e o
  que ele fez de verdade, tirado do registro.
- **Boas-vindas**: na primeira vez, os três passos do web (como funciona, perguntas, permissões),
  sempre dá para pular; refazer em Ajustes → Memória.
- **Ajustes** ("Do seu jeito."): Aparência (floresta e movimento), Autonomia (agir por conta
  própria, pesquisar sozinho), Google (estado, olhar sozinho, desconectar; conectar continua pelo
  computador), Memória (lembrar, refazer as perguntas iniciais) e Conta (trocar senha e email,
  sair). Os de voz entram com a ligação (etapa 5); avisos com o app fechado dependem da conta paga
  (APNs).

### Etapa 5: ligação por voz

Toque na **orbe** ao lado do campo: a tela inteira vira a conversa, sem as mãos e com a tela
acesa, como a ligação do web ([VOICE.md](VOICE.md)).

- **Ouvir**: `SFSpeechRecognizer` em pt-BR. Quando o iPhone permite, o reconhecimento roda **no
  próprio aparelho** (a tela da ligação diz "no iPhone"); senão usa os servidores da Apple, e
  Ajustes avisa. Uma frase termina depois de 1,3 s de silêncio.
- **Falar**: `AVSpeechSynthesizer` com a melhor voz pt-BR instalada no iPhone (vozes melhores em
  Ajustes do iPhone → Acessibilidade → Conteúdo Falado → Vozes). Código e links não são lidos:
  ele diz que deixou na tela (as mesmas regras do `speakable.ts`).
- **Interromper falando** (ligado por padrão): é só falar por cima que ele para e escuta, como no
  modo de voz do Grok. O áudio da ligação vai nos dois sentidos ao mesmo tempo
  (`DuplexVoice.swift`): o microfone fica aberto com o processamento de voz do iPhone (o
  cancelamento de eco do FaceTime) e a voz dele toca pelo mesmo motor de áudio, então o iPhone
  sabe o que tirar do microfone. Enquanto ele fala, o reconhecimento continua; uma ou duas
  palavras suas (não o eco) param a fala e viram o seu turno. Os primeiros 450 ms de cada fala são
  ignorados, enquanto o cancelamento de eco se ajusta. Desligado em Ajustes → Voz e avisos, volta o
  jeito antigo: enquanto fala não ouve, e o botão **Interromper** para.
- Na ligação, a resposta e o que ele fala por conta própria (aberturas, o relatório do Mac) saem
  em voz. O que você fala vai como `modality=voice`.
- **Aprovar por voz**: quando há um email, evento ou pedido ao Mac esperando, ele termina de
  falar, lê exatamente o que vai fazer e espera **"pode mandar"** (ou "pode marcar", "pode rodar",
  "aprovo", "confirmo", um "sim" curto) ou **"não"** ("cancela", "espera"). Regras fixas, sem
  modelo, iguais às do `approval.ts`: frase que mistura sim e não, ou longa, não decide nada e
  segue como mensagem. Vale só para o pedido que ele acabou de ler, por 3 minutos. A decisão vai
  com `via=voz` e ele só diz "pronto" depois que o servidor aceitou; se falhar, diz que ficou na
  tela. O cartão também aparece grande na ligação, com Aprovar e Recusar.
- **Privacidade**: o microfone só abre pela orbe; sair do app ou bloquear a tela desliga a
  ligação. Nada escuta em segundo plano.
- **Ajustes → Voz e avisos**: "Falar as respostas" (fora da ligação também) e "Aprovar por voz na
  ligação".
- **Vozes no iPhone** (Ajustes → **Voz no iPhone**): cada uma é baixada uma vez, quando você toca
  em Baixar, tem "Ouvir uma amostra", "Usar esta voz" e "Apagar"; a escolhida vale para a ligação
  e para "Falar as respostas". "Voz do servidor ou do iPhone" volta ao que não precisa baixar.
  - **Supertonic 3** (~350 MB, versão FP16 para o Neural Engine,
    [aufklarer/Supertonic-3-CoreML-FP16](https://huggingface.co/aufklarer/Supertonic-3-CoreML-FP16)):
    99M de parâmetros, 31 idiomas, lê o português direto do texto, sem regras de pronúncia, e
    tem 10 vozes (5 femininas, 5 masculinas). Licença dos pesos **OpenRAIL-M**: livre para uso
    pessoal, com restrições de uso (proíbe imitar pessoas reais sem consentimento, entre outras).
    Produto `SupertonicTTS` do mesmo pacote. Na primeira vez que abre, o iPhone compila o modelo,
    o que leva alguns segundos.
- **Pronúncia brasileira no Kokoro**: o dicionário de português do pacote é **europeu** ("tarde"
  vira tˈaɾədɨ), por isso a Dora, treinada em pt-BR, soava robótica e não brasileira. O app
  converte o texto com regras próprias de português do Brasil (`VisaoKit/BrazilianPhonemes.swift`,
  sem espeak e sem GPL), nos mesmos símbolos com que a voz foi treinada (espeak-ng `pt-br`
  passado pelo misaki: ʤ, ʧ, I, A, W): "de"/"di" → ʤi, "te"/"ti" → ʧi, e/o finais → i/ʊ, l final
  → w, r forte → x, s entre vogais → z, vogais nasais, acento pelas regras e uma lista de palavras
  comuns; números por extenso. Como o gancho público de pronúncias do pacote só vale no caminho do
  inglês, cada palavra vai como um código neutro ("qx…") registrado com a pronúncia brasileira.
  Erros de pronúncia se corrigem na lista de exceções ou nas regras, com teste.
- **Kokoro no iPhone** (~335 MB, uma vez): o Kokoro-82M
  roda no próprio iPhone pelo Core ML (Neural Engine), com a voz `pf_dora`, a mesma que ele
  escolheu no servidor. Depois de baixado, fala sem servidor e sem internet, frase a frase,
  sintetizando a próxima enquanto a atual toca. É a primeira escolha quando está baixado e ligado.
  - Pacote: [soniqo/speech-swift](https://github.com/soniqo/speech-swift) **0.0.29** (versão
    exata), produto `KokoroTTS`, Apache-2.0. O português sai de um dicionário de pronúncia e de
    regras em Swift: **sem espeak-ng, sem GPL**. Por isso a pronúncia pode errar em algumas palavras.
  - Modelo: [aufklarer/Kokoro-82M-CoreML](https://huggingface.co/aufklarer/Kokoro-82M-CoreML)
    (pesos do hexgrad/Kokoro-82M, Apache-2.0), baixado do Hugging Face só quando você toca em
    Baixar. "Apagar" libera o espaço.
  - Exige iOS 18: o app passou a pedir iOS 18 ou mais novo.
  - A ordem da voz fica: a voz escolhida no iPhone → voz própria do servidor → voz do iPhone.
  - O modelo só abre na primeira vez que vai falar, nunca ao abrir o app. Roda no CPU + Neural
    Engine: no iOS 27.3 beta o caminho pela GPU (MPSGraph) derrubava o Core ML ao abrir o modelo.
    Se abrir o modelo derrubar o app, na vez seguinte ele tenta só no CPU; se de novo, desliga o
    Kokoro neste aparelho e diz por quê, em vez de cair a cada uso ("Tentar de novo" em Ajustes
    recomeça depois de atualizar o iOS).
- **Voz própria**: quando o servidor tem o Kokoro instalado e uma voz aprovada (`/voice/status`),
  o app fala com ela, frase a frase (`/voice/sentences` e `/voice/tts`), sintetizando a próxima
  enquanto a atual toca, como o web; a ligação mostra "Voz própria". Se o servidor falhar no meio,
  o resto sai na voz do iPhone. Sem Kokoro no servidor (como na nuvem hoje), é a voz do iPhone.

### Etapa 7: Live Activity (tela de bloqueio e Dynamic Island)

Quando você manda uma mensagem, aparece um cartão na tela de bloqueio e na Dynamic Island com a
lanterna, o nome dele, o passo atual ("Pesquisando “voos”", "Abrindo github.com"), o detalhe, os
passos já feitos e o tempo desde a pergunta (contado pelo próprio sistema). Quando a resposta
chega, o cartão diz **"Respondeu"** com as primeiras palavras; se você estava no app, ele some na
hora; se não, fica 30 minutos.

| Peça | Onde |
|---|---|
| O que o cartão mostra (`VisaoTurnAttributes`), compilado no app e na extensão | `apps/ios/Shared/TurnActivity.swift` |
| O cartão e a Dynamic Island | alvo `VisaoLive` (`apps/ios/VisaoLive/`, id `<bundle id>.live`) |
| Começar, atualizar e encerrar | `apps/ios/Visao/LiveTurn.swift` |

**Com o Apple ID grátis o cartão é atualizado só pelo app**: enquanto ele está na tela e, depois
que você sai ou bloqueia, pelos cerca de 30 segundos que o iPhone dá a um app (uma background
task). Nesse tempo o app continua perguntando o passo e fecha o cartão com a resposta se ela
chegar. Uma resposta mais demorada deixa o cartão no último passo, com o tempo correndo, até você
voltar ao app (ou o cartão ficar velho, 10 minutos depois). O aviso do servidor continua como
antes: quando o app para de consultar, ele manda a notificação.

Para desligar: Ajustes do iPhone → V.I.S.A.O. → Atividades ao Vivo.

#### O caminho por push, pronto e desligado

Para o cartão acompanhar até o fim com o app suspenso, o servidor precisa mandar cada passo e o fim
do turno ao APNs. O app já está preparado (`LiveActivityPush` em `LiveTurn.swift`): com
`VISAO_LIVE_ACTIVITY_PUSH = YES` no `Local.xcconfig`, ele pede o cartão com `pushType: .token` e
recebe o token do cartão. Falta:

1. **Conta paga** (Apple Developer): o entitlement `aps-environment` e uma chave APNs (.p8).
2. **Uma rota no servidor**, que não existe hoje e não foi criada: por exemplo
   `POST /live-activities` com `{"conversation_id", "token"}`, guardando o token do cartão.
3. **O servidor mandar o push**: em `core/conversation/progress.py`, a cada `progress.step(...)` e no
   fim do turno, um push `liveactivity` para esse token com o mesmo `ContentState` (`steps`,
   `detail`, `done`, `excerpt`, `failed`), e `event: end` no fim.

Até lá o token não é mandado para lugar nenhum.

### Revisão pelas diretrizes da Apple

Revisado com a skill [dickwu/apple-design-skill](https://github.com/dickwu/apple-design-skill)
(as páginas das Human Interface Guidelines, lidas direto do repositório, sem instalar):

- **Reduzir Transparência** (Ajustes do iPhone → Acessibilidade): nenhum vidro; toda superfície
  vira opaca (`Palette.adapted`).
- **Aumentar Contraste**: texto secundário e linhas mais fortes.
- **Alvos de toque** de 44 pt em tudo que se toca (o × de "Respondendo a…" tinha 26 pt, abaixo do
  mínimo de 28); o desenho continua do mesmo tamanho.
- **Contraste**: a nota "Nada roda sem o seu toque." passou de 4,1:1 para 5,9:1. Os outros pares
  medidos passam de 4,5:1 (texto 14:1, secundário 5,3:1 de dia e 6:1 à noite).
- **Liquid Glass só nos controles** (barra, pílula, campo, botões, gaveta); a orbe grande da
  ligação e a do login são conteúdo e usam material comum.
- Desvio mantido de propósito: as abas ficam numa pílula no topo, como no web, e não numa barra
  de abas embaixo, como a HIG recomenda.

O sotaque da Kokoro é **neutro**: o "r" forte é um h suave (não o x carioca) e o "r" no meio da
palavra continua um toque leve.

### Câmera na ligação

O botão de **câmera** na tela da ligação liga a câmera de trás (troca para a da frente na
janelinha). Com ela ligada, **cada frase que você fala vai com uma foto do momento**
(`CallCamera.swift`): a imagem é reduzida a 1568 px, sobe como anexo (`/attachments`) e vai com a
frase, como uma foto mandada no chat. Se o envio da foto falhar, a frase vai sem ela.

- Só vídeo, sem áudio, e sem mexer na sessão de áudio da ligação.
- Só pelo botão, só durante a ligação; desliga quando a ligação acaba ou o app sai da tela.
- Ele só enxerga se o servidor tiver um modelo com visão (`VISION_LLM_MODEL`, ver
  [ANEXOS.md](ANEXOS.md)); cada foto reserva cerca de 1600 tokens no orçamento.

### Pendências da voz (para retomar)

- **Interromper falando ainda não interrompe.** O áudio em via dupla já liga e ouve (diário de
  14/11, 11:36: motor religado, frases reconhecidas), mas falar por cima enquanto ele fala ainda
  não o para. Próximo passo: registrar no diário o que o reconhecimento recebe durante a fala dele
  (hoje o diário só escreve quando ele está ouvindo), para saber se a sua voz chega ou se o
  cancelamento de eco a engole. O diário fica em `Library/Caches/diario-da-voz.txt` no app e se lê
  pelo cabo:
  `xcrun devicectl device copy from --device <id> --domain-type appDataContainer --domain-identifier io.github.allisonfreittass.visao --source Library/Caches/diario-da-voz.txt --destination diario.txt`
- **Atraso até ele começar a falar.** Medido em 14/11 (diário): 5,2 s do fim da sua fala até a voz,
  quase tudo esperando o servidor, que fazia três chamadas ao modelo uma atrás da outra: a avaliação
  de curiosidade, a resposta inteira e a conferência das regras. Nas ligações (`modality=voice`)
  agora:
  - a avaliação de curiosidade e a conferência das regras são puladas (as regras seguem no prompt
    de sistema; no chat por texto nada mudou);
  - a resposta é escrita em pedaços (streaming do provedor Anthropic) e o texto até ali aparece no
    campo `draft` do `/progress`, que o app pergunta a cada 0,3 s durante a ligação;
  - cada frase que termina vai para a voz na hora (`DraftReader` em VisaoKit); quando a resposta
    final chega, ele fala só o que faltou. Falar por cima ou tocar para parar descarta o resto.
  O diário mostra "primeira frase escrita X s depois" e "resposta inteira chegou X s depois". O
  provedor compatível com OpenAI ainda responde inteiro (sem rascunho), como antes.

## O que depende da conta paga (Apple Developer, US$ 99/ano)

| | Apple ID grátis | Conta paga |
|---|---|---|
| Rodar no seu iPhone pelo cabo | sim, reinstalando a cada 7 dias | sim, perfil de 1 ano |
| TestFlight / App Store | não | sim |
| Avisos por push (APNs) com o app fechado | não | sim |
| Live Activity atualizada pelo servidor (push) | não; só pelo app, enquanto está na tela e uns 30 s depois | sim, com a rota no servidor (etapa 7) |

Sem a conta paga, o aviso "terminou" com o app fechado continua chegando pelo PWA (Web Push).
