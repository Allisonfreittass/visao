# App do iPhone (SwiftUI)

O cliente nativo do iPhone fica em `apps/ios/`. Ele fala com a **mesma API** do web (FastAPI atrás
do Caddy, em `/api`); nada no servidor muda por causa dele.

| Pasta | O que tem |
|---|---|
| `apps/ios/VisaoKit/` | Pacote Swift com o que dá para testar sem tela: cliente da API, tipos, Keychain, a fila de envio do chat e o Markdown. Testes em XCTest. |
| `apps/ios/Visao/` | As telas em SwiftUI (login, conversas, chat). A pasta é sincronizada com o projeto: arquivo novo aqui entra no app sozinho. |
| `apps/ios/Config/` | `Visao.xcconfig` (no git), `Local.xcconfig` (seu, fora do git) e o `Info.plist`. |
| `apps/ios/Visao.xcodeproj` | O projeto do Xcode. |

iOS 17 ou mais novo, Swift 6, Observation, async/await e URLSession. Sem dependências de terceiros.

## Antes da primeira vez

1. **Termine a instalação do Xcode.** Se o Xcode nunca foi aberto neste Mac (ou foi atualizado),
   rode uma vez, com a sua senha:

   ```bash
   sudo xcodebuild -runFirstLaunch
   ```

   Sem isso o `xcodebuild` e o simulador não carregam (`CoreSimulator.framework` não encontrado).
   Abrir o Xcode e aceitar a instalação de componentes faz o mesmo.

2. **Entre com o seu Apple ID no Xcode**: Xcode → Settings → Accounts → +. Anote o *Team ID* do
   "Personal Team".

3. **Crie o seu `Local.xcconfig`:**

   ```bash
   cp apps/ios/Config/Local.example.xcconfig apps/ios/Config/Local.xcconfig
   ```

   e preencha:

   | Chave | O que é |
   |---|---|
   | `VISAO_BUNDLE_ID` | Id único do app. Com Apple ID grátis, o Xcode recusa um id que outra pessoa já registrou. |
   | `VISAO_DISPLAY_NAME` | O nome embaixo do ícone. |
   | `VISAO_DEVELOPMENT_TEAM` | O Team ID do passo 2. |
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
Markdown (código sem fechar, só links http/https, HTML como texto).

## O que tem nesta etapa

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
- **Dynamic Type** (só estilos de texto do sistema, nada de tamanho fixo), **modo escuro** pelas
  cores do sistema, VoiceOver com ação "Responder".

As próximas etapas (fotos e arquivos, páginas, cartões de aprovação, projetos e ajustes, ligação
por voz, o céu de pinheiros e Live Activity) entram aqui à medida que forem feitas.

## O que depende da conta paga (Apple Developer, US$ 99/ano)

| | Apple ID grátis | Conta paga |
|---|---|---|
| Rodar no seu iPhone pelo cabo | sim, reinstalando a cada 7 dias | sim, perfil de 1 ano |
| TestFlight / App Store | não | sim |
| Avisos por push (APNs) com o app fechado | não | sim |
| Live Activity atualizada pelo servidor (push) | não; só atualização local, com o app aberto | sim |

Sem a conta paga, o aviso "terminou" com o app fechado continua chegando pelo PWA (Web Push).
