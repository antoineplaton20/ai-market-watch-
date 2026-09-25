# Les 3 portes et la lecture des bougies (v17.5)

## Les 5 rôles, dans notre code

| Rôle | Où | Ce qu'il fait |
|---|---|---|
| 1. Hypothèse | `strategie.py` (9 espèces, chacune avec son mécanisme) | propose une idée avec une raison économique |
| 2. Code | `backtest.py`, `evolution.py`, `simulation.py` | signal décalé d'une bougie, frais + glissement, stop-limite réaliste |
| 3. Critique | `tests/test_portes.py` (lancé à chaque `bots verifier` et à chaque mise à jour) | change TOUT le futur et vérifie que rien de ce que les bots voyaient avant ne bouge |
| 4. Statisticien | `surapprentissage.py`, `backtest.portes()` | Sharpe dégonflé selon le nombre d'essais, PBO, barre anti-chance |
| 5. Risque | `gardien.py`, Monte-Carlo de l'évolution | 1 % du capital risqué par trade, -5 % par jour au maximum, pire baisse probable ≤ 10 % |

## Les 3 portes avant tout argent réel

1. **Le critique ne trouve aucune fuite du futur.** C'est un test automatique ; la mise à jour est refusée
   s'il échoue.
2. **Le Sharpe dégonflé est d'au moins 95 %.** Quand on compare 3 unités de temps, la barre monte avec le
   nombre d'essais.
3. **Le walk-forward reste positif** sur 3 fenêtres successives : apprendre sur le passé, être jugé sur la
   période suivante.

`bots backtest` affiche maintenant les portes, les fenêtres et les régimes de marché (hausse / baisse) de
chaque période. Une unité de temps n'est recommandée que si elle passe les portes.

## Corrections du backtest (revue en 8 points)

- **Univers complet par défaut**, cryptos disparues comprises : plus de biais du survivant.
- **Stops simulés avec 0,25 % de glissement**, au lieu de 0,05 %. Le vrai stop est un stop-limite posé 0,5 %
  sous le déclenchement.
- **Stop « sécurisé » plus haut**, en réel comme en backtest : il couvre frais + glissement, donc un gagnant ne
  redevient pas perdant.
- **Le choix de l'unité 15m / 1h / 4h** n'est plus « la meilleure sur la période de test ». Elle doit passer les
  portes, avec la correction pour 3 essais.
- **Rapport des régimes de marché** pour chaque fenêtre.

## Bougies japonaises : 14 figures

- **Rebond, après une baisse :** marteau, avalement haussier, étoile du matin, ligne pénétrante, trois soldats
  blancs, harami haussier, doji libellule.
- **Chute, après une hausse :** étoile filante, avalement baissier, étoile du soir, nuage noir, trois corbeaux,
  harami baissier, pendu.

Les failles de lecture, et comment on s'en protège (détails dans `moteurs/chandeliers.py`) :

- **Bougie pas encore fermée** : on ne lit que des bougies fermées.
- **Figure sortie de son contexte** : on exige la tendance qui précède.
- **Figure sans confirmation** : l'option confirmation exige que la bougie suivante clôture au-dessus du plus
  haut de la figure.
- **Figure sans volume** : option volume.
- **Trous d'ouverture** : ils n'existent presque pas en crypto, les définitions sont adaptées.
- **Petite unité de temps** : beaucoup de fausses figures.

Où elles servent :

- **L'évolution** a une 9e espèce, CHANDELIERS. Elle ne trade que si elle passe le coffre-fort, la barre
  anti-chance, le PBO et le Sharpe dégonflé.
- **Aucune espèce n'achète sur une figure de chute.**
- **La veille marchés** ajoute la lecture de la bougie d'hier dans chaque fiche (`/note`).

### Premier test honnête (BTC, ETH, SOL, septembre 2024 → août 2026, frais et glissement compris)

Sur 32 essais (2 unités × 8 figures × avec ou sans confirmation), **aucune figure ne passe les portes** :

| Figure | Unité | Période d'apprentissage (80 %) | Période jamais vue (20 %) |
|---|---|---|---|
| Trois soldats blancs, confirmée | 4h | +0,49 R (12 trades) | +0,01 R |
| Toutes les figures de rebond, sans confirmation | 1h | -0,39 R | -0,44 R |

Les figures sont fréquentes (plus de 2 000 marteaux en 1 h sur 2 ans), mais seules, elles ne battent pas les
frais. L'évolution les combinera avec les votes de l'équipe et les stops. Ce sont les portes qui décident.

À comparer : l'équipe actuelle du bot principal sur les mêmes données, en walk-forward, donne -0,82 R (15m),
-0,50 R (1h) et -0,25 R (4h). Aucune unité ne passe les portes, ce qui est cohérent avec l'absence d'avantage
constatée depuis le début.

## Ce qui n'a PAS été fait, volontairement

- **« Rattraper le manque de bénéfice »** : augmenter la mise après des pertes (martingale) est la façon la plus
  sûre de vider un compte. Le risque par trade reste fixe, quoi qu'il arrive.
- **« Arbitrage à la vitesse pure, prix synchronisés chaque seconde, erreurs de prix entre des dizaines de
  marchés »** : les écarts de prix sur Binance sont corrigés en millisecondes par des firmes installées à côté
  des serveurs de la bourse. Un serveur à Nuremberg, avec 0,1 % de frais par ordre, arrive toujours après
  elles, et l'écart est plus petit que les frais. Il faudrait aussi des comptes approvisionnés sur plusieurs
  plateformes. Le bot principal scanne déjà toutes les paires USDT de Binance (plusieurs centaines) à chaque
  bougie, et surveille ses positions toutes les 20 s.
