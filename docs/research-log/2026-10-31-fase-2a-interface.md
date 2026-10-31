# 2026-10-31: Fase 2a (interface web e bolha)

## Feito

- `apps/web` (React 18.3.1, Vite 5.4.21, TypeScript 5.9.3, Vitest 2.1.9): login, lista de
  conversas, conversa por texto, interruptor de memória, verificação de saúde a cada 15 s.
- Bolha de partículas laranja em canvas, com os seis estados da seção 12. Modelo matemático
  separado (`orbModel.ts`) e testado; demonstração em `?orb=demo`.
- Primeira versão parecia uma "bola de golfe" (grade de Fibonacci regular). Ajustes:
  deslocamento determinístico das partículas, tamanhos variados, mistura aditiva e camada
  interna.
- CI ganhou o job `web` (typecheck, testes, build).

## Verificado

| Verificação | Resultado |
|---|---|
| `tsc --noEmit`, `vitest` | 10 testes passando |
| `vite build` | ~153 kB JS (~50 kB gzip) |
| Navegador (painel do app, 800 px): login com usuário de desenvolvimento, envio de mensagem | bolha em "pensando" durante a chamada, volta a "ocioso"; resposta do LLM real via reserva NVIDIA |
| Estados na demonstração | ocioso, pensando, falando conferidos visualmente |

Não verificado: iPhone/Safari real, desempenho do canvas em celular antigo, leitor de tela.

## Observação

Durante o teste no navegador, a pessoa responsável também digitava no mesmo campo; a primeira
mensagem enviada saiu misturada. Não é defeito da interface.
