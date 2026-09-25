from .models import BotSpec

DEPARTMENTS = {
    "INTELLIGENCE": [
        ("reasoner", "Raisonnement général", "décomposer et résoudre des problèmes"),
        ("planner", "Planification", "transformer un objectif en plan exécutable"),
        ("critic", "Critique", "chercher failles et hypothèses fragiles"),
        ("contradictor", "Contradiction", "produire des contre-arguments"),
        ("synthesizer", "Synthèse", "fusionner plusieurs analyses"),
        ("decision_analyst", "Analyse décisionnelle", "structurer options, contraintes et conséquences"),
        ("uncertainty", "Incertitude", "identifier inconnues et niveaux de confiance"),
        ("decomposer", "Décomposition", "transformer une mission complexe en sous-tâches"),
        ("router", "Routage", "assigner les tâches aux spécialistes"),
        ("judge", "Juge", "évaluer une réponse selon une grille"),
    ],
    "RESEARCH": [
        ("web_researcher", "Recherche web", "collecter des informations publiques"),
        ("academic_researcher", "Recherche académique", "chercher et comparer des travaux"),
        ("source_finder", "Sources", "trouver des sources primaires"),
        ("source_validator", "Validation sources", "vérifier qualité et provenance"),
        ("fact_checker", "Fact-check", "vérifier les affirmations"),
        ("citation_checker", "Citations", "vérifier couverture et exactitude des citations"),
        ("date_validator", "Dates", "contrôler fraîcheur et chronologie"),
        ("competitor_researcher", "Concurrence", "cartographier offres et acteurs"),
        ("open_source_researcher", "Open source", "analyser dépôts et écosystèmes"),
        ("trend_researcher", "Tendances", "détecter évolutions émergentes"),
    ],
    "DATA": [
        ("data_collector", "Collecte", "ingérer des données structurées"),
        ("data_cleaner", "Nettoyage", "détecter et corriger les anomalies"),
        ("data_validator", "Validation data", "contrôler cohérence et complétude"),
        ("statistician", "Statistiques", "produire analyses statistiques"),
        ("time_series", "Séries temporelles", "analyser tendances et saisonnalités"),
        ("anomaly_detector", "Anomalies", "détecter comportements inhabituels"),
        ("feature_engineer", "Features", "construire variables utiles"),
        ("data_visualizer", "Visualisation", "produire représentations analytiques"),
        ("data_lineage", "Traçabilité", "suivre provenance et transformations"),
        ("dataset_curator", "Curation", "maintenir des jeux de données de référence"),
    ],
    "SOFTWARE": [
        ("software_architect", "Architecture", "concevoir architecture logicielle"),
        ("backend_dev", "Backend", "développer services backend"),
        ("frontend_dev", "Frontend", "développer interfaces web"),
        ("fullstack_dev", "Full stack", "développer verticales complètes"),
        ("python_dev", "Python", "développer en Python"),
        ("typescript_dev", "TypeScript", "développer en TypeScript"),
        ("sql_dev", "SQL", "concevoir requêtes et modèles relationnels"),
        ("api_dev", "API", "concevoir et intégrer APIs"),
        ("llm_engineer", "LLM", "construire intégrations LLM"),
        ("rag_engineer", "RAG", "construire systèmes de recherche augmentée"),
        ("agent_engineer", "Agents", "construire agents et outils"),
        ("prompt_engineer", "Prompts", "concevoir et tester instructions"),
        ("debugger", "Debug", "diagnostiquer bugs reproductibles"),
        ("refactorer", "Refactoring", "améliorer structure sans changer le comportement"),
        ("code_reviewer", "Code review", "contrôler qualité et risques"),
        ("documentation_engineer", "Documentation", "maintenir documentation technique"),
        ("dependency_manager", "Dépendances", "contrôler versions et compatibilité"),
        ("migration_engineer", "Migration", "préparer migrations de versions"),
        ("release_manager", "Release", "préparer releases reproductibles"),
        ("devops_engineer", "DevOps", "automatiser build, test et déploiement"),
    ],
    "QA": [
        ("unit_tester", "Tests unitaires", "générer et maintenir tests unitaires"),
        ("integration_tester", "Tests intégration", "tester interfaces entre composants"),
        ("e2e_tester", "E2E", "tester parcours complets"),
        ("regression_tester", "Régression", "détecter ruptures après changement"),
        ("property_tester", "Property testing", "tester invariants et propriétés"),
        ("load_tester", "Charge", "mesurer comportement sous charge"),
        ("chaos_tester", "Chaos", "tester tolérance aux pannes"),
        ("red_team_tester", "Red team", "chercher chemins de défaillance"),
        ("benchmark_runner", "Benchmark", "exécuter suites comparatives"),
        ("test_data_builder", "Données de test", "fabriquer fixtures et scénarios"),
    ],
    "SECURITY": [
        ("security_architect", "Architecture sécurité", "définir contrôles de sécurité"),
        ("secret_scanner", "Secrets", "détecter secrets exposés"),
        ("dependency_auditor", "Dépendances", "auditer vulnérabilités de dépendances"),
        ("permission_auditor", "Permissions", "contrôler privilèges des agents"),
        ("sandbox_guardian", "Sandbox", "vérifier isolation des exécutions"),
        ("prompt_injection_guard", "Prompt injection", "détecter tentatives de détournement"),
        ("tool_policy_guard", "Outils", "autoriser/refuser appels d'outils"),
        ("data_loss_guard", "DLP", "prévenir sorties de données sensibles"),
        ("incident_responder", "Incidents", "orchestrer réponse aux incidents"),
        ("security_reviewer", "Revue sécurité", "examiner changements sensibles"),
    ],
    "ORCHESTRATION": [
        ("ceo_orchestrator", "Orchestrateur", "piloter équipes et priorités"),
        ("task_router", "Routeur", "assigner les tâches"),
        ("team_manager", "Manager", "coordonner une équipe"),
        ("workflow_manager", "Workflow", "faire respecter les étapes"),
        ("budget_manager", "Budget", "contrôler coût et quotas"),
        ("model_router", "Model routing", "choisir modèle selon tâche"),
        ("tool_router", "Tool routing", "choisir les outils autorisés"),
        ("parallel_coordinator", "Parallélisation", "coordonner travaux parallèles"),
        ("handoff_manager", "Handoffs", "transférer contexte entre agents"),
        ("escalation_manager", "Escalade", "faire remonter les cas difficiles"),
    ],
    "TOOLS": [
        ("browser_operator", "Navigateur", "utiliser navigateur dans environnement contrôlé"),
        ("filesystem_operator", "Fichiers", "lire et modifier fichiers autorisés"),
        ("shell_operator", "Shell", "exécuter commandes autorisées"),
        ("git_operator", "Git", "gérer branches et changements"),
        ("github_operator", "GitHub", "interagir avec dépôts via permissions"),
        ("database_operator", "Base de données", "exécuter opérations DB autorisées"),
        ("api_operator", "API", "appeler APIs autorisées"),
        ("cloud_operator", "Cloud", "piloter ressources cloud autorisées"),
        ("document_operator", "Documents", "transformer documents"),
        ("notification_operator", "Notifications", "envoyer notifications approuvées"),
    ],
    "MEMORY": [
        ("memory_writer", "Écriture mémoire", "stocker faits validés"),
        ("memory_retriever", "Récupération", "retrouver contexte pertinent"),
        ("memory_curator", "Curation", "fusionner et nettoyer souvenirs"),
        ("memory_decay", "Décroissance", "gérer obsolescence"),
        ("knowledge_graph", "Graphe", "maintenir relations entre entités"),
        ("provenance_tracker", "Provenance", "lier faits à leurs sources"),
        ("context_builder", "Contexte", "construire contexte de tâche"),
        ("profile_manager", "Profils", "gérer préférences non sensibles"),
    ],
    "EVALUATION": [
        ("eval_designer", "Design évaluation", "définir critères et datasets"),
        ("eval_runner", "Runner", "exécuter évaluations"),
        ("judge_llm", "LLM judge", "évaluer sorties selon rubriques"),
        ("score_aggregator", "Scores", "agréger métriques"),
        ("drift_detector", "Drift", "détecter dégradation"),
        ("cost_evaluator", "Coût", "mesurer coût par tâche"),
        ("latency_evaluator", "Latence", "mesurer délais"),
        ("reliability_evaluator", "Fiabilité", "mesurer taux d'échec"),
        ("champion_manager", "Champion", "gérer référence actuelle"),
        ("challenger_manager", "Challenger", "tester alternatives"),
    ],
    "PRODUCT": [
        ("product_manager", "Produit", "transformer besoins en spécifications"),
        ("ux_researcher", "UX", "étudier usages et parcours"),
        ("ux_writer", "UX writing", "rédiger microcopies"),
        ("ui_designer", "UI", "concevoir interfaces"),
        ("content_writer", "Contenu", "rédiger contenus"),
        ("marketing_analyst", "Marketing", "analyser marché et messages"),
        ("sales_analyst", "Sales", "structurer opportunités commerciales"),
        ("operations_manager", "Opérations", "optimiser processus"),
        ("customer_support", "Support", "traiter demandes utilisateurs"),
        ("report_builder", "Rapports", "produire livrables structurés"),
    ],
    "INFRA": [
        ("container_engineer", "Conteneurs", "construire images et services"),
        ("linux_engineer", "Linux", "administrer systèmes"),
        ("ci_cd_engineer", "CI/CD", "automatiser pipelines"),
        ("observability_engineer", "Observabilité", "traces, logs, métriques"),
        ("cost_optimizer", "Coûts infra", "optimiser consommation"),
        ("backup_engineer", "Sauvegardes", "maintenir backups vérifiés"),
        ("disaster_recovery", "Reprise", "tester reprise après incident"),
        ("service_manager", "Services", "superviser services"),
    ],
}


DOMAIN_VARIANTS = {
    "AI": ["model", "prompt", "agent", "rag", "eval"],
    "SOFTWARE": ["backend", "frontend", "api", "devops", "testing"],
    "RESEARCH": ["web", "academic", "market", "competitive", "verification"],
    "FINANCE": ["market", "risk", "portfolio", "macro", "execution"],
    "OPERATIONS": ["workflow", "support", "planning", "quality", "reporting"],
    "SECURITY": ["identity", "application", "data", "runtime", "incident"],
}

def build_domain_variants(existing):
    variants=[]
    seed=[b for b in existing if b.department in {"INTELLIGENCE","RESEARCH","DATA","SOFTWARE","QA","SECURITY","ORCHESTRATION","EVALUATION"}]
    # Keep a controlled matrix: enough specialists to scale without creating meaningless permutations.
    for domain, specialties in DOMAIN_VARIANTS.items():
        for b in seed:
            if len(variants) >= 360-len(existing):
                return variants
            suffix=specialties[len(variants) % len(specialties)]
            vid=f"{domain.lower()}_{b.specialty}_{suffix}"
            variants.append(BotSpec(
                id=vid,
                name=f"{domain} {b.name} — {suffix}",
                department=domain,
                mission=f"{b.mission} appliqué au domaine {domain.lower()} ({suffix})",
                specialty=f"{b.specialty}_{suffix}",
                inputs=["task_context", "domain_context"],
                outputs=["result", "evidence", "confidence"],
                tools=[], model_policy="local_first", memory="shared_validated",
                supervisor="orchestration_team_manager", permissions=["read","plan"],
                evaluation=["correctness","reliability","cost","domain_fit"],
                risk_level="medium" if domain in {"FINANCE","SECURITY","OPERATIONS"} else "low"
            ))
    return variants

def build_catalogue():
    bots=[]
    for dept, rows in DEPARTMENTS.items():
        for slug, name, mission in rows:
            bots.append(BotSpec(
                id=f"{dept.lower()}_{slug}", name=name, department=dept,
                mission=mission, specialty=slug,
                inputs=["task_context"], outputs=["result", "evidence"],
                tools=[], evaluation=["correctness", "reliability", "cost"],
                risk_level="medium" if dept in {"TOOLS","INFRA","SECURITY"} else "low"
            ))
    bots.extend(build_domain_variants(bots))
    return bots
