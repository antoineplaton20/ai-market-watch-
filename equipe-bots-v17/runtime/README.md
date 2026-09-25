# Runtime V15

Le runtime est volontairement séparé du catalogue.

Flux:
1. Task reçue
2. Orchestrator route
3. Policy vérifie permissions
4. Agent planifie
5. Human/manager approuve les side-effects si nécessaire
6. Tool runtime exécute
7. Memory écrit les faits validés
8. Evaluator mesure le résultat
9. Champion/Challenger compare les variantes
