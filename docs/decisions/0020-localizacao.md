# ADR-0020: Localização para "perto de mim", sem guardar e sem mostrar ao modelo

- Data: 2026-11-16
- Estado: aceita
- Completa: [ADR-0018](0018-compartilhar-do-iphone.md) (a outra metade da EDITH)

## Contexto

"Tem farmácia aberta aqui perto?" não tinha resposta: o Visão não sabia onde o dono estava, e
perguntar o bairro toda vez é o oposto da EDITH. Mas a posição do dono é o dado mais sensível que
o app poderia ter. Em 16/11/2026, um teste com o navegador do servidor num ponto público (Av.
Paulista) leu do Google Maps o nome, o endereço, "Aberto · Fecha 23:00" e o telefone de cada
farmácia.

## Decisão

- **Opcional e por aparelho.** "Usar minha localização" em Ajustes vem desligado. Ligar pede a
  permissão do sistema na hora, não no meio de uma pergunta.
- **Só sai do celular quando precisa.** O app manda a posição (`location`: lat, lon, precisão,
  hora) só com uma mensagem que parece pergunta de lugar perto. O servidor confere de novo em
  código (`core/location.py`) e, se não for, ignora a posição. "Perto do Natal", "daqui a pouco"
  e "perto de terminar" não contam.
- **O modelo nunca vê as coordenadas:**
  - o planejador só sabe que a posição existe (`perto_dela: true`) e devolve o que procurar
    (`nearby: ["farmácia"]`);
  - o código monta o endereço do Google Maps naquele ponto (zoom 15) e o navegador lê;
  - a resposta recebe os lugares lidos e a regra de nunca dizer coordenadas.
- **Nada guarda a posição:**
  - a mensagem fica sem ela;
  - a memória nunca a vê;
  - o registro do turno diz só `location_used` com a precisão em palavras;
  - o endereço guardado da página lida troca as coordenadas por `@local`.
- **Posição velha ou grosseira não é "aqui":** mais de 30 min ou precisão pior que 3 km é
  ignorada.
- **Sem posição numa pergunta de lugar perto:** ele pede o bairro ou a cidade e lembra que dá para
  ligar a localização.
- Vale no chat (`POST /conversations/{id}/messages`) e no compartilhar (`POST /share`).

## Fora desta decisão

- **Localização em segundo plano**, para avisar ao passar perto de algo: exige permissão
  "Sempre" e guardar a posição. Não.
- **Rotas e tempo de deslocamento:** o mapa aberto é a busca, não a rota.
- **Geocodificação reversa por terceiros** (Nominatim etc.): mandaria a posição para mais um
  serviço sem necessidade.
