# Localização: "tem farmácia aberta aqui perto?"

Com **Ajustes > Localização > Usar minha localização** ligado, perguntas sobre lugares perto de
você ("tem farmácia aberta aqui perto?", "qual o posto mais perto?", "algum restaurante bom por
aqui?") vão com a posição do celular. Ele abre o Google Maps onde você está e responde com o
nome, o endereço e se o lugar está aberto e até quando
([ADR-0020](decisions/0020-localizacao.md)).

## Privacidade

| Pergunta | Resposta |
|---|---|
| Quando a posição sai do celular? | Só com a chave ligada e numa mensagem de "perto de mim" |
| O servidor guarda? | Não: nem na mensagem, nem na memória, nem no registro do turno; o endereço da página lida fica com `@local` no lugar das coordenadas |
| O modelo (Anthropic) vê? | Não. O planejador só sabe que ela existe e diz o que procurar; o código monta o mapa |
| E o Google? | Sim: o navegador do servidor abre o Maps naquele ponto, como você abriria |
| Posição antiga? | Mais de 30 min ou precisão pior que 3 km é ignorada |

## API (por acréscimo)

`POST /conversations/{id}/messages` e `POST /share` aceitam:

```json
{ "location": { "lat": -23.5614, "lon": -46.6559, "accuracy_m": 35, "at": "2026-11-16T20:00:00Z" } }
```

`accuracy_m` e `at` são opcionais. O servidor só usa a posição quando a mensagem é sobre um lugar
perto. O app não precisa acertar a regra: ela é conferida de novo no servidor. Mas o app só deve
mandar a posição com a chave ligada e numa mensagem parecida com isso, para ela não sair do
celular à toa. No web, a regra está em `apps/web/src/location.ts`; no servidor, em
`core/location.py`.

## No iPhone

- A chave em Ajustes pede `CLLocationManager.requestWhenInUseAuthorization()` ao ser ligada e
  fica em `UserDefaults`.
- Numa mensagem de "perto de mim", o app pede uma posição com `requestLocation()`
  (`kCLLocationAccuracyHundredMeters`, até ~4 s) e a manda junto. Sem posição a tempo, a mensagem
  vai sem ela.
- `Info.plist`: `NSLocationWhenInUseUsageDescription` = "Para achar lugares perto de você quando
  você pergunta, como uma farmácia aberta. A posição vai só com essa mensagem e não fica
  guardada."
