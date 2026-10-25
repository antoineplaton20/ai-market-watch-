# Études reproductibles (R5.1, 25 octobre 2026)

Chaque chiffre cité dans `LISEZMOI.md` et `PROMPT_MAITRE.md` sur ces sujets sort de ces scripts. Rien n'est ajusté
après coup ; chaque variante essayée est listée.

| Script | Données | Commande (depuis `armee-or/`) |
|---|---|---|
| `regle_r4.py` : la règle de la démo R4 (sa propre fonction `signal`) rejouée trade par trade | PAXGUSDT 15 min 2021-2026, livré dans `donnees_initiales/binance` | `.venv/bin/python etudes/regle_r4.py donnees_initiales/binance .` |
| `variantes.py` : peut-on rendre chaque trade gagnant ? 8 variantes de la règle des 200 jours | 34 marchés Yahoo 2000-2026 (non livrés : usage personnel) | `.venv/bin/python etudes/variantes.py DOSSIER_YAHOO . etudes` |
| `recherche_r6.py` : les 10 règles publiées de la recherche R6, mêmes conditions | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/recherche_r6.py DOSSIER_YAHOO . etudes` |
| `robustesse_r6.py` : le momentum 12 mois face aux frais, aux familles, à 200 sous-paniers, par périodes de 5 ans | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/robustesse_r6.py DOSSIER_YAHOO . etudes` |
| `or_seances.py` : l'or selon les séances (Asie, New York) | PAXGUSDT 15 min 2021-2026, livré | `.venv/bin/python etudes/or_seances.py donnees_initiales/binance` |
| `grands_r61.py` : méthodes publiques de CFM, Bridgewater, Millennium/Citadel, et 10 marchés de plus | 34 marchés + 10 marchés Yahoo (Asie, Europe, obligations US) | `.venv/bin/python etudes/grands_r61.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA . etudes` |
| `robustesse_r61.py` : le risque égal par famille sans cryptos, sans forex, frais, 200 sous-paniers, périodes | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/robustesse_r61.py DOSSIER_YAHOO . etudes` |

Résultats du 25/10/2026 :

- règle R4 : 2 783 trades, 44 % gagnants, −0,04 R par trade (perdante 2021-2024, +0,07 R en 2025, +0,06 R en 2026) ;
- R6 : momentum 12 mois +0,38 / +0,66 (stop 5 ATR compris) contre +0,08 / +0,46 pour le naïf, seul candidat retenu sur 13 essais (détail : `PROMPT_MAITRE.md` §5, fiches H27 à H39) ;
- R6.1 : risque égal par famille (Bridgewater) → momentum +0,51 / +0,92, règle 200 jours +0,47 / +0,83, naïf +0,37 / +0,77 ; CFM acheteur seul et 44 marchés rejetés ; limite de perte à la Millennium mesurée (fiches H40 à H43) ;
- règle des 200 jours (l'équipe multi-marchés) : 22 % de trades gagnants, Sharpe +0,35 / +0,52 sur les deux moitiés ;
- forcer 70 à 81 % de trades gagnants (prise de gain à 0,5 ou 1 ATR) : Sharpe nul ou négatif ;
- 90 à 97 % de trades gagnants en ne fermant jamais à perte : pertes cachées dans les positions restées ouvertes
  (jusqu'à −310 % de la mise d'un marché), positions bloquées jusqu'à 18 ans, pire baisse −28 à −31 %.
