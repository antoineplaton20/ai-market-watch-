# Migration V14.1 → V15

## Ce qui reste intact
- `main.py`, `equipe.py`, `gardien.py`, `auditeur.py`, `backtest.py`, `evolution.py`, moteurs, tests et commandes existantes.
- Les 24 rôles historiques du domaine Finance/Crypto.

## Les 24 rôles historiques deviennent

| V14 | V15 |
|---|---|
| CALENDRIER | finance_calendar_v14 |
| MÉTÉO | finance_market_weather_v14 |
| PEUR & AVIDITÉ | finance_sentiment_v14 |
| SCOUT | finance_scout_v14 |
| FILTRE | finance_filter_v14 |
| RISK | finance_risk_v14 |
| ANTI-HYPE | finance_antihype_v14 |
| TENDANCE | finance_trend_v14 |
| MOMENTUM | finance_momentum_v14 |
| MULTI-UNITÉS | finance_multitimeframe_v14 |
| CARNET | finance_orderbook_v14 |
| DÉRIVÉS | finance_derivatives_v14 |
| BALEINES | finance_whales_v14 |
| CORRÉLATION | finance_correlation_v14 |
| VEILLE | finance_news_v14 |
| LIQUIDITÉ | finance_liquidity_v14 |
| MACRO | finance_macro_v14 |
| POSITIONNEMENT | finance_positioning_v14 |
| DÉVELOPPEURS | finance_developer_activity_v14 |
| CONTRADICTEUR | finance_contradictor_v14 |
| LEADER | finance_leader_v14 |
| GARDIEN + TRAILING | finance_guardian_v14 |
| AUDITEUR | finance_auditor_v14 |
| BACKTESTEUR | finance_backtester_v14 |

Cette migration est une couche d'organisation; elle ne réécrit pas les fonctions V14.1.

## Règle de migration

1. Ne pas mélanger le code métier V14 avec le runtime générique V15.
2. Encapsuler chaque domaine derrière un adaptateur.
3. Ne donner aucune permission d'action à un bot par défaut.
4. Faire passer les nouveaux bots par sandbox + évaluation avant promotion.
5. Conserver une référence champion et tester les challengers contre le même dataset.
