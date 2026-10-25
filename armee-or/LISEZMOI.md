# Armée de l’or 2.5-R5.2 — R4 + multi-marchés + équipe vidéo, pilotée par Termius et Telegram

## 25 octobre 2026 (R5.2) — tout depuis Termius et Telegram, comme avant

Décision du propriétaire : l’armée se pilote et se met à jour **uniquement depuis Termius et Telegram**, comme avant R3. Plus de zip à enregistrer dans Fichiers ni à envoyer par SFTP.

- `or maj` (Termius) et `/or_maj` (Telegram) sont rétablis : ils téléchargent la version publiée sur GitHub et l’installent, avec les contrôles de R4 (tests sur le serveur, sauvegarde, pause).
- Le risque qui avait fait bloquer `/or_maj` en R3, revenir à une version plus ancienne qui contournerait le permis, est fermé : seule une version **strictement plus récente** s’installe. Le contrôle est fait par une copie root, que le compte des bots ne peut pas modifier.
- Après l’installation, l’armée est en pause, et on te donne les commandes pour reprendre exactement ce qui tournait.
- `or retour IDENTIFIANT` revient à la version d’avant, depuis Termius.
- Première fois : la ligne à coller est dans « Installer et mettre à jour » ci-dessous.
- Tests : 229 (238 avec TA-Lib), tous réussis sous Python 3.11, 3.12 et 3.13. Les 8 nouveaux couvrent l’ordre des versions, le refus d’une version plus ancienne (même si le compte des bots falsifie son dossier), les services `/or_maj`, les commandes de reprise, et un garde-fou : le paquet publié doit avoir ses empreintes et sa version à jour.

## 25 octobre 2026 (R5.1) — contrôle complet, banc recalibré

**Gagner à chaque trade ?** Mesuré sur 34 marchés réels (2000-2026), trade par trade (`etudes/variantes.py`) :

| Ce qu'on force | Trades gagnants | Résultat |
|---|---|---|
| Rien : règle des 200 jours, stop 5 ATR (l'équipe multi-marchés) | 22 % | **gagnante** : Sharpe +0,35 / +0,52, pire baisse −14 % |
| Prise de gain rapide à 0,5 ATR | 81 % | **perdante** sur les deux moitiés |
| Prise de gain à 1 ATR | 70 % | nulle |
| Ne jamais fermer à perte | 90 à 97 % | pertes cachées (jusqu'à −310 % de la mise d'un marché), positions bloquées jusqu'à 18 ans, pire baisse −31 % |

- Aucune règle connue ne rend chaque trade positif.
- Viser la fréquence des petits gains fait perdre : chaque petit gain est payé par des pertes plus grosses et plus rares.
- Les vidéos montrent l'autre façon d'avoir « 100 % de trades gagnants » : ne jamais fermer une perte, jusqu'à la ruine (99,98 % des tentatives).
- L'armée vise donc un **résultat net positif**, avec des pertes petites, limitées par un stop et visibles. `/or_marches` montre désormais, trade par trade, la part de gagnants, le gain moyen, la perte moyenne et le pire trade.

**La démo R4 est perdante sur l'historique.** Sa propre fonction de signal, rejouée sur l'or de 2021 à 2026 (`etudes/regle_r4.py`, données livrées) :

- 2 783 trades, 44 % gagnants, −0,04 R par trade ;
- perdante de 2021 à 2024, légèrement gagnante en 2025-2026 seulement, pendant la forte hausse de l'or.

Si tu veux seulement ce qui a gagné sur l'historique : `/or_demo_off` (ou `or demo off`). `/or_demo` affiche maintenant cette mesure.

**Le banc d'essai recalibré.** Il achetait au cours de clôture qui avait servi à décider. Il exécute maintenant à l'ouverture suivante, comme l'équipe en direct. Le résultat ne bouge presque pas (+0,35 / +0,52 au lieu de +0,31 / +0,51) et le permis est maintenu. Le permis exige aussi 30 entrées sur **chaque** moitié, et non plus 30 au total.

**Tests ajoutés.** La suite compte 221 tests : tous réussis, 1 ignoré sans TA-Lib. Avec TA-Lib : 230 réussis, sous Python 3.11 (celui du pont sous Wine), 3.12 et 3.13, chaque fichier seul et trois fois de suite. Les nouveaux tests :

- aucune donnée du futur : changer tout ce qui suit un jour ne change rien avant ce jour ;
- l'équipe en direct, rejouée bougie après bougie, achète et vend les mêmes jours que le banc ;
- 500 demandes d'ordre au hasard sur le chemin multi-marchés : jamais de vente, jamais d'ordre sans stop sous le cours, une position par marché, jamais plus de 2 % de pertes cumulées jusqu'aux stops, rien sur un compte réel ;
- 400 demandes au hasard sur le chemin vidéo : jamais plus de 10 positions, jamais de stop.

**Installation** : voir « Installer et mettre à jour » ci-dessous (R5.2 : plus de zip).

## 25 octobre 2026 — ce que R5 ajoute

R5 part de R4, la version installée sur ton serveur, et lui ajoute deux équipes. **Rien de R4 n’est retiré** : la démo expérimentale (770090), ses règles, ses freins et les verrous R3 des anciennes équipes restent identiques.

| Équipe | Où | Ordres | Au démarrage |
|---|---|---|---|
| Multi-marchés (770050) | compte démo de l’armée | achats sous permis de son banc d’essai | **désactivée** |
| Vidéo (770077) | 2e compte démo séparé, à fort levier | méthode des vidéos, sans stop | **désactivée** (et pas branchée tant que `or video installer` n’est pas fait) |

Les deux ne passent **aucun ordre** sans ton activation explicite, comme `/or_demo_on` :

- **Multi-marchés** : `/or_marches_on` (ou `or marches on`).
  - L’activation vérifie le compte démo et l’absence d’incident R2.
  - Même activée, l’équipe n’achète que si son banc d’essai lui accorde le permis : gagner sur chaque moitié de l’historique du courtier ET battre « toujours acheter ».
  - Désactivée, elle montre ce qu’elle achèterait (`/or_marches`).
- **Vidéo** : `/or_video_on` (ou `or video on`), après `or video installer`. L’activation vérifie que le 2e compte est connecté et en démo.

Les deux activations lèvent la pause générale, comme `/or_demo_on`. `/or_marches_on` lève aussi la pause MT5.

**Les verrous R3 ne sont pas touchés.**

- Le pont de l’armée refuse toujours les anciennes ouvertures (`ouvrir`) et ne dimensionne que l’or pour elles.
- **Le multi-marchés passe par son propre chemin, `marches_ouvrir`** :
  - achat seulement, stop obligatoire chez le courtier ;
  - une position par marché ;
  - au plus 0,5 % du compte risqué par ordre ;
  - le **plafond R3 de 2 %** de pertes cumulées jusqu’aux stops, toutes positions du compte comprises, s’applique : cela fait environ 6 marchés tenus à la fois avec un stop à 5 ATR.
  - Le banc d’essai suppose tout le panier ; le plafond en tient moins, ses résultats sont donc un plafond optimiste.
- **L’équipe vidéo passe par `video_ouvrir`.**
  - Ce chemin n’existe que sur le pont du 2e compte (instance `video`, port 18778).
  - Ce pont refuse `ouvrir`, `dimensionner`, `demo_*` et `marches_ouvrir`.
  - Le pont de l’armée refuse `video_ouvrir`.
- **Ordre incertain** : l’intention du multi-marchés est écrite avant l’envoi (`r2:ordre_incertain`). Une réponse perdue verrouille toutes les entrées, comme en R2.
  - Ordre retrouvé chez le courtier : il est adopté.
  - Ordre jamais exécuté (vérifié 10 min plus tard) : le verrou est levé.
  - Dans les deux cas, `/or_marches_on` est nécessaire pour reprendre.

**À savoir** : la démo R4 exige un compte sans aucune position. Une position multi-marchés ouverte bloque donc ses nouvelles entrées. Choisis l’une ou l’autre, ou accepte que la démo R4 attende.

## Installer et mettre à jour : Termius et Telegram seulement

**Une seule fois**, pour passer ton serveur de R4 (ou R5) à R5.2, colle cette ligne dans Termius, en root :

```bash
D=$(mktemp -d) && curl -fsSL https://github.com/antoineplaton20/ai-market-watch-/archive/refs/heads/claude/termius-binance-bot-optimization-g98ihl.tar.gz | tar -xz -C "$D" && bash "$D/ai-market-watch--claude-termius-binance-bot-optimization-g98ihl/armee-or/installer_or.sh" installer
```

**Ensuite, chaque mise à jour** se fait avec `or maj` (Termius) ou `/or_maj` (Telegram, le résultat arrive dans Telegram).

Dans les deux cas, l’installateur procède ainsi :

- **jamais de retour en arrière** : la version publiée doit être strictement plus récente que celle notée par root à la dernière installation (`/var/lib/armee-or`, que le compte `bots` ne peut pas modifier) ;
- il refuse une installation inconnue : seuls R4, R5, R5.1 ou la base acceptée par R4 sont migrés ;
- il lance tous les tests sur le serveur avec son Python, et s’arrête au moindre échec, sans rien modifier ;
- il sauvegarde le code, la base et les réglages dans `/var/backups/armee-or-r5/` ;
- il pose les fichiers et redémarre uniquement les services de l’armée. Le pont du 2e compte n’est relancé que s’il tournait.

**Chaque nouvelle version démarre en pause** : rien ne passe d’ordre sans toi. L’installateur, et le message Telegram après `/or_maj`, donnent les commandes pour reprendre exactement ce qui était actif, par exemple `/or_marches_on` · `/or_demo_on`. Vérifie avec `or diagnostic`, `or mt5` et `or marches`.

**2e compte pour l’équipe vidéo** (facultatif) : `or video installer`. Le login, le mot de passe PRINCIPAL et le serveur se tapent dans Termius, jamais dans une conversation. Ensuite : `/or_video_on`.

**Retour à la version d’avant** : `or retour IDENTIFIANT`, avec l’identifiant affiché à l’installation. Il est refusé dans trois cas :

- une position multi-marchés est ouverte : `or marches fermer` d’abord ;
- un panier vidéo est ouvert : `or video fermer` d’abord ;
- la démo R4 est active ou en incident, comme en R4.

Revenu à R4, le pont du 2e compte est arrêté et désactivé, car R4 ne sait pas le piloter. Après un retour, `or maj` n’installe que la version suivante, pas celle qu’on vient de quitter.

Plus aucun zip ni SFTP. `or mettre-a-jour` renvoie vers `or maj`.

Résultats des tests (terminal MT5 simulé, aucun compte réel) : `validation/tests_R5.2.txt`. Ceux de R4, R5 et R5.1 restent à côté.

## Armée multi-marchés : tout MT5 (`/or_marches`)

**Décision du 25/10/2026** : l'armée ne vise plus seulement l'or, mais tous les marchés de MT5 (forex, métaux, énergie, matières agricoles, indices, crypto).

**Ce que la mesure a montré**, sur 34 marchés (Yahoo 2000-2026, frais et financement compris) :

- La règle la plus simple et la mieux documentée gagne : n'être acheteur d'un marché qu'**au-dessus de sa moyenne de 200 jours** (Paul Tudor Jones ; Faber, 2007), avec une taille réglée par la volatilité.
- Son Sharpe va de +0,47 à +0,81 selon le coût du financement. Elle est positive sur les deux moitiés (2000-2013 et 2013-2026), avec une pire baisse moitié moindre que « tout acheter ».
- Le croisement 20/50 jours de la 3e vidéo ne fait pas mieux que « tout acheter ». La cassure des Turtles perd après frais.
- C'est la diversification qui travaille, pas la prédiction.

**Ce que fait l'équipe** (`marches.py`, numéro magique 770050, jamais gérée par l'exécutant de l'or) :

1. **Inventaire** : la liste de tous les symboles du courtier, et un panier d'environ 34 marchés liquides choisi automatiquement, quels que soient leurs noms chez ce courtier (EURUSD.a, XAUUSDm, US500.cash…).
2. **Archive** : les bougies journalières de chaque marché, depuis 2000 si le courtier les a.
3. **Banc d'essai** : chaque règle, sur chaque marché, avec les écarts et les swaps réels du courtier, sur deux moitiés.
4. **Permis** : une règle trade seulement si le portefeuille gagne sur chaque moitié ET bat « toujours acheter » le même panier. Le permis est revu chaque heure, et tu es prévenu (🪪) dès qu'il change.
5. **Équipe** (R5 : seulement après `/or_marches_on`, et sous permis) : une décision par marché et par bougie journalière close.
   - Achat au-dessus de la règle, sortie en dessous.
   - Taille réglée par la volatilité.
   - Stop de catastrophe chez le courtier à 5 ATR.
   - Pas de nouvel achat sous coupe-circuit, frein du jour, `/or_pause`, incident R2 ou au-delà de 50 % de marge utilisée.
   - Plafonds du pont : 0,5 % risqué par ordre, 2 % cumulés sur tout le compte (règle R3).

**Le capital décide du nombre de marchés.** Seuls les marchés dont le lot minimum tient dans le budget de risque sont tradés. Avec environ 2 700 €, l'or, le pétrole ou le Bitcoin sont trop gros au lot minimum (0,01), contrairement à la plupart des paires de forex et aux indices. `/or_marches` montre les marchés tenables et les exclus. Pour voir le portefeuille complet, il faut un compte démo avec un solde plus élevé.

**Honnêtement** : c'est une stratégie lente, avec des positions gardées des semaines ou des mois, quelques pertes et des gains plus rares mais plus gros. Elle n'est pas « positive à chaque trade ». Sur 26 ans, sa force est de baisser deux fois moins que « tout acheter ».

**Commandes** :

- `/or_marches` : inventaire, banc, permis, capital et positions ;
- `/or_marches_on` : activer (vérifie le compte et les incidents) ; `/or_marches_off` : arrêter les achats (les positions gardent leurs sorties et leurs stops) ;
- `/or_marches_fermer` : tout fermer ;
- dans Termius : `or marches`.

**La 3e vidéo**, analysée image par image et transcrite : un tutoriel en anglais (Claude Code et Alpaca), sur des actions américaines et un compte papier de 50 000 $, avec un croisement 20/50 jours sur Apple. Elle ne montre aucun résultat réel, et la courbe de gains affichée est une illustration. L'auteur prévient lui-même que la règle perd en marché sans tendance.

**L'équipe vidéo sur d'autres marchés** : `/or_video_symbole_eurusd` (ou un autre nom) fait jouer le prochain panier sur ce marché ; `/or_video_symbole_or` ramène l'équipe sur l'or. Le gain et la mise sont ramenés à la même part du prix que sur l'or.

## Équipe vidéo : 2e compte démo à fort levier (`/or_video`)

**Les deux vidéos envoyées le 25/10/2026**, analysées image par image (une image toutes les 3 secondes) :

| | Vidéo 1 | Vidéo 2 |
|---|---|---|
| Compte | 2,02 $ → 218 697 $ en 74 min | 9,88 $ → 129 861 $ en 51 min |
| Marché | uniquement l'or (XAUUSDm) | uniquement l'or (XAUUSDm) |

- **La méthode** : 7 à 10 positions identiques, fermées ensemble dès 1 à 3 $ de gain par once, **aucun stop**. La mise est relancée après chaque gain jusqu'à la limite de marge (niveau de marge vu à 87 %, 91 % et 99 %).
- **« Positif à chaque trade »**, seulement parce que les pertes ne sont jamais fermées. Elles sont visibles à l'écran : 7 × −157,92 $, puis −2 817 $.

**Rejouée avec les mêmes règles sur l'or réel** (bougies 1 min, janvier-septembre 2026, fonction `video.simuler`) :

- 167 040 loteries : départ à 2,02 $ ou 9,88 $, gain pris à 1, 2 ou 3 $ par once ;
- le résultat des vidéos est atteint **4 fois**, soit 1 sur 42 000 ;
- **99,98 % des loteries sont ruinées en moins de 24 h**.

Les vidéos montrent les rares gagnants d'une loterie.

**L'équipe vidéo.** À la demande du propriétaire, elle rejoue cette méthode **à l'identique sur un 2e compte DÉMO** (argent fictif), à côté de l'armée :

- **Séparée de l'armée** : elle a son terminal MT5 (une copie du préfixe Wine), son pont (127.0.0.1:18778), son service `armee-or-mt5-video` et son numéro magique 770077. Le compte de l'armée et ses identifiants ne sont jamais touchés.
- **Chaque loterie est comptée** : départ, record, paniers gagnés, ruine. Telegram annonce chaque départ, chaque palier (×10, ×100…) et chaque ruine.
- **Après une ruine**, il suffit de remettre le solde du compte démo (dans l'espace du courtier) : la loterie suivante démarre seule.
- **Démo seulement** : le pont refuse tout ordre si le compte n'est pas un compte démo.

**Mise en route (Termius) :**

1. Crée un compte DÉMO à fort levier avec un petit solde (2 à 10 $) : dans l'app MT5, Réglages > Nouveau compte, ou depuis l'espace client du courtier.
2. Lance `or video installer` et entre le login, le mot de passe et le nom exact du serveur. La copie du terminal prend 2 à 5 min, la connexion 5 min au plus.
3. Active-la avec `/or_video_on` (R5 : elle reste désactivée jusque-là), puis suis-la avec `/or_video`. Réglages :
   - `/or_video_gain_2` : fermeture des paniers à +2 $ par once ;
   - `/or_video_off` : plus de nouveau panier (celui en cours se ferme à son gain) ;
   - `/or_video_fermer` : tout fermer tout de suite.
4. `or video rejouer` rejoue la méthode sur les bougies 1 min du courtier (environ 3 mois).

## Prompt maître (`/or_prompt`)

`PROMPT_MAITRE.md` est la consigne complète à donner à l'IA (Claude ou une autre) qui conçoit, code et améliore l'armée. Il contient :

- la mission ;
- les douze lois d'airain : la preuve avant l'argent, aucune donnée du futur, les frais réels, battre le naïf, le risque d'abord… ;
- les faits déjà mesurés ;
- l'économie et l'histoire de l'or depuis 1900 ;
- les chandeliers et les écoles de l'analyse technique ;
- les grands traders, investisseurs et économistes, français compris. Chacun est traduit en hypothèse testable (H01 à H22) ou en leçon ;
- la méthode de preuve : banc d'essai, étalons, permis ;
- les chantiers.

Pour s'en servir :

- **Sur Telegram** : `/or_prompt` envoie le fichier, à transmettre tel quel à une IA.
- **Avec Claude Code** : écris « Lis armee-or/PROMPT_MAITRE.md puis attaque le chantier n° 1 ». Le fichier `CLAUDE.md` du dossier le rappelle à chaque session.
- **Version courte** : pour une IA qui ne lit pas les longs fichiers, le « prompt court » du §0 suffit.

## R4 (23 octobre 2026) — démo expérimentale, choix explicite du propriétaire

Le propriétaire a choisi « Démo expérimentale » : achats et ventes automatiques de test sans preuve de rentabilité, avec compte démo obligatoire et limites de risque. Cette autorisation remplace l’exigence de permis statistique UNIQUEMENT pour l’équipe expérimentale R4. Les anciennes équipes restent verrouillées et aucun permis scientifique n’est déclaré acquis.

La R4 ajoute une équipe d’exécution dédiée, numéro magique 770090. Les autres bots continuent leurs analyses. Il ne s’agit pas d’une certification de rentabilité, ni de la réalisation de tous les chantiers de recherche du prompt.


## Activer les achats et ventes automatiques

Une seule des deux commandes suffit :

- Termius : `or demo on`
- Telegram : `/or_demo_on`

La commande est traitée par le chef et sa réponse confirme l’activation ou explique le refus. La première activation exige un compte démo hedging sans position ni ordre en attente. Elle fixe le compte autorisé et le point de départ du risque expérimental. Elle lève les pauses générales et MT5 ; les anciennes équipes demeurent bloquées par leurs verrous.

Le programme ouvre un achat OU une vente quand ses conditions sont réunies. L’activation n’envoie pas un ordre immédiatement : il attend une clôture de bougie, un signal concordant et tous les contrôles.

- État et dernier motif d’attente : `or demo` ou `/or_demo`.
- Compte et positions : `or mt5` ou `/or_mt5`.
- Arrêter les nouvelles entrées expérimentales : `or demo off` ou `/or_demo_off`.
- Pause générale : `or pause` ou `/or_pause`.
- Reprendre après une pause : `or demo on` ou `/or_demo_on` (aucune remise à zéro du risque).
- Fermer les positions de l’armée et suspendre : `or mt5 fermer` ou `/or_mt5_fermer`.

On peut fermer Termius : les services restent sur le serveur. Une interruption du chef laisse les stops et objectifs chez le courtier ; les sorties à échéance nécessitent que le chef et le pont fonctionnent.

## Règle expérimentale fixe

- Or contre dollar, données du même terminal MT5 que l’exécution.
- Bougies closes de 15 minutes et 1 heure, 300 demandées par unité (100 closes au minimum).
- Achat : clôture > EMA20 > EMA50 sur les deux unités. Vente : clôture < EMA20 < EMA50 sur les deux unités. Sinon, attente.
- ATR14 de Wilder en 15 minutes. Stop à 3 ATR ; objectif à 6 ATR ; horizon maximal 4 heures.
- Stop et objectif envoyés avec l’ordre au courtier. Aucune martingale, aucun élargissement du stop, aucun renforcement.
- Lot minimum du symbole uniquement ; jamais augmenté pour rattraper une perte.
- Risque au stop, converti par MT5 en devise du compte et majoré d’une réserve de 25 %, au plus 0,25 % de l’équité. Si le lot minimum dépasse ce budget, aucun ordre.
- Une seule position à la fois. Toute position ou tout ordre en attente sur le compte bloque les nouvelles entrées. Les positions manuelles ne sont pas fermées.
- Au plus 3 tentatives d’entrée par jour UTC, et au moins une heure entre deux tentatives. Une bougie n’est jamais rejouée.
- Entrées du lundi au vendredi, 7 h inclus à 16 h exclu UTC, dans les 120 secondes suivant une clôture 15 min. Sortie au plus tard vendredi 20 h UTC.
- Écart achat/vente limité au plus petit de 2 USD ou 10 % de l’ATR. Dernier cours vieux d’au plus 60 secondes.
- Calendrier USD à fort impact âgé d’au plus 6 heures ; aucune entrée ±15 minutes autour d’une annonce. Le calendrier doit être valide et le bot conserve ses limites de couverture : il n’anticipe pas les nouvelles imprévues.

Ces réglages sont des choix fixes pour un essai, pas des paramètres optimisés ou une preuve d’avantage. Un stop ne garantit pas le prix final en cas de trou de cotation. Les commissions, swaps et glissements peuvent augmenter la perte effective au-delà du risque visé.

## Freins et incidents

Les freins expérimentaux sont supplémentaires à ceux de l’armée :

- −1 % d’équité depuis le premier contrôle du jour UTC : arrêt des entrées jusqu’au jour suivant et demande de fermeture de la position expérimentale ;
- −3 % depuis le sommet observé de l’expérience : coupe-circuit persistant et demande de fermeture ;
- réponse d’ordre incertaine : intention conservée et aucune nouvelle entrée ;
- compte changé ou réel : aucune action de trading ;
- stop/objectif non conformes après exécution : fermeture demandée et incident conservé.

Un arrêt puis une réactivation ne remet pas les compteurs à zéro. Le coupe-circuit et les ordres incertains exigent un diagnostic ; aucun bouton ne les efface automatiquement. Les fermetures refusées ou partielles sont réessayées aux passages suivants. Une erreur du courtier peut empêcher une fermeture : consulter les positions dans MT5.

L’état durable du pont est dans `runtime/demo-r4.json`. Le journal des intentions et réponses est `runtime/demo-r4-journal.jsonl`. Les rapports Linux restent en SQLite. Ne pas supprimer ni restaurer ces fichiers pendant que des positions existent. Une sauvegarde SQLite seule ne contient pas l’état propre du pont ; une migration de serveur doit aussi conserver ces fichiers et vérifier les positions avant toute réactivation.

## Validation et portée

La suite locale utilise un terminal MT5 simulé et aucun compte réel. Les tests couvrent les deux sens, les bougies closes, la causalité du signal, les prix périmés, le calendrier, le risque, la pause, les protections courtier, la réponse perdue, la reprise après panne et les fermetures partielles. Les résultats figurent dans `validation/tests_R4.txt` et `validation/resultats_R4.xml`.

Le code du pont et ses deux modules autonomes n’utilisent que la bibliothèque standard de Python et MetaTrader5. Aucune nouvelle dépendance réseau ou clé d’IA n’est ajoutée. Référence de l’API : https://www.mql5.com/en/docs/python_metatrader5/mt5ordersend_py

Aucun ordre ni déploiement n’a été exécuté sur ton serveur depuis l’environnement de développement. Le résultat financier de cet essai reste inconnu. Le banc statistique complet, l’observation shadow et la qualification du prompt restent des travaux distincts ; les tests logiciels ne les remplacent pas.

