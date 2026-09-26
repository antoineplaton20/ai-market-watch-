# V17.8 — Binance, Termius, Telegram et iPhone

Cette version renforce le moteur crypto `v17_ops` et la procédure de mise à jour. L’application iPhone, le bot principal, les autres modules et les historiques fournis sont conservés. Elle n’augmente pas automatiquement le capital ni le nombre de bots qui passent des ordres. Aucun levier ajouté.

**Aucun rendement positif permanent n’est possible à imposer au logiciel. Les résultats ci-dessous ne justifient pas un passage en argent réel.** Une stratégie peut perdre malgré tous ses contrôles ; multiplier les bots peut multiplier la même exposition. Le levier augmente l’exposition financière, pas la quantité de données ni les capacités de raisonnement.

## Ce qui change

- La taille d’un achat V17 tient compte du budget, du stop, des frais et d’une provision de glissement, en plus des plafonds existants.
- La perte cumulée du portefeuille V17 est comparée au budget déployable, sans être diluée par un grand solde fictif inutilisé. Le blocage des nouveaux achats persiste après redémarrage.
- Trois positions simultanées au maximum par défaut ; délai de repos de quatre bougies après une vente de protection.
- Un réglage numérique invalide bloque les achats : le moteur reste consultable et les sorties restent possibles. Corriger `.env` puis redémarrer V17.
- Un ordre introuvable ne devient plus automatiquement « non exécuté » après deux minutes. Un solde libre insuffisant n’efface plus la position après dix minutes : les fonds peuvent être bloqués ailleurs.
- Le rapprochement démo/testnet exige une réponse explicite de Binance. Une reprise après échec d’écriture ne doit pas comptabiliser deux fois le même achat. Le rapprochement live reste manuel.
- L’état des protections est visible dans `/v17` et dans les alertes de l’application iPhone. Lever la pause ne supprime pas le blocage pour perte cumulée.
- La mise à jour copie aussi les données de recherche et les catalogues JSON ; elle préserve `.env`, les bases et l’état du serveur. Elle restaure uniquement les services qui étaient actifs, y compris l’API iPhone, au lieu d’activer une veille supplémentaire.

Ces contrôles concernent **V17 uniquement**. Le bot principal possède ses propres contrôles : les budgets de plusieurs moteurs ne constituent pas un budget commun de compte Binance. Les stops V17 sont surveillés par le programme : une panne ou un saut de prix peut dépasser la perte estimée. Les frais exchange restent estimés par `V17_FEE_RATE` ; ce n’est pas un rapprochement comptable complet des commissions réelles en BNB ou autre actif.

## Mise à jour d’un serveur déjà installé

Termius se connecte en SSH au serveur qui exécute Python. Les commandes ci-dessous supposent le compte root et l’installation existante dans `/home/bots/equipe-bots`.

1. Enregistrer `equipe-bots-v17.8-iphone.zip`, puis l’envoyer dans `/root/` avec le transfert SFTP de Termius.
2. Dans le terminal Termius :

```bash
mkdir -p /root/maj-v178
unzip -q /root/equipe-bots-v17.8-iphone.zip -d /root/maj-v178
bash /root/maj-v178/equipe-bots-v17/bots mettre-a-jour /root/equipe-bots-v17.8-iphone.zip
bots v17-etat
```

**Utiliser bien le script extrait ci-dessus pour cette première mise à jour** : l’ancienne commande `bots mettre-a-jour` exclut des fichiers nécessaires à la recherche. Le nouveau script sauvegarde l’ancien code et les données avant copie, suspend les services actifs pendant l’opération et les restaure après les tests. Ne pas interrompre cette opération avec des positions ouvertes : leur surveillance est suspendue pendant l’arrêt du moteur.

Les clés et le jeton d’application existants sont conservés. Ne pas remplacer `.env` par `.env.example`, et ne pas transmettre ses clés dans une conversation. La mise à jour conserve le mode existant ; elle ne bascule pas un compte démo en réel. Elle ne clôture pas les positions.

En cas d’échec, le script tente de restaurer l’ancien code et les données ; les bibliothèques Python installées peuvent avoir changé. La sauvegarde est indiquée dans le terminal. Si une restauration ou un redémarrage échoue, il le signale et termine en erreur.

Pour ouvrir l’application : `bots app`, puis suivre `APPLI_IPHONE.md`. Sur Telegram : `/v17` pour l’état, `/v17 stop` pour suspendre les nouveaux achats, `/v17 reprise` pour lever cette pause. Les autres contrôles restent actifs.

Pour un **nouveau serveur Ubuntu 24.04**, extraire l’archive puis lancer `bash installer.sh` dans son dossier ; l’installateur d’origine configure le serveur et les modules. Une installation système complète n’a pas été exécutée ici. Sur un serveur existant, utiliser la mise à jour ci-dessus.

## Paramètres V17.8

Valeurs par défaut, appliquées aussi lorsqu’elles sont absentes du `.env` :

```dotenv
V17_RISK_PER_TRADE_PCT=0.5
V17_MAX_DRAWDOWN_PCT=10
V17_MAX_POSITIONS=3
V17_COOLDOWN_BARS=4
```

Le risque nominal vaut `min(capital autorisé, valeur du portefeuille) × risque par opération / (stop + frais aller-retour + glissement aller-retour)`. Tous les pourcentages sont convertis en fractions dans le calcul. Exemple purement mécanique : budget 1000 USDT, risque 0,5 %, stop 3 %, frais 0,1 % par côté, provision de glissement 0,25 % par côté → plafond nominal d’environ 135 USDT, encore limité à 100 USDT par `MAX_ORDER_USDT` par défaut. Une protection désactivée par `V17_STOP_LOSS_PCT=0` supprime le stop : la formule ne représente alors plus un risque de perte borné.

La limite cumulée commence à la première observation de V17.8 : elle ne reconstitue pas le pic historique antérieur à cette version. Elle porte sur le carnet local V17, pas sur l’intégralité du compte Binance. Un changement de budget change son échelle. Après déclenchement, ne pas supprimer la base ni relever arbitrairement les plafonds pour contourner l’arrêt : analyser les ordres, les soldes et la stratégie avant un réarmement technique. Aucune commande de réarmement automatique n’est ajoutée.

## Validation historique incluse — résultats négatifs conservés

Données fournies dans l’archive : 96 archives mensuelles Binance, **280 512 bougies de 15 minutes**, BTC/USDT, ETH/USDT et SOL/USDT, janvier 2024 à août 2026. Le nouveau programme vérifie les empreintes SHA-256 locales et la continuité des bougies. Aucune nouvelle collecte ni connexion à un compte privé pour cette validation.

Le programme compare quatre possibilités fixées avant l’essai : la stratégie V17.7, un filtre de tendance sur 200 bougies, un repos après stop de huit bougies, et l’absence de position. Pour chaque fenêtre : six mois de sélection, puis trois mois de test postérieur. Une variante doit avoir au moins dix allers-retours et une performance qui couvre la baisse maximale constatée lorsque les coûts sont doublés ; sinon, rester sans position. Aucun résultat futur de cette fenêtre n’entre dans la sélection.

Coûts de base : frais de 0,1 % et glissement de 0,05 % par côté ; essai de résistance : 0,2 % et 0,1 %. Exécution à l’ouverture suivante, stops intrabougie approximés avec prise en compte des sauts de prix. Les huit fenêtres de test couvrent juillet 2024 à juin 2026. Juillet et août 2026 sont explicitement laissés de côté faute d’un trimestre complet.

| Actif | Somme des PnL sélectionnés | Somme des PnL V17.7 | Fenêtres sans position |
|---|---:|---:|---:|
| BTC/USDT | −23,69 USDT | −24,54 USDT | 6/8 |
| ETH/USDT | −5,81 USDT | +1,43 USDT | 6/8 |
| SOL/USDT | 0,00 USDT | −48,38 USDT | 8/8 |

**Chaque fenêtre repart avec 1000 USDT et des ordres de 100 USDT au maximum. Ces sommes ne sont ni un rendement composé ni le résultat d’un compte exécuté en continu.** Rester sans position explique les résultats nuls. La sélection fait moins bien que V17.7 sur ETH : les variantes ne sont pas activées dans le moteur.

Limites : seulement trois actifs survivants, historique déjà observé auparavant, échauffement au début de chaque fenêtre, exécution OHLC approximative, aucune modélisation de levier/liquidation, pas de reproduction complète de tous les contrôles opérationnels V17.8. Ce n’est ni une preuve de performance future ni un test en conditions réelles.

Pour reproduire l’évaluation, sans ordre ni Telegram :

```bash
bots valider-v178
```

Rapport détaillé : `research/walk_forward_v178.json`. Programme : `research/walk_forward_ops.py`. Les données d’entrée et leur provenance sont dans `research/results/`. Une empreinte incorrecte ou une série incomplète fait échouer l’évaluation. Le programme ne modifie aucun paramètre ni stratégie de trading.

## Vérifications de livraison

357 tests réussis : 233 pour le bot principal, 3 pour V15, 4 pour V16 et 117 pour V17, sans test ignoré. Les journaux de tests et les versions utilisées sont dans `validation/v178/`. Ils vérifient le logiciel avec des échanges simulés ; ils ne prouvent pas sa rentabilité. Aucune connexion à vos comptes, aucun ordre réel, aucun déploiement sur votre serveur ni envoi Telegram n’a été effectué.
