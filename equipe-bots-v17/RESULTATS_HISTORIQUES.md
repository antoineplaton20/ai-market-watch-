# Résultats historiques — révision du 25 septembre 2026

**Verdict : les corrections réduisent fortement les pertes dans cette expérience, mais la dernière tranche reste déficitaire sur les trois actifs. Rentabilité non démontrée ; aucun passage au réel justifié par ces résultats.**

Collecte achevée : 96 archives mensuelles, 280,512 bougies de 15 minutes, zéro fichier rejeté. BTCUSDT, ETHUSDT, SOLUSDT ; janvier 2024 à août 2026. SHA-256 vérifiés et provenance incluse.

## Derniers 30 % de chaque historique

Comptes fictifs indépendants de 1 000 USDT ; toutes les performances ci-dessous sont après frais et glissement simulés. Aucun résultat ne doit être additionné comme s’il s’agissait d’un seul portefeuille.

| Actif | Votes d’origine, coûts de base | Votes corrigés, coûts de base | Votes corrigés, coûts doublés | Baisse max. corrigée, base | Allers-retours origine → corrigé |
|---|---:|---:|---:|---:|---:|
| BTCUSDT | -22.80 % | -1.87 % | -2.96 % | 4.23 % | 684 → 39 |
| ETHUSDT | -24.16 % | -2.56 % | -4.43 % | 4.46 % | 715 → 67 |
| SOLUSDT | -22.53 % | -1.19 % | -3.54 % | 5.35 % | 687 → 84 |

Dernière tranche : du 2025-11-12T19:00:00+00:00 au 31 août 2026 inclus. Les dates exactes figurent dans le JSON.

Le filtre d’intensité élimine beaucoup d’opérations motivées par des signaux minuscules. Cela réduit la rotation et les coûts dans ce test. Cette amélioration relative ne transforme pas les résultats en gains. Les paramètres n’ont pas été retouchés après consultation des résultats.

## Ensemble des résultats

| Actif | Tranche | Règle | Coûts | Rendement net | Baisse max. aux clôtures | Allers-retours |
|---|---|---|---|---:|---:|---:|
| BTCUSDT | first_70pct | original_vote | base | -38.97 % | 39.53 % | 1572 |
| BTCUSDT | first_70pct | original_vote | stress | -86.08 % | 86.22 % | 1572 |
| BTCUSDT | first_70pct | strength_vote | base | +4.04 % | 4.71 % | 94 |
| BTCUSDT | first_70pct | strength_vote | stress | +1.39 % | 5.66 % | 94 |
| BTCUSDT | last_30pct | original_vote | base | -22.80 % | 23.98 % | 684 |
| BTCUSDT | last_30pct | original_vote | stress | -43.31 % | 43.65 % | 684 |
| BTCUSDT | last_30pct | strength_vote | base | -1.87 % | 4.23 % | 39 |
| BTCUSDT | last_30pct | strength_vote | stress | -2.96 % | 5.30 % | 39 |
| ETHUSDT | first_70pct | original_vote | base | -30.50 % | 31.67 % | 1524 |
| ETHUSDT | first_70pct | original_vote | stress | -76.37 % | 76.72 % | 1525 |
| ETHUSDT | first_70pct | strength_vote | base | +8.81 % | 3.63 % | 174 |
| ETHUSDT | first_70pct | strength_vote | stress | +3.80 % | 6.21 % | 174 |
| ETHUSDT | last_30pct | original_vote | base | -24.16 % | 25.21 % | 715 |
| ETHUSDT | last_30pct | original_vote | stress | -45.55 % | 45.74 % | 715 |
| ETHUSDT | last_30pct | strength_vote | base | -2.56 % | 4.46 % | 67 |
| ETHUSDT | last_30pct | strength_vote | stress | -4.43 % | 5.76 % | 67 |
| SOLUSDT | first_70pct | original_vote | base | -39.38 % | 40.57 % | 1494 |
| SOLUSDT | first_70pct | original_vote | stress | -83.97 % | 84.24 % | 1494 |
| SOLUSDT | first_70pct | strength_vote | base | -1.66 % | 7.96 % | 309 |
| SOLUSDT | first_70pct | strength_vote | stress | -11.61 % | 15.40 % | 311 |
| SOLUSDT | last_30pct | original_vote | base | -22.53 % | 24.19 % | 687 |
| SOLUSDT | last_30pct | original_vote | stress | -43.08 % | 43.93 % | 687 |
| SOLUSDT | last_30pct | strength_vote | base | -1.19 % | 5.35 % | 84 |
| SOLUSDT | last_30pct | strength_vote | stress | -3.54 % | 7.19 % | 84 |

## Ce que cette expérience ne prouve pas

Il s’agit d’une comparaison fixe de règles de vote, avec une simulation simplifiée. Elle ne rejoue pas l’intégralité du moteur, ne modélise pas les commissions variables ou en BNB, et ne dispose pas du carnet historique. Les protections intrabougie sont approximées. Trois actifs survivants ne constituent pas un univers exempt de biais. Les deux tranches repartent chacune de zéro ; la seconde a maintenant été observée. Voir `LIRE_AVANT_UTILISATION.md` pour les hypothèses et les risques opérationnels restants.

Les archives et `provenance.json` permettent d’inspecter les données. `comparison.json` conserve les résultats numériques non arrondis lorsque disponibles. Le script `research/validate.py` permet de reproduire le calcul, sans accès privé et sans envoi d’ordres.

## Validation logicielle

255 tests passent, exécutés en trois suites isolées : 178 pour le moteur principal et ses modules, 7 pour V15/V16, 70 pour V17. Les journaux sont dans `validation/`. Les fixtures historiques V17 ont été adaptées à l’horloge simulée ; deux anciennes attentes qui effaçaient des positions sans justification ont été corrigées. Un démarrage paper hors réseau a également été vérifié. Aucun test de connexion à un compte exchange authentifié n’a été effectué.
