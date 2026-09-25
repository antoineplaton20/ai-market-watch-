# Révision de robustesse — 25 septembre 2026

Cette révision améliore le contrôle des erreurs et la crédibilité des mesures. Elle ne démontre pas une stratégie rentable et ne constitue pas une solution de remboursement de dette. Aucun ordre réel, aucune connexion à un compte privé et aucun déploiement n'ont été effectués pendant le travail.

## Démarrage en simulation

Dans une copie séparée du projet, après installation des dépendances :

```bash
python -m pip install -r requirements.txt
bash start_paper_review.sh --once --price 50000
bash start_paper_review.sh
```

Un prix injecté (`--price`) est refusé dans les modes exchange. Le premier appel est un contrôle hors réseau, sans transaction. Le second utilise les cours publics avec une caisse fictive et une base dédiée `runtime/v17_review_paper.db`. Le script force le mode paper et désactive les notifications Telegram, même si le `.env` contient d'autres modes. Le service existant et le moteur principal `main.py` ne sont pas lancés par ce script. Arrêt : Ctrl+C.

Ne pas remplacer à chaud une installation en fonctionnement. Sauvegarder la base et les réglages avant toute migration. Les anciens scripts de déploiement du projet sont conservés ; leur présence n'est pas une validation du mode réel.

## Corrections livrées

| Composant | Défaut constaté | Correction |
|---|---|---|
| `v17_ops/core/portfolio.py` | Bénéfice réalisé ne déduisant pas les frais d'entrée | Frais d'entrée mémorisés, alloués aux ventes partielles et persistés |
| `v17_ops/adapters/ccxt_adapter.py` | Quantité demandée substituée à un remplissage nul ou absent | Quantité réellement confirmée, prix moyen confirmé ou calculé sur le coût ; sinon arrêt pour rapprochement |
| Moteur V17 / SQLite | Une erreur réseau pouvait laisser le résultat de l'ordre indéterminé | Intention persistée avant envoi, identifiant client, blocage durable en cas d'incertitude, carnet et levée du blocage validés dans la même transaction |
| Ventes V17 | Reliquats effacés et fonds d'une vente externe inventés | Reliquat conservé ; solde incohérent soumis à rapprochement, sans inventer de recette |
| Risque / configuration | NaN et infinis contournant des comparaisons | Validation des montants, prix et paramètres numériques |
| Limites d'exécution | Nombre d'ordres ouverts passé en dur à zéro | Lecture du nombre d'ordres ouverts sur l'exchange avant achat |
| Liquidité | Seuil de glissement configuré mais inutilisé | Contrôle de profondeur/prix avant achat ; pause des achats si remplissage confirmé dépassant le seuil |
| Données V17 | Pas de contrôle des séries périmées ou trouées | Contrôle des valeurs OHLCV, ordre, continuité, fraîcheur, dates futures et alignement temporel |
| Perte quotidienne | Reprise possible après rebond pendant la même journée | Seuil mémorisé jusqu'au changement de journée UTC |
| Protection | Possibilité de réutiliser la bougie ayant déclenché le stop | Bougie consommée après vente de protection confirmée |
| Votes V17 | Accord de deux signaux presque nuls affiché à 100 % | Score tenant compte de l'intensité et du désaccord ; ce score n'est pas une probabilité de gain |
| `trading_army/strategy_lab.py` | Pas de frais ; exécution sur la clôture du signal ; victoires calculées depuis le capital initial | Frais et glissement, exécution à la barre suivante, résultat par aller-retour |
| `backtest.py` | Gains futurs réinvestis dès l'entrée ; trades d'apprentissage pouvant finir pendant le test | PnL réalisé à la sortie ; purge des trades traversant la frontière apprentissage/test |

Le catalogue V16 contient 3 120 fiches, celui V15 en contient 360. Les fabriques produisent principalement des spécifications et squelettes. Le moteur OPS utilise deux signaux techniques corrélés (moyennes simples et momentum), et non des milliers de stratégies indépendantes. Aucun ajout artificiel de fiches n'a été effectué.

## Données et expérience reproductible

```bash
python -m research.validate --start 2024-01 --end 2026-08
python -m pytest -q tests --import-mode=importlib
python -m pytest -q tests_v15 tests_v16 --import-mode=importlib
python -m pytest -q tests_v17 --import-mode=importlib
```

Le nouveau collecteur utilise uniquement les archives publiques Binance Spot : BTCUSDT, ETHUSDT et SOLUSDT, bougies de 15 minutes, mois complets. Trois téléchargements simultanés au maximum ; reprises sur erreurs réseau ; contrôle SHA-256 avec les fichiers CHECKSUM de l'éditeur ; contrôle du nombre exact et de la continuité des bougies. Les archives existantes sont réutilisées après vérification. Un mois absent ou invalide exclut le symbole du rapport au lieu de fabriquer les données manquantes.

Les fichiers `research/results/provenance.json` et `comparison.json` contiennent la traçabilité et les résultats. Les ZIP bruts vérifiés sont conservés dans `research/results/archives/`. Le rapport lisible est `RESULTATS_HISTORIQUES.md`.

Comparaison fixée avant observation des résultats : votes d'origine contre votes corrigés, sans recherche de paramètres. Capital fictif de 1 000 USDT **par symbole**, ordres de 100 USDT, stop de 3 %, seuil quotidien de 50 USDT. Signal à la clôture, achat/vente à l'ouverture suivante, stop simulé avec prise en compte des gaps. Frais de base 0,10 % par côté et glissement 0,05 % par côté ; stress : respectivement 0,20 % et 0,10 %. Les 70 % initiaux et 30 % finaux sont simulés séparément avec remise à zéro du capital et échauffement. Les trois comptes ne constituent pas un portefeuille partagé.

Cette comparaison est un simulateur de recherche approximatif, **pas une reproduction intégrale du moteur en production** : pas de carnet historique, latence, exécution partielle, latching exact du risque journalier ou conflits avec le bot principal. Les baisses sont mesurées aux clôtures et peuvent sous-estimer les pertes intrabougie. L'étude porte sur trois actifs survivants, avec un biais de sélection. La dernière tranche est maintenant observée : elle ne doit pas devenir une cible d'optimisation répétée présentée ensuite comme un test inédit.

## Limites qui empêchent de considérer ce projet comme validé pour le réel

- Les performances historiques peuvent rester négatives, même après correction. Les tests logiciels prouvent des comportements de code, pas des gains futurs.
- Les stops du moteur restent locaux : panne du processus, du réseau ou données invalides peuvent empêcher une vente. `KILL_SWITCH=1` bloque aussi les sorties. Des ordres de protection natifs côté exchange et leur rapprochement restent à concevoir et valider.
- Un ordre incertain bloque volontairement toute nouvelle exécution OPS, y compris les ventes. Il faut rapprocher l'ordre et les avoirs avant reprise ; ce n'est pas un gestionnaire automatique complet des incidents.
- Les commissions d'exchange restent estimées au taux configuré `V17_FEE_RATE`. Les frais prélevés en actif de base ou en BNB ne sont pas encore rapprochés automatiquement. Le correctif de frais exact concerne le modèle paper au taux choisi.
- Les anciens carnets n'ont pas conservé les frais d'entrée historiques : leur migration conserve les positions, mais ne peut reconstruire des frais inconnus. Ne pas comparer leur bénéfice cumulé comme s'il avait été recalculé rétroactivement.
- Un contrôle du carnet avant envoi ne garantit pas le prix d'un ordre au marché. Un mouvement brutal peut dépasser le seuil avant l'exécution.
- Le moteur principal et les versions V15/V16 n'ont pas reçu un audit exhaustif. Leurs garde-fous ne doivent pas être confondus avec ceux de V17 OPS. Risque agrégé multi-moteurs, corrélations, suivi comptable exact et limites exchange complètes restent à valider.
- La correction du résumé `backtest.py` mesure seulement la baisse du capital réalisé, pas une courbe complète valorisant toutes les positions ouvertes.

## Procédure si `reconciliation_required` apparaît

1. Arrêter le service concerné et sauvegarder sa base. Ne pas supprimer le marqueur pour simplement relancer le bot.
2. Vérifier auprès de l'exchange l'ordre identifié par `intent_id` (identifiant client sans tirets), ses transactions, commissions et le solde libre **et bloqué**.
3. Reconstituer le carnet et le cash d'après ces exécutions, sans les comptabiliser deux fois. Pour un transfert ou une opération manuelle, déterminer son traitement comptable séparément.
4. Mettre à jour la base et retirer `pending:<mode>` dans une même transaction seulement une fois le rapprochement terminé, par une personne capable de vérifier la comptabilité. Aucun bouton de déblocage aveugle n'est fourni.
5. Reprendre d'abord en simulation. Les commandes Telegram habituelles ne suppriment pas ce blocage.

## Sources techniques consultées

- Binance, archives publiques et format, changement des horodatages Spot en microsecondes depuis 2025, vérification CHECKSUM : https://github.com/binance/binance-public-data
- Binance, ordres Spot, identifiant client et quantités exécutées : https://developers.binance.com/docs/binance-spot-api-docs/rest-api/trading-endpoints
- Dépôt des archives : https://data.binance.vision/

La collecte est ciblée sur les données nécessaires à cette expérience. Elle ne prétend pas avoir aspiré toutes les plateformes, documents ou nouvelles. Accumuler des sources sans horodatage de disponibilité et sans validation ajouterait des biais plutôt qu'une preuve d'avantage.
