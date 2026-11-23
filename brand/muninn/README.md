# Muninn

A forma atual do Visão: o corvo da memória de Odin. Regras de uso em [DESIGN.md](../../DESIGN.md#5-o-muninn).

| Arquivo | O que é |
|---|---|
| `muninn-lineart.png` | Ilustração mestre: traço branco sobre preto, 1254 × 1254. **Adicionar à mão** (o PR que criou esta pasta não conseguia enviar binários). |
| `trace.py` | Extrai os traços da ilustração para a animação de gênese. |
| `strokes.json` | Gerado por `trace.py` (1.965 traços, coordenadas 0..1000, ordem de desenho). |

```bash
pip install opencv-python scikit-image numpy
python brand/muninn/trace.py
```

Como funciona: binariza a imagem, reduz os traços a esqueleto de 1 px, percorre o esqueleto entre
pontas e cruzamentos, simplifica cada trecho (Douglas-Peucker, 1 px) e ordena pela distância ao
peito. Trocar a ilustração e rodar de novo atualiza a animação sem mexer em código.
