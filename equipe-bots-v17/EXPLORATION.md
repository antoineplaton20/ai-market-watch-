# Mode EXPLORATION (v14) — compte démo uniquement

Un bot qui n'achète jamais n'apprend rien. En démo, l'argent est fictif : l'équipe prend volontairement plus
de risques pour que des transactions aient lieu, et **chaque risque pris est mesuré**.

## Verrou
Niveau 0 forcé dès que `MODE` n'est pas `demo` (ou `testnet`), deux vérifications indépendantes. En argent réel,
seul le champion strict trade, exactement comme avant.

## Niveaux (Telegram : `/exploration 0|1|2|3`)

| | 1 prudent | 2 normal (défaut) | 3 agressif |
|---|---|---|---|
| Vote exigé | seuil − 0,10 | seuil − 0,15 | seuil − 0,25 |
| Unités favorables (4h/1h/15m/5m) | 3/4 | 2/4 | 0/4 |
| Espèce du champion | exigée | libre | libre |
| Coûts | potentiel net ≥ 0 | notés, pas bloquants | notés, pas bloquants |
| Vetos durs (baleines, corrélation, recherche, IA) | respectés | respectés | ignorés |
| Pump > 40 % en 24 h | refusé | refusé | autorisé |
| Liquidité minimale | stricte | stricte | x0,2 (spread x2) |
| Positions d'exploration max | 1 | 2 | 3 |
| Achats d'exploration / jour | 4 | 8 | 15 |
| Garantie d'activité | — | 1 achat / 4 h (score ≥ 45 %) | 1 achat / h (score ≥ 35 %) |
| Budget de perte / jour | 5 % | 10 % | 20 % |

Toujours : stop posé chez Binance, veto VEILLE (piratage, délisting…), données fraîches, historique suffisant,
risque par trade 0,5 % (moitié d'un trade strict), coupe-circuit de l'exploration à −40 % du capital.

## Ce qui apprend
- Chaque trade porte ses « risques pris » (ex. `VOTE_FAIBLE`, `MTF_2/4`, `ANTI_HYPE`, `COUTS`, `GARANTIE`).
- Les notes /10 des votants se remplissent avec ces vrais résultats ; celles des vetos comparent les trades pris
  **malgré** le veto aux trades qui l'ont respecté.
- `/exploration` : résultat moyen de chaque risque pris (payant / neutre / coûteux).

## Ce qui n'est PAS touché par l'exploration
Le disjoncteur, les niveaux de risque, la limite de perte du jour et les paliers de capital ne jugent que les
trades **stricts** du champion : une mauvaise série d'exploration ne coupe pas le champion, et une bonne série
ne peut pas te proposer d'augmenter le capital.

## Scan de toutes les paires
`SCOUT_MAX=0` : toutes les paires USDT tradables (≈ 400) sont examinées à chaque bougie de signal, les plus
échangées d'abord. Les positions restent surveillées pendant le scan (toutes les 20 s). Un scan ne dépasse jamais
80 % d'une bougie : s'il est interrompu, le suivant reprend là où il s'était arrêté. La limite réelle est le
nombre de requêtes que Binance autorise par minute, pas la puissance du serveur.
