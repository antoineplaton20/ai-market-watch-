# Études reproductibles (R5.1, 25 octobre 2026)

Chaque chiffre cité dans `LISEZMOI.md` et `PROMPT_MAITRE.md` sur ces sujets sort de ces scripts. Rien n'est ajusté
après coup ; chaque variante essayée est listée.

| Script | Données | Commande (depuis `armee-or/`) |
|---|---|---|
| `regle_r4.py` : la règle de la démo R4 (sa propre fonction `signal`) rejouée trade par trade | PAXGUSDT 15 min 2021-2026, livré dans `donnees_initiales/binance` | `.venv/bin/python etudes/regle_r4.py donnees_initiales/binance .` |
| `variantes.py` : peut-on rendre chaque trade gagnant ? 8 variantes de la règle des 200 jours | 34 marchés Yahoo 2000-2026 (non livrés : usage personnel) | `.venv/bin/python etudes/variantes.py DOSSIER_YAHOO . etudes` |

Résultats du 25/10/2026 :

- règle R4 : 2 783 trades, 44 % gagnants, −0,04 R par trade (perdante 2021-2024, +0,07 R en 2025, +0,06 R en 2026) ;
- règle des 200 jours (l'équipe multi-marchés) : 22 % de trades gagnants, Sharpe +0,35 / +0,52 sur les deux moitiés ;
- forcer 70 à 81 % de trades gagnants (prise de gain à 0,5 ou 1 ATR) : Sharpe nul ou négatif ;
- 90 à 97 % de trades gagnants en ne fermant jamais à perte : pertes cachées dans les positions restées ouvertes
  (jusqu'à −310 % de la mise d'un marché), positions bloquées jusqu'à 18 ans, pire baisse −28 à −31 %.
