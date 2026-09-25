# EQUIPE-BOTS V16

La V16 transforme V15 en plateforme Trading Intelligence + Bot Army.

## Démarrage sans argent réel
```bash
cp .env.v16.example .env
python -m trading_army.cli catalog
python -m trading_army.cli export
pytest -q tests_v16
```

## Testnet
Configurer `MODE=testnet` puis fournir des clés sandbox dédiées. Ne jamais réutiliser des clés de production.

## Live
Désactivé par défaut. Aucun retrait n'est implémenté dans l'ExecutionEngine. Le passage live doit faire l'objet d'un audit séparé.
