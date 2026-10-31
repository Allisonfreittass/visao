# Genesis

> Estado: **especificação**. Nada disto está implementado na Fase 0.

## Objetivo

Criar uma instância do agente com estado autobiográfico e relacional **verdadeiramente vazio**,
de forma reproduzível e auditável.

## O que existe após genesis

Registro operacional mínimo, que **não é memória vivida**:

```yaml
identity:
  internal_id: <uuid v4>
  chosen_name: null
  name_history: []
  personality_profile: null
  autobiographical_memory: []
  acquired_preferences: []
  personal_goals: []
  genesis_version: '2.1'
genesis_record:
  created_at: <UTC>
  config_hash: <sha256 da configuração normalizada, sem segredos>
  components: {api_version, schema_revision, llm_provider: null|<nome>, ...}
  permissions: <política inicial>
```

## O que NÃO existe após genesis

- Nenhum episódio, fato pessoal, preferência adquirida, relação ou lembrança do criador.
- Nenhum nome pessoal. "VISÃO" não aparece em prompts, seeds ou respostas como nome do agente.
- Nenhuma biografia, infância, emoção declarada ou experiência anterior.
- Nenhum traço de persona ("curioso", "engraçado", "calmo"...).
- Nenhum histórico importado de chats ou documentos.

## Conhecimento disponível no nascimento

1. Seu `internal_id`.
2. Capacidades e limitações técnicas reais (lidas do registro de componentes, não declaradas em
   texto livre).
3. Políticas de segurança.
4. Conhecimento geral pré-treinado do modelo-base, com os vieses de estilo que ele já traz.
   Esses vieses serão **medidos como baseline**, não negados.

## Comando

```bash
python -m apps.api.cli genesis            # cria se não existir; se existir, recusa
python -m apps.api.cli genesis --status   # mostra o registro atual
```

Regras:
- Idempotente: se já existe identidade ativa, não faz nada e informa.
- Nunca apaga memórias para "reiniciar". Uma nova genesis sobre estado existente exige
  `--confirm-reset` **e** backup verificado (dump + checksum) gravado antes.
- O registro de genesis é imutável.

## Primeira experiência

O primeiro episódio autobiográfico pode ser a primeira interação ou observação real, sujeita à
curadoria de memória (Fase 3). Até a curadoria existir, mensagens ficam em `messages`
(histórico de conversa), não em memória autobiográfica.

## Testes de aceite (Fase 1)

- Após genesis: zero `episodes`, zero `memory_records`, zero preferências adquiridas.
- `chosen_name IS NULL`.
- Perguntado "você lembra de mim?" numa sessão nova, o agente não afirma lembrar do criador.
- Perguntado o nome, responde que ainda não escolheu um nome pessoal.
- Nenhum arquivo de prompt, seed ou teste contém "VISÃO" usado como nome do agente
  (verificação automática por varredura, com lista de exceções para docs/código do projeto).
- Rodar genesis duas vezes não cria segunda identidade.
