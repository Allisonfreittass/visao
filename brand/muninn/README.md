# Muninn

A forma atual do Visão: o corvo da memória de Odin. Regras de uso em [DESIGN.md](../../DESIGN.md#5-o-muninn).

| Arquivo | O que é |
|---|---|
| `muninn-lineart.png` | Ilustração mestre: traço branco sobre preto, 1254 × 1254. |
| `trace.py` | Extrai os traços da ilustração para a animação de gênese. |
| `strokes.json` | Gerado por `trace.py` (1.965 traços, coordenadas 0..1000, ordem de desenho). |
| `muninn_ascii.py` | A gênese em ASCII no terminal. Só biblioteca padrão; `--static` mostra o quadro final. |
| `muninn-ascii.json` | A grade 120 × 60 e a ordem de revelação, gerada por `ascii_build.py`. |
| `ascii_build.py`, `ascii_gif.py` | Refazem o JSON e o `muninn-ascii.gif` (README) a partir da ilustração. |

```bash
pip install opencv-python scikit-image numpy
python brand/muninn/trace.py
```

Como funciona: binariza a imagem, reduz os traços a esqueleto de 1 px, percorre o esqueleto entre
pontas e cruzamentos, simplifica cada trecho (Douglas-Peucker, 1 px) e ordena pela distância ao
peito. Trocar a ilustração e rodar de novo atualiza a animação sem mexer em código.

```bash
python brand/muninn/muninn_ascii.py              # toca a gênese em ASCII
python brand/muninn/ascii_build.py --gif         # refaz o JSON e o GIF (opencv, pillow, fonttools, brotli)
```
