> Mise à jour V17.8 : lire d’abord **V17_8_TERMIUS.md**. Les anciens déblocages par simple délai sont supprimés. Les résultats positifs ne sont pas garantis.

# Équipe de bots crypto v10 — prête à fonctionner sur serveur, 24 h/24

> **v17.5** : 3 portes avant le réel, backtest corrigé, bougies japonaises (PORTES_ET_BOUGIES.md). **v17.4** : armée de renseignement (RENSEIGNEMENT.md). **v17.3** : veille marchés mondiaux et notes de 0 à 5 (VEILLE_MARCHES.md). **v17.1** : moteur v17 branché sur la plateforme (service `equipe-bots-v17`, `/v17` sur Telegram,
> `bots v17-…`). Mise à jour et mode d'emploi : **V17_PLATEFORME.md**. `python verifier.py` lance
> désormais toutes les suites (plateforme + v15 + v16 + v17).

## Par où commencer
**Lis GUIDE_INSTALLATION.md** : 11 étapes, tout depuis ton téléphone (Telegram, Binance démo, serveur
Hetzner, Termius), environ 1 h 30 la première fois.

## Ce que la v10 ajoute
- **installer.sh** : installation complète en une commande sur un serveur Ubuntu 24.04 neuf
  (sécurité, heure, pare-feu, compte dédié, Python, tests, configuration guidée, démarrage automatique).
- **configurer.sh** : assistant qui pose les questions une par une, détecte ton identifiant Telegram,
  teste Telegram et Binance, et protège le fichier des clés.
- **bots** : télécommande du serveur (`bots etat`, `bots journal`, `bots config`, `bots unite 1h`,
  `bots evolution`, `bots mettre-a-jour 'lien'`...). Tape `bots` pour la liste.
- **preparer.py** : après l'installation, tests → backtest 2 ans → première évolution, résultats sur Telegram.
  Il CONSEILLE l'unité de bougie mais ne la change jamais seul.
- **Mises à jour sûres** : sauvegarde, installation, tests, retour arrière automatique en cas d'échec.
- Journal limité à 25 Mo (rotation) : le disque du serveur ne se remplit jamais.

Testé de bout en bout sur un Ubuntu 24.04 vierge : installation, configuration, 103 tests, changement
d'unité, mise à jour réussie (données et réglages conservés), mise à jour défectueuse (retour arrière).

`python verifier.py` (ou `bots verifier` sur le serveur) : 103 tests.

---

# Rappel v9 — base solide : contrôle, traçabilité, IA calibrée, recherche

## Ce que tu reçois sur Telegram
| Symbole | Signification | Son |
|---|---|---|
| 🔔 🟢 ACHAT | le bot vient d'acheter (prix, quantité, stop, score) | oui |
| 🔔 ✅ / 🔻 VENTE | le bot vient de vendre (raison, gain ou perte) | oui |
| 🔔 Signal d'achat → ⛔ bloqué | un achat était prévu mais un veto l'a bloqué (et lequel) | oui (1 fois / 2 h / paire) |
| 🔔 Signal d'achat → ⏭ non exécuté | limite de positions atteinte ou montant trop faible | oui |
| 🔔 🚨 VENTE ANTICIPÉE | mauvaise nouvelle réelle (piratage, délisting) sur une position : vendue | oui |
| 💰 prise partielle / 🔒 sécurisé | une partie encaissée / stop remonté au prix d'entrée | oui |
| ↗️ stop suiveur remonté | routine | non |
| 🟢🟡🟠🔴 État de risque | changement de niveau de risque | oui si 🟠 ou 🔴 |
| 🙋 APPROBATION DEMANDÉE | boutons ✅ / ❌ : nouveau champion ou palier de capital | oui |
| 🗓 Bilan du jour (21 h) · 💓 signe de vie (6 h) · 🔬 recherche · 🧬 évolution | routine | non |

Le scan part environ 10 secondes après la clôture de chaque bougie : un signal t'arrive dans la
minute qui suit sa naissance. Les ventes au stop sont exécutées instantanément par Binance.

Commandes : /statut /rapport /journal /sante /notes /calibration /evolution /attente /univers /exploration /tr /registre
/stop /reprise /rearmer /vendre_tout /approuver <id> /refuser <id> (les boutons font la même chose).

## A. Contrôle et sécurité
- **Approbation humaine** : un challenger qui gagne son duel N'EST PAS promu. Tu reçois les chiffres et
  deux boutons. Sans réponse, rien ne change. Un challenger qui perd est éliminé automatiquement.
- **États de risque gradués** : SÛR (x1) → PRUDENCE (x0,75) → RÉDUCTION (x0,5) → ARRÊT.
  PRUDENCE dès -5 % de baisse, -1,5 % sur la journée, 3 pertes d'affilée ou une IA mal calibrée.
  RÉDUCTION dès -8 %, -3 % sur la journée ou 5 pertes d'affilée.
- **Coupe-circuit absolu à -15 %** depuis le plus haut, quelle que soit la prévision du champion.
- **Capital par paliers** : 100 → 300 → 1 000 → 3 000 USDT (config.py), jamais au-delà de
  CAPITAL_MAX_USDT (.env). Monter : 14 jours et 30 trades minimum au palier, espérance positive,
  risque SÛR, puis TON approbation. Descendre : automatique à chaque disjoncteur.
- **Fraîcheur des données** : prix de plus de 2 min, bougies en retard, horloge décalée de plus de 5 s
  ou 3 erreurs réseau d'affilée → aucun nouveau risque. Les stops restent chez Binance.

## B. Traçabilité
- **Journal d'audit** (journal.db) : chaque décision est enregistrée AVANT toute action, avec l'empreinte
  SHA-256 de l'état du marché, l'état complet, la version du génome et de la politique, les vetos, le
  niveau de risque. Chaque ordre : prix voulu, prix obtenu, glissement réel, frais. Sans trace écrite, pas de trade.
- **Registre de recherche immuable** (registre_recherche.jsonl) : évolutions, challengers, duels,
  approbations, recherches. Chaîne d'empreintes : toute retouche se voit (/registre).

## C. IA (sans Jev)
- **Calibration du CONTRADICTEUR** : chaque verdict est suivi sur le papier, tradé ou non. Score de Brier
  comparé à un devin naïf : CALIBRÉ, SURCONFIANT, SOUS-CONFIANT ou NON FIABLE (/calibration).
  SURCONFIANT ou NON FIABLE → état PRUDENCE automatique.
- **Règle d'escalade** : l'IA relit chaque achat mais peut seulement dire NON. Si la clé IA est configurée
  et que l'IA ne répond pas → aucun trade (jamais de décision sans son avis).

## D. Recherche fondamentale (dimanche, veto uniquement)
CoinGecko (offre en circulation, dilution) + DefiLlama (TVL, frais et revenus sur 30 jours) +
deblocages.csv (tenu à la main : aucune source gratuite fiable). Exclus des achats pour 7 jours :
moins de 35 % de l'offre en circulation, TVL -25 % en 7 jours, déblocage d'au moins 2 % dans les 14 jours.
Chaque chiffre porte sa source et sa date ; les thèses de l'IA sont étiquetées ESTIMATION.



---

# Rappel v8 — mesure du sur-apprentissage (PBO + Sharpe dégonflé)

## Nouveau en v8 : le système mesure s'il est en train de se tromper lui-même
Quand on teste des milliers de stratégies, certaines paraissent excellentes par pure chance.
Deux outils de la recherche en finance quantitative mesurent ce risque AVANT d'ouvrir le coffre-fort :

**1. PBO — probabilité de sur-apprentissage** (Bailey, Borwein, López de Prado, Zhu)
L'entraînement est coupé en 12 tranches. Pour chacune des 924 façons d'en prendre 6 comme « passé »
et 6 comme « futur », on choisit la meilleure stratégie sur le passé et on regarde son rang sur le futur.
- 0 % : la meilleure du passé reste parmi les meilleures dans le futur → sélection fiable.
- 50 % : pas mieux que tirer au sort.
- Seuil : 35 %. Au-dessus, le coffre reste fermé toute la semaine et aucun challenger n'est désigné.
  Bonus : le coffre n'est pas « usé » pour rien (sa barre anti-chance monte à chaque ouverture).

**2. Sharpe dégonflé** (Bailey, López de Prado)
Pour chaque candidate : probabilité que son avantage soit réel une fois retirés l'effet « on a gardé
la meilleure de beaucoup d'essais » et l'effet des gros écarts (asymétrie, queues épaisses).
- Seuil : 90 %. En dessous, la candidate est écartée avant même d'ouvrir le coffre.
- Le nombre d'essais utilisé est le nombre de stratégies VRAIMENT différentes : 30 mutations d'une même
  idée comptent pour une seule (mesuré par la corrélation de leurs résultats).

Vérifié : sur du hasard pur, la PBO vaut en moyenne ~48 % (valeur attendue : 50 %). Quand un vrai motif
existe, elle tombe à 0 % et le Sharpe dégonflé monte à 100 %. Sur le hasard de test, la PBO de la semaine
(39 %) a gardé le coffre fermé.

Attention : la PBO d'une seule semaine varie beaucoup (de 17 % à 83 % sur du hasard pur). C'est pourquoi
elle n'est qu'un garde-fou parmi d'autres : Sharpe dégonflé, coffre-fort, barre anti-chance, Monte-Carlo,
puis duel réel. Une stratégie doit franchir TOUS ces filtres.

Le rapport quotidien Telegram affiche aussi la PBO : « fiabilité de la sélection » du jour.
`python verifier.py` : 69 tests.

Ordre complet des filtres avant qu'une stratégie trade de l'argent :
entraînement robuste (pire période) → PBO ≤ 35 % → Sharpe dégonflé ≥ 90 % → coffre-fort + barre anti-chance
→ Monte-Carlo (pire baisse probable ≤ 10 %) → duel réel de 14 jours minimum → champion.

---

# Rappel v7 — audit complet

## Nouveau en v7 : audit de tout le code
Analyse statique de chaque fichier, relecture ligne à ligne des parties qui touchent à l'argent,
puis un test automatique pour CHAQUE erreur trouvée (elle ne peut plus revenir sans être détectée).

Erreurs trouvées et corrigées :
1. Les trades fantômes étaient rejoués en bougies 15 min même si le bot trade en 1 h ou 4 h (notes des vetos faussées).
2. Un stop exécuté en partie puis une vente de secours : la partie vendue au stop n'était pas comptée.
3. Réconciliation : un stop exécuté passait inaperçu si tu détiens la même crypto en dehors du bot.
4. Le bot pouvait lire champion.json pendant que l'évolution l'écrivait : écritures désormais atomiques.
5. Les messages Telegram de plus de 4 096 caractères étaient refusés : ils sont tronqués proprement.
6. Le vote CARNET n'était pas calculé pareil en réel et en backtest : même définition partout.
7. Si le solde tardait à s'afficher après un achat, les jetons achetés pouvaient rester sans stop.
8. Panne totale de Binance au moment de l'achat : la position est désormais suivie et protégée dès le retour.
9. Duel inéquitable : l'IA ne filtrait que le champion. Les deux sont maintenant jugés sur la même base.
10. Commandes Telegram du type /stop@MonBot mal reconnues ; Ctrl+C mal géré par le chien de garde.

Améliorations tirées de la documentation officielle de Binance (changements 2026) :
- **Horloge** : synchronisation automatique avec les serveurs Binance (évite les erreurs « timestamp »).
- **Mode DÉMO** (nouveau, recommandé) : vrais prix du marché, argent fictif. Clés API sur demo.binance.com.
  Le testnet, lui, a des prix artificiels et Binance efface toutes ses données chaque mois : le bot le
  détecte désormais et retire les positions effacées sans fausser le journal.
- **Ordres au marché exécutés en partie** (règle de fourchette de prix de Binance) : le bot termine la vente
  au lieu de laisser un reste sans protection.
- **Contrôle qualité des archives** : bougies impossibles ou aberrantes retirées avant tout backtest.

`python verifier.py` : 61 tests, environ 15 secondes.

---

# Rappel v6 — sécurité de fonctionnement, disjoncteur, tests automatiques

## Nouveau en v6

### Lancer le bot (changement important)
`python lanceur.py` au lieu de `python main.py`. Le chien de garde :
- relance le bot s'il plante (attente croissante de 10 s à 5 min) ;
- le relance s'il ne donne plus signe de vie pendant 15 min ;
- s'arrête et te prévient après 5 plantages en 1 h (mieux vaut arrêté qu'en boucle).
Deux bots ne peuvent jamais tourner en même temps dans le même dossier (verrou système).

Sur Windows, pour qu'il tourne en continu :
- Paramètres > Système > Alimentation > mise en veille : **Jamais** (sinon le bot dort avec le PC) ;
- Planificateur de tâches > Créer une tâche > Déclencheur « Au démarrage » > Action : `python lanceur.py`
  (dossier de départ : le dossier du bot).

### Réconciliation avec Binance (au démarrage puis toutes les heures)
- Position vendue pendant une coupure → clôturée proprement dans le journal.
- Stop disparu ou annulé → reposé ; prix déjà sous le stop → vente par sécurité.
- Quantité différente (vente manuelle) → corrigée, stop ajusté.
- Ordres orphelins créés par le bot (signés « eqb ») → annulés. Tes ordres manuels ne sont jamais touchés.
- En réel : avoirs inconnus du bot signalés, jamais vendus d'office.

### Disjoncteur de performance
- Pire baisse réelle > 1,5 x la pire baisse prévue par le coffre-fort → plus aucun achat.
- Espérance réelle nettement sous la prévision (test statistique dès 30 trades) → plus aucun achat.
- 7 pertes d'affilée → pause de 24 h.
Les positions gardent leur stop. Relance manuelle avec /rearmer, après avoir compris ce qui se passe.

### Surveillance et sauvegardes
- Message « 💓 Bot actif » toutes les 6 h : s'il n'arrive plus, il y a un problème.
- Sauvegarde quotidienne (champion, population, journal, notes, réglages) dans `sauvegardes/`,
  30 jours gardés. Mets un dossier OneDrive dans `SAUVEGARDE_COPIE` (config.py) pour une copie hors du PC.
- Nouvelles commandes Telegram : /sante (disjoncteur, pause, dernière sauvegarde), /rearmer.

### Tests automatiques
`python verifier.py` : 46 tests en ~15 s, sans réseau ni argent. Ils vérifient le moteur de sortie,
la taille des positions, le stop toujours présent, la prise partielle au centime, la réconciliation,
le disjoncteur, le verrou, les sauvegardes, le chien de garde, le duel, l'évolution (refuse le hasard,
trouve un vrai motif) et un cycle complet de bout en bout.
**À lancer après chaque mise à jour, avant de relancer le bot.**

Ce que les tests ont déjà trouvé : la taille des positions ne comptait pas les frais ni le glissement
du stop. Une perte au stop coûtait environ 1,2 % du capital au lieu de 1 %. C'est corrigé : le risque
réel par trade est maintenant bien de 1 %, frais compris.

---

# Rappel v5 — 26 bots, 8 espèces, amélioration quotidienne

## Nouveau en v5 : l'équipe apprend chaque jour
- **Chaque nuit** (3 h) : entraînement quotidien, 6 générations de 128 stratégies sur les données du jour.
  La population progresse sans ouvrir le coffre-fort. Rapport Telegram « Ce que l'équipe a appris ».
- **Chaque dimanche** : grande évolution de 25 générations, coffre-fort, Monte-Carlo, nouveau challenger.
- **En continu** : notes des bots (AUDITEUR), trades fantômes, duel champion / challenger, échange à chaud.

## L'encyclopédie : ce que les bots savent, et d'où ça vient
| Source | Ce qu'elle apporte | Depuis |
|---|---|---|
| data.binance.vision | bougies de TOUTES les paires USDT, y compris celles retirées de Binance | 2017 |
| data.binance.vision | funding, open interest, positions des gros traders et de la foule | plusieurs années |
| DefiLlama | argent frais qui entre ou sort de la crypto (stablecoins) | 2017 |
| alternative.me | peur et avidité | 2018 |
| Yahoo Finance | S&P 500, VIX, or, pétrole, taux US, euro-dollar, Nasdaq, dollar | des décennies |
| Wikipedia | attention du grand public (consultations Bitcoin et Cryptocurrency) | 2015 |
| Fed / BLS | décisions de taux et inflation US | 2024-2026 |

Univers complet : chaque semaine, les 5 plus grosses paires plus un tirage au sort parmi toutes les paires
ayant existé. Les cryptos effondrées puis retirées font partie de l'apprentissage : c'est ce qui évite de
croire que « tout remonte toujours » (biais du survivant).

## Les 8 espèces : les grandes techniques documentées du trading
| Espèce | Technique | Inventeur / référence |
|---|---|---|
| MOMENTUM | acheter la force confirmée par l'équipe | momentum de séries temporelles (Moskowitz) |
| REVERSION | creux dans une tendance de fond haussière | retour à la moyenne |
| BREAKOUT | cassure d'un plus haut avec volume | canaux de Donchian, les Tortues de Richard Dennis |
| RANGE | bas d'un couloir étroit | trading de range |
| BOLLINGER | sortie de compression de volatilité | John Bollinger |
| MACD | croisement au-dessus de zéro | Gerald Appel |
| CONNORS | RSI 2 très bas au-dessus de la moyenne 200 | Larry Connors |
| CONTRARIAN | acheter la panique extrême | principe attribué à Rothschild, repris par Buffett |
L'évolution décide seule quelle espèce mérite de trader. Aucune n'est favorisée d'office.

## Stop-loss : ce que l'évolution peut maintenant choisir
- **Stop ATR** : distance fixe en volatilité (règle des Tortues).
- **Stop structure** : juste sous le plus bas récent, là où l'idée d'achat devient fausse.
- **Prise partielle** : vendre une part (0 à 70 %) à un gain choisi, le reste court avec le stop suiveur.
- Sécurisation au prix d'entrée, stop suiveur, objectif, durée max : tous évolués et tous posés chez Binance.

## Qui a inspiré quoi dans le système
| Principe | Personnalité | Où il vit dans le code |
|---|---|---|
| Couper vite les pertes, ne jamais renforcer une perte | Jesse Livermore | stop chez Binance, aucun renforcement |
| Taille de position selon la volatilité | Richard Dennis, les Tortues | risque 1 % calculé en ATR |
| Prudence dans l'euphorie, opportunité dans la panique | Rothschild, Buffett | PEUR & AVIDITÉ, ATTENTION, espèce CONTRARIAN |
| Marge de sécurité | Benjamin Graham | FILTRE (fenêtre d'entrée), CONTRADICTEUR |
| Les bulles se retournent brutalement | George Soros | ANTI-HYPE, POSITIONNEMENT |
| Défense d'abord | Paul Tudor Jones | GARDIEN, -5 % par jour |
| Diversifier des paris décorrélés | Ray Dalio | CORRÉLATION, quotas d'espèces |
| Éviter la ruine, se méfier des événements rares | Nassim Taleb, Ed Thorp | Monte-Carlo, plafonds de risque |
| Un petit avantage statistique répété | Jim Simons | toute la démarche : mesurer, jamais croire |
| Maîtrise obsessionnelle des coûts | John D. Rockefeller | frais et glissement dans chaque simulation |
Ces principes sont aussi une liste de contrôle que le CONTRADICTEUR vérifie avant chaque achat.
Les grands industriels (Carnegie, Morgan, Rockefeller) ont surtout légué des leçons de gestion
d'entreprise, pas des règles de trading : seules celles qui se traduisent en règle testable sont utilisées.


## Rappel v4 : le système se met à jour tout seul
Chaque stratégie est un **génome** de 30 gènes : espèce, fenêtre, seuil de vote, poids de chaque bot,
vetos activés ou non, stop, sécurisation, stop suiveur, objectif, durée max, déclencheurs d'espèce.
Le même code décide en backtest et en réel : ce qui a été évolué est exactement ce qui est tradé.

Le cycle hebdomadaire (lancé automatiquement le dimanche à 3 h par main.py, ou à la main : `python evolution.py`) :
1. **Observer** : les nouvelles bougies de la semaine s'ajoutent aux archives.
2. **Engendrer** : 128 stratégies par génération, 8 espèces x 16.
   Quotas fixes : une espèce chanceuse ne peut pas éliminer les autres.
3. **Sélectionner** : les 3 meilleures de chaque espèce survivent, 11 enfants naissent de croisements et de
   mutations, 2 nouvelles venues aléatoires entrent. 25 générations (6 pour l'entraînement quotidien).
4. **Juger sur la robustesse** : la note dépend autant de la PIRE période que de la moyenne. Élimination si
   pire baisse > 10 %, profit factor < 1,05, une période perdante, ou moins d'une paire sur deux gagnante.
5. **Coffre-fort** : les 20 % d'historique les plus récents ne sont jamais montrés à l'évolution. On ne l'ouvre
   que pour la meilleure stratégie vivante de chaque espèce. La barre exigée monte à chaque ouverture.
6. **Monte-Carlo** : 1 000 ordres de trades tirés au hasard ; la pire baisse probable doit rester sous 10 %.
7. **Duel réel** : la gagnante devient CHALLENGER. Champion et challenger sont suivis dans l'ombre avec leurs
   propres règles. Après 14 jours et 20 trades minimum, le challenger remplace le champion s'il fait mieux
   d'au moins 0,05 R par trade. Sinon il est éliminé. Échange à chaud, sans redémarrer.
8. **Mémoire génétique** : les survivantes repartent la semaine suivante. Chaque passage part des meilleures.

Ce que l'évolution ne peut JAMAIS modifier : 1 % de risque par trade, -5 % par jour, 3 positions max,
stop posé chez Binance, et les vetos BALEINES, CORRÉLATION, VEILLE et CONTRADICTEUR.

Honnêtement : « s'améliorer chaque jour » signifie qu'un nouveau champion n'est accepté que s'il bat
l'ancien sur des données jamais vues ET en conditions réelles. Le système ne régresse donc pas sur ce qu'il
peut mesurer. Mais aucun champion ne garantit l'avenir : quand le marché change, le suivant prend le relais.

Commandes Telegram en plus : /evolution (champion, challenger, état du duel).
Fichiers : champion.json, challenger.json, population.json, evolution_rapport.txt, evolution_journal.csv
(courbe de progression génération par génération), champions_archive.json.
Conseil frais : dans Binance, activer « Utiliser le BNB pour payer les frais » (-25 %) puis mettre
FRAIS_ALLER_RETOUR_PCT = 0.15 dans config.py. Des frais plus bas rendent rentables davantage de stratégies.


## Comment un bot obtient 8/10
Une note ne se décrète pas dans un prompt : elle se **mesure**. Chaque bot est noté sur 10
selon de combien il améliore l'espérance de gain, en R (1 R = la somme risquée sur un trade).

| Note | Signification | Conséquence automatique |
|---|---|---|
| 8 à 10 | améliore l'espérance d'au moins +0,3 R par trade | **fiable** : poids x1,5 |
| 5 à 8 | effet positif mais faible | en observation : poids x1 |
| moins de 5 | fait pire que le hasard | votant **coupé** (poids 0) ; veto signalé « à revoir » |

- Votants : on compare les trades où le bot disait OUI à ceux où il disait NON.
- Vetos : on compare les trades exécutés aux « trades fantômes » qu'il a bloqués
  (l'AUDITEUR rejoue après coup ce qui se serait passé, avec les règles exactes du GARDIEN).
- Deux sources de notes : le BACKTESTEUR (plusieurs années d'historique, avant de risquer 1 €), puis l'AUDITEUR
  (résultats réels, qui remplacent le backtest dès 30 cas).
- Si aucun votant n'atteint 5/10, l'équipe n'achète plus rien. C'est voulu : pas d'avantage = pas de trade.

## Les 3 garde-fous du backtest v3
1. **Aucune donnée future** : chaque information est datée au moment où elle était réellement connue
   (une donnée journalière n'est utilisée que le lendemain, une bougie supérieure qu'une fois fermée).
2. **Stabilité** : l'historique est coupé en 4 périodes. Un bot noté 9 sur une période et 3 sur une autre
   est instable : sa note est plafonnée à 7,9, il ne peut pas être « fiable ».
3. **Hors échantillon** : les poids sont appris sur les 3 premières périodes, puis l'équipe est jugée sur la
   dernière, qu'elle n'a jamais vue. Seul ce chiffre autorise le passage au testnet.

## Sources de données (toutes gratuites)
| Source | Données | Historique |
|---|---|---|
| data.binance.vision | bougies spot + volume acheteur exécuté | depuis 2017 |
| data.binance.vision | funding des contrats à terme | plusieurs années |
| data.binance.vision | open interest, ratios foule / gros traders | fichiers journaliers (365 j par défaut) |
| DefiLlama | offre totale de stablecoins | depuis 2017 |
| alternative.me | indice Peur & Avidité | depuis 2018 |
| Yahoo Finance | Nasdaq, dollar (DXY) | des décennies |
| Fed / BLS | décisions de la Fed, inflation US | 2024 à 2026 dans le code |
Le premier lancement télécharge tout (compter 15 à 45 min selon la connexion) dans le dossier `archives/`.
Les lancements suivants réutilisent le cache et prennent quelques minutes.

## Les 24 bots

| Bot | Type | Source | Noté par |
|---|---|---|---|
| CALENDRIER | veto global | dates Fed et inflation US (config.py) | backtest |
| MÉTÉO | veto global | tendance du Bitcoin 1 h | backtest |
| PEUR & AVIDITÉ | taille des positions | alternative.me (gratuit) | backtest |
| SCOUT | scan | 150 paires les plus échangées | — |
| FILTRE | 6 checks | volume, spread, pump, liquidité, historique, fenêtre | — |
| RISK | veto | volatilité, doublon, quarantaine | backtest + réel |
| ANTI-HYPE | veto | pic de volume, +8 %/h, tendances CoinGecko | backtest + réel |
| TENDANCE | vote | moyennes 15 min | backtest + réel |
| MOMENTUM | vote | RSI + volume | backtest + réel |
| MULTI-UNITÉS | vote | confirmation 1 h et 4 h | backtest + réel |
| CARNET | vote | carnet d'ordres + achats réellement exécutés | backtest + réel |
| DÉRIVÉS | veto + vote | funding et évolution de l'open interest | backtest + réel |
| BALEINES | veto + vote | ordres de plus de 100 000 USDT | réel |
| CORRÉLATION | veto | pas deux positions = même pari | réel |
| VEILLE | veto | presse (CoinDesk, Cointelegraph, Decrypt) + IA | réel |
| LIQUIDITÉ | veto + vote | offre de stablecoins sur 7 jours (DefiLlama) | backtest + réel |
| MACRO | veto + vote | Nasdaq et dollar (Yahoo Finance) | backtest + réel |
| POSITIONNEMENT | veto + vote | foule trop acheteuse ? gros traders plus optimistes ? | backtest + réel |
| DÉVELOPPEURS | vote léger | activité GitHub via CoinGecko | réel |
| CONTRADICTEUR | veto final | IA qui cherche les raisons de ne PAS acheter | réel |
| LEADER | décision | vote pondéré par les notes | — |
| GARDIEN + TRAILING | exécution | stop chez Binance, sécurisation, stop suiveur | — |
| AUDITEUR | notation | trades réels + fantômes | — |
| BACKTESTEUR | notation | historique Binance public | — |

## Installation
1. Python 3.11+ (sous Windows, cocher « Add Python to PATH »).
2. Dans ce dossier : `pip install -r requirements.txt`
3. Copier `.env.example` en `.env` et le remplir (voir ci-dessous).

Clés :
- Démo Binance (recommandé) : https://demo.binance.com → Gestion des API → créer une clé ; `MODE=demo`.
- Testnet (ancien, prix artificiels) : https://testnet.binance.vision → Log In with GitHub ; `MODE=testnet`.
- Telegram : @BotFather → /newbot (token) ; envoyer un message au bot, puis @userinfobot (ton id).
- IA (optionnel) : https://console.anthropic.com. Sans clé, VEILLE garde son filtre par mots-clés
  et CONTRADICTEUR s'abstient.
- CoinGecko (optionnel) : clé « Demo » gratuite sur coingecko.com. Sans clé, DÉVELOPPEURS s'abstient.

## Ordre obligatoire
1. **Backtest comparatif** : `python backtest.py --comparer` (2 ans, 25 paires, en 15 min, 1 h et 4 h).
   Plus long : `python backtest.py --comparer --jours 1095 --paires 30`.
   Il recommande l'unité à mettre dans `UNITE_BOUGIE` (config.py). Des trades en 4 h durent plusieurs jours :
   c'est normal, et c'est souvent là que les frais pèsent le moins.
   Lis `backtest_rapport_<unité>.txt`. Sans espérance hors échantillon positive, on ajuste avant d'aller plus loin.
2. **Testnet** : `python main.py` avec `MODE=testnet`, au moins 4 semaines.
   Tape /notes sur Telegram pour suivre le bulletin des bots.
3. **Vérification** : `python verifier.py` doit afficher ✅.
4. **Première évolution** : `python evolution.py` (après avoir réglé UNITE_BOUGIE). Lis `evolution_rapport.txt`.
   Ensuite main.py la relance seul chaque semaine.
5. **Lancement** : `python lanceur.py` (mode démo d'abord, 4 semaines minimum).
6. **Réel**, seulement si l'espérance reste positive : clé API avec « Enable Spot Trading » uniquement,
   JAMAIS « Enable Withdrawals », restreinte à ton IP ; `MODE=reel` ; `CAPITAL_MAX_USDT` = une somme
   que tu acceptes de perdre entièrement.

Commandes Telegram : /statut, /notes, /stop, /reprise, /vendre_tout.

## Entretien
- Chaque fin d'année : ajouter les dates Fed et inflation US de l'année suivante dans `EVENEMENTS_MACRO`
  (config.py) et les dates passées dans `MACRO_PASSE` (backtest.py).
- Le dossier `archives/` peut peser plusieurs centaines de Mo : on peut le supprimer, il se reconstruit.
- Relancer le backtest tous les mois : les marchés changent, les notes aussi.

## Limites honnêtes
- Aucun réglage ne garantit un gain. L'objectif est une espérance positive avec des pertes plafonnées.
- Un backtest surestime toujours un peu la réalité (paires choisies aujourd'hui : les cryptos mortes entre-temps n'y sont pas).
- Yahoo Finance est une source non officielle : si elle tombe, MACRO s'abstient au lieu de bloquer l'équipe.
- Le testnet prouve que la mécanique fonctionne, pas que la stratégie gagne.
- En cas de krach brutal, le prix peut sauter au-delà du stop : la perte peut alors dépasser 1 %.

## Fiscalité (France)
Plus-values crypto imposées à 30 % lors d'une conversion en euros. Compte sur plateforme étrangère
à déclarer (formulaire 3916-bis). Garde `journal.db` comme historique.

## V12 — scanner universel

Le système ajoute un `InstrumentRegistry` pour normaliser les instruments Binance et Trade Republic, un `UniversalScanner` pour filtrer automatiquement les actifs inactifs, sans cotation, trop peu liquides ou trop larges, et un `correlation_engine` pour limiter les expositions redondantes. Trade Republic reste séparé de l'exécution Binance : aucune API privée n'est inventée.

V12.1 : ces trois modules sont **branchés** dans le bot en marche (SCOUT, veto CORRÉLATION, univers Trade Republic en suivi). Commande Telegram `/univers`. Détails : `UNIVERS_SCANNER_V12.md`.

## V13 — veille Trade Republic

Un second service (`equipe-bots-tr`) lit chaque jour la liste officielle des titres Trade Republic, relie chaque
ISIN à Yahoo Finance et envoie sur Telegram des signaux d'achat et de vente **à exécuter toi-même** (filtre
4 unités, coûts TR, suivi stop / objectif / retournement). Commande Telegram `/tr`. Détails :
`VEILLE_TRADE_REPUBLIC.md`.

## V14 — toutes les paires + exploration (démo)

Toutes les paires USDT de Binance sont scannées. En démo, le mode EXPLORATION laisse l'équipe prendre des risques
mesurés pour que des transactions aient lieu et que les notes /10 apprennent de vrais résultats (niveaux 0 à 3,
`/exploration` sur Telegram). Verrouillé : jamais en argent réel. Détails : `EXPLORATION.md`.

## V15 — Bot Factory

Cette version ajoute une couche générique au-dessus de V14.1. V14 reste le domaine Finance/Crypto historique; V15 introduit un catalogue de 360 rôles de bots, une factory, un orchestrateur, une policy d'autorisation et un évaluateur. Voir `ARCHITECTURE_V15.md`, `BOT_CATALOGUE_V15.md` et `MIGRATION_V14_V15.md`.

Générer/exporter le catalogue:

```bash
python GENERATE_V15.py
```

Tester la couche V15:

```bash
python -m pytest -q tests_v15
```
