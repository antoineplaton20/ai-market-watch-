# Inventaire V15

## Base existante
- V14.1: moteur de trading, backtests, évolution, sécurité, tests, veille, moteurs de marché.
- 24 rôles métier historiques documentés dans README.md.

## Nouvelle plateforme
- 360 bots dans `catalogue/bots_v15.json`.
- 12 familles fondamentales + variantes par domaine.
- BotFactory pour génération/scaffolding.
- Orchestrator pour routage.
- PolicyEngine pour séparation plan/acte.
- Evaluator pour comparaison de sorties.

## Structure

`bot_factory/` = cerveau générique de fabrication
`catalogue/` = inventaire et configuration
`runtime/` = emplacement du runtime généré
`teams/` = équipes futures
`tests_v15/` = tests de la couche V15

## Important

Le catalogue de 360 bots est un registre de rôles/scaffolds. Il ne signifie pas que 360 processus LLM tournent simultanément. Le déploiement doit être dynamique, quotaïsé et observable.
