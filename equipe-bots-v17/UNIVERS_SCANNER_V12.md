# Scanner universel — V12

Cette couche ajoute un registre unifié Binance / Trade Republic et un scanner de tradabilité.

- Binance : découverte via `ccxt.load_markets()` et conservation des règles de marché.
- Trade Republic : ingestion d'un CSV/JSON d'univers fourni depuis une source autorisée. Le projet ne fabrique pas d'API privée et ne prétend pas exécuter automatiquement des ordres TR.
- Tous les instruments passent par la même chaîne : découverte → qualité → liquidité/spread → MTF → coûts → risque → exécution.
- Le contrôle de corrélation permet de détecter plusieurs positions qui représentent essentiellement le même risque.

Exemple CSV TR :

```text
symbol,kind,currency,active,min_order,fixed_fee
DE000...,stock,EUR,true,1,1
IE00...,etf,EUR,true,1,1
```

Le registre peut ensuite être exporté en JSON pour audit.

## Branchement dans le bot (V12.1)

| Module | Où il agit | Effet |
|---|---|---|
| `InstrumentRegistry` | début de chaque scan (`equipe.scout`) | liste les marchés Binance **spot** actifs (futures, marges et options ignorés) |
| `UniversalScanner` | juste après, avant le FILTRE | écarte inactifs, sans cotation, volume trop faible, spread trop large, paires exclues ; les survivants sont classés par volume |
| `correlation_engine` | veto dur CORRÉLATION (`equipe.correlation`) | refuse une position corrélée à plus de 0,85 (rendements 1 h) avec une position ouverte ; une corrélation négative n'est pas bloquée |
| Univers Trade Republic | registre, en suivi | fichier `univers_trade_republic.csv` (ou `UNIVERS_TR_FICHIER`) dans le dossier du bot : compté dans `/univers`, **jamais tradé** |

Commande Telegram : **/univers** → nombre de marchés vus, tradables, analysés, et rejets par motif.

Corrections faites au passage :
- depuis la v11, une position ouverte faisait planter l'analyse de toutes les autres paires (cache 1 h vide) : le bot ne pouvait jamais ouvrir de deuxième position ;
- depuis la v11, les caractéristiques `sup1` et `MULTI_UNITES` n'étaient plus calculées comme dans le backtest : l'espèce qui exige `sup1 == 1` ne se déclenchait jamais en direct. Elles reprennent la définition du backtest ; la porte MTF 4/4 de la v11 reste appliquée à part avant tout achat.
