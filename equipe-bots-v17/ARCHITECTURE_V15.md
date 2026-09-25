# V15 — Architecture Bot Factory

## Vision

V14.1 reste le domaine Finance/Crypto. V15 ajoute une plateforme générique permettant de créer, versionner, router, sécuriser, mémoriser, tester et déployer des centaines de bots.

## Hiérarchie

ORCHESTRATOR → MANAGERS → TEAMS → SPECIALISTS → TOOLS

Un bot n'obtient jamais automatiquement des droits d'écriture simplement parce qu'il sait appeler un outil.

## Cycle d'un bot

DISCOVER → SPECIFY → SCAFFOLD → TEST → EVALUATE → CHAMPION/CHALLENGER → DEPLOY → OBSERVE → RETIRE/IMPROVE

## États

planned → sandbox → candidate → champion → paused → retired

## Séparation des responsabilités

- Model runtime: produit du raisonnement.
- Agent runtime: applique la mission.
- Orchestrator: choisit qui travaille.
- Tool runtime: effectue les actions.
- Policy: autorise/refuse les actions.
- Memory: conserve uniquement les éléments admissibles.
- Evaluator: mesure la performance.
- Observer: trace les exécutions.

## Infrastructure

Les outils de la liste initiale sont des briques interchangeables. Ollama peut servir de runtime local; LangChain/LangGraph de composants/workflows; AutoGen/CrewAI/CAMEL d'orchestration multi-agent; DSPy d'optimisation; E2B de sandbox; Composio ou adaptateurs natifs pour les outils; Mem0/RAG pour mémoire; AgentOps pour observabilité; Vercel AI SDK pour produit web. Les choix doivent rester derrière des interfaces internes.

## Domaine Finance/Crypto

Tous les modules V14.1 sont conservés. Ils ne deviennent pas des permissions globales. Les actions à effet de bord financier restent explicitement séparées et soumises aux contrôles du domaine.
