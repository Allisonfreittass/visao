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

iOS 17 ou mais novo, Swift 6, Observation, async/await e URLSession. Sem dependências de terceiros.

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
decisão recusada pelo servidor não some nem é dada como feita.

## O que o app tem

### Etapa 1: conversa

- **Login** com e-mail e senha; o token fica no **Keychain** (só este aparelho, depois do primeiro
  desbloqueio), nunca em UserDefaults. Um 401 em qualquer chamada volta para o login.
- **Conversas**: a lista do servidor (rotulada pela data, como no web), puxar para atualizar e
  nova conversa. A conversa só é criada no servidor com a primeira mensagem.
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
- **Noite**: o tema escuro liso da marca. A aparência e "Neblina em movimento" ficam no menu da
  conta (ícone de pessoa na lista de conversas) até a etapa de Ajustes.
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
- Na conversa de onde o pedido veio, o cartão fica embaixo das mensagens. Na lista de conversas, o
  bloco **"Esperando você"** junta todos, inclusive os que não são de nenhuma conversa, com um
  atalho para abrir a conversa.
- O toque vai com `?via=toque` (a ligação da etapa 5 usa `via=voz`), e o servidor registra no
  audit. Se o servidor recusar (já decidido, expirado), o cartão continua e o motivo aparece; o app
  nunca diz que foi feito antes da resposta do servidor. Depois de aprovar um email ou evento, a
  mensagem dele dizendo o que fez aparece na conversa.
- A lista de pedidos é atualizada ao abrir, depois de cada resposta e a cada 15 s com o app na
  frente.

## O que depende da conta paga (Apple Developer, US$ 99/ano)

| | Apple ID grátis | Conta paga |
|---|---|---|
| Rodar no seu iPhone pelo cabo | sim, reinstalando a cada 7 dias | sim, perfil de 1 ano |
| TestFlight / App Store | não | sim |
| Avisos por push (APNs) com o app fechado | não | sim |
| Live Activity atualizada pelo servidor (push) | não; só atualização local, com o app aberto | sim |

Sem a conta paga, o aviso "terminou" com o app fechado continua chegando pelo PWA (Web Push).
