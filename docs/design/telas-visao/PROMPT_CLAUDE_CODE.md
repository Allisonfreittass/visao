# Prompt para o Claude Code: implementar as telas do VISAO

Copie tudo abaixo da linha e cole no Claude Code, na raiz do repositório.

---

Quero que o app web (`apps/web`) fique igual ao mockup em `docs/design/telas-visao/`. Antes de mexer em código, leia nesta ordem:

1. `docs/design/telas-visao/README.md` (regras visuais e como navegar).
2. `docs/design/telas-visao/mapa-de-funcionalidades.html` (lista de funcionalidades e em que tela cada uma aparece).
3. Abra `prototipo-computador.html` e `prototipo-celular.html` no navegador e clique em tudo. Os prints em `telas/` são a referência de pixel.
4. `DESIGN.md`, `PRODUCT.md` e os componentes atuais: `App.tsx`, `components/Rail.tsx`, `SkyNav.tsx`, `ChatView.tsx`, `InboxView.tsx`, `MacView.tsx`, `PanelsBoard.tsx`, `ProjectsView.tsx`, `SettingsView.tsx`, `CallView.tsx`, `Login.tsx`, `Onboarding.tsx`, `brand/tokens.css`, `brand/theme.ts`.

O HTML do mockup é referência visual, não código para copiar: implemente em React com os tokens e componentes do projeto.

## Identidade (vale para tudo)

- Ícone: o corvo no eclipse (`assets/icone-grande-512.png` acima de 72 px e `icone-pequeno-256.png` abaixo). Ele é o avatar das mensagens dele, o logo da barra lateral e o ícone do PWA. Gere os tamanhos do manifest e o favicon a partir dele (`brand/generate_assets.py`).
- Selo: campo âmbar com "VISAO" em Six Caps preenchendo o quadrado atrás do busto em xilogravura. Só no login e em material de marca.
- Âmbar `#E39A2E` é só dele (eclipse, filete dos pensamentos, pedido de aprovação, ponto de atividade pulsando, aviso de versão). Botões comuns nunca são âmbar.
- Fontes: Geist (interface), Geist Mono (dados, horários, status), Newsreader 300 itálico (a fala dele), Six Caps (só o nome VISAO). Sirva as fontes localmente (os arquivos estão em `assets/fonts`).
- Três temas, trocados na hora em Ajustes › Aparência: Papel (claro), Tinta (escuro) e Rótulo (creme `#F3E9D2` e azul `#1D2B4F`). Os valores de cada tema estão no objeto `THEMES` do script de `prototipo-computador.html`; leve-os para `brand/tokens.css` como variáveis CSS.
- Atualize o `DESIGN.md` com esta identidade e marque o que sai (o anel e o que mais o mockup não usa). Não apague a gênese do Muninn sem me perguntar.

## Ordem de trabalho

Faça uma etapa por vez. No fim de cada uma, rode `ruff`, os testes do web e o build, e me mostre um print comparado com o PNG de referência antes de seguir.

1. **Base:**
   - tokens e temas;
   - fontes;
   - ícones;
   - estrutura de janela: barra lateral, área principal e barra de status no rodapé.
2. **Barra lateral:**
   - logo;
   - Nova conversa e lupa;
   - navegação: Início, Chat, Projetos, Caderno, Rotinas, Mac, Agentes, Canais, Habilidades;
   - conversas Fixadas e Recentes;
   - cartão de versão nova;
   - usuário e Ajustes.
3. **Barra de status:** servidor, Braço, rotinas, silêncio, tokens e custo do dia, modelo. Clicar no modelo abre a troca de modelo. Use os dados reais que a API já expõe.
4. **Login e Primeira vez:** o login com o selo, e o fluxo de 4 passos (modelo, memória, Mac, silêncio). Reaproveite o `Onboarding.tsx`.
5. **Início:** saudação, pensamento dele, pedido de aprovação com o carimbo "APROVADO", cartão do painel e compositor com atalhos.
6. **Chat:**
   - passos das ferramentas recolhidos em cartões, com modo Resumido ou Técnico;
   - ponto âmbar de atividade no compositor;
   - painel "Agora / O que fiz de verdade";
   - ler em voz alta;
   - compartilhar com link privado, Markdown e PDF, mais o aviso de confirmação (veja `docs/COMPARTILHAR.md`).
7. **Paleta de comandos:** Ctrl/⌘+K, com busca de conversas e projetos e as ações do mockup.
8. **Caderno:**
   - abas Memória (com origem e Esquecer), Pensamentos, Interesses (barras que esfriam), O nome e Autorretrato;
   - consulte `docs/AUTONOMOUS_NAMING.md` e `docs/SELF_KNOWLEDGE.md`.
9. **Rotinas, Mac, Painel, Projetos e Ajustes:**
   - Rotinas: interruptores e horário de entrega;
   - Mac: log ao vivo;
   - Painel: gráfico com a linha da meta;
   - Ajustes: busca e seções.
10. **Ligação:** fundo tinta, corvo no eclipse grande, legenda do que ele está fazendo e Desligar.
11. **Celular:** abas embaixo (Início, Chat, Caderno, Rotinas) e o microfone abrindo a ligação.
12. **Funcionalidades sem backend ainda:**
    - quais são: Agentes em paralelo, Canais (Telegram, WhatsApp, e-mail, Discord), Habilidades que ele propõe, Autorretrato e o aviso de atualização (use `docs/NOVIDADES.md`);
    - antes de codar, me diga o que já existe no backend para cada uma;
    - o que não existir: faça a tela com estado vazio honesto ("ainda não disponível") e abra uma issue por funcionalidade, com o que a API precisa expor;
    - não invente dados na interface.

## Regras

- Não mude nada de backend, banco ou migração sem me perguntar.
- Nada roda no Mac sem aprovação: mantenha o fluxo de aprovação atual.
- Acessibilidade:
  - toda ação tem um botão de verdade, com nome acessível;
  - interruptores com `role="switch"`;
  - contraste AA nos três temas;
  - foco visível;
  - `prefers-reduced-motion` desliga o pulso âmbar.
- Commits pequenos por etapa, em português, numa branch `design/telas-visao`.
