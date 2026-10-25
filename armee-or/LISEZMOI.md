# Armée de l'or — v2.4 (avec MetaTrader 5 démo, pilotable depuis l'iPhone)

Des bots dédiés **uniquement à l'or**. Ils tournent **à côté** de l'équipe V17.9, sans jamais la toucher :

| | Équipe V17.9 | Armée de l'or |
|---|---|---|
| Dossier | `/home/bots/equipe-bots` | `/home/bots/armee-or` |
| Python | son `.venv` | son propre `.venv` |
| Base de données | la sienne | `runtime/or.db` (SQLite) |
| Services | `bots-*` | `armee-or-flux`, `armee-or-chef`, `armee-or-mt5` |
| Télécommande | `bots` | `or` |
| Clé Claude | – | **aucune** |

Les comptes de levier x1 → x50 restent **simulés sur papier**. Si tu branches MetaTrader 5, l'armée passe aussi de **vrais ordres sur ton compte DÉMO** (argent fictif). Elle refuse tout ordre sur un compte réel : le contrôle est fait deux fois, dans le chef et dans le pont MT5. Aucune clé Binance n'est demandée.

## Installation et mises à jour (iPhone + Termius, en root)

1. Aucun zip ni SFTP : colle cette ligne dans Termius. Elle télécharge la dernière version publiée sur GitHub et lance l'installation :
   ```
   curl -fsSL https://github.com/antoineplaton20/ai-market-watch-/archive/refs/heads/claude/termius-binance-bot-optimization-g98ihl.tar.gz | tar -xz -C /root && bash /root/ai-market-watch--claude-termius-binance-bot-optimization-g98ihl/armee-or/installer_or.sh
   ```
2. Ensuite, chaque mise à jour se fait en tapant simplement `or maj`.
3. Choisis le Telegram :
   - **Recommandé** : crée un nouveau bot avec @BotFather (`/newbot`), colle le jeton, puis envoie « bonjour » à ce nouveau bot. Tu pourras ensuite lui envoyer `/or`, `/or_levier`, `/or_bilan`, `/or_pause`, `/or_reprise`, `/or_bibliotheque`, `/or_mt5`, `/or_mt5_fermer`, `/or_mt5_reprendre`.
   - **Sinon**, appuie sur Entrée : ton bot actuel est réutilisé en **envoi seul**, avec des messages préfixés 🟡 [or]. Il ne lit jamais les messages, pour ne pas voler les commandes de l'équipe V17.9.
4. À la question « Brancher ton compte DÉMO MetaTrader 5 ? », réponds **O**. Donne ensuite :
   - le login ;
   - le mot de passe **principal**, qui reste invisible pendant la frappe (le mot de passe investisseur ne permet que la lecture) ;
   - le serveur (`MetaQuotes-Demo` par défaut).
5. L'installateur :
   - lance les tests et s'arrête si un seul échoue ;
   - importe l'historique livré (environ 5 s) ;
   - installe Wine, un écran virtuel, le terminal MT5 et Python pour Windows avec la bibliothèque officielle MetaTrader5 (10 à 20 minutes la première fois) ;
   - démarre les services.

## Tout depuis l'iPhone

- **Installer** : enregistre le zip dans l'app Fichiers. Dans Termius, ouvre ton serveur, puis SFTP : envoie le zip dans `/root`. Colle ensuite les deux commandes d'installation dans le terminal.
- **Piloter** : dans ton bot Telegram dédié, touche le bouton **Menu** (ou tape `/`). Toutes les commandes y sont, et les réponses contiennent des commandes à toucher, par exemple `/or_profil_x20` ou `/or_entrainement_off`.
- **Voir les positions** : dans l'app **MetaTrader 5** pour iPhone, connectée au même compte démo.
- **Termius** ne sert qu'en secours (`or etat`, `or mt5 journal`).

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
3. Suis l'équipe avec `/or_video`. Réglages :
   - `/or_video_gain_2` : fermeture des paniers à +2 $ par once ;
   - `/or_video_off` et `/or_video_on` : arrêter ou reprendre les nouveaux paniers ;
   - `/or_video_fermer` : tout fermer tout de suite.
4. `or video rejouer` rejoue la méthode sur les bougies 1 min du courtier (environ 3 mois).

## Commandes Termius

```
or etat          cours en direct, rythme, marchés liés, pronostics, comptes papier, santé des bots
or levier        fiches x1 → x50 : marge, prix de liquidation, perte au stop, risque historique
or bilan         bilan sur tout l'historique (sans regarder le futur, frais compris)
or bibliotheque  études et manuels utilisés
or pause|reprise positions papier suspendues / reprises (l'analyse continue)
or journal       journal en direct
or demarrer|arreter|redemarrer
or test          contrôle complet
or mt5           compte MT5 démo : solde, positions de chaque équipe, résultats
or mt5 fermer    ferme toutes les positions de l'armée et suspend ses ordres (or mt5 reprendre)
or mt5 profil x20            levier des décisions : x1 x3 x5 x10 x20 x50 ou pro (défaut : pro 1 % risqué)
or mt5 entrainement on|off   équipe d'entraînement au lot minimum
or mt5 journal | compte      journal du pont MT5 / changer de compte démo
or mettre-a-jour /root/armee-or-vX.zip
or config        refaire le réglage Telegram
```

## L'armée

Le **chef d'orchestre** (`armee-or-chef`) fait passer chaque bot à son tour, toutes les quelques secondes. Chaque passage est inscrit dans la table `rapports` : réussite, durée, message. Si un bot échoue :

- ses tentatives sont espacées, jusqu'à 1 h maximum ;
- après 5 échecs, une alerte part sur Telegram ;
- **les autres bots continuent**.

systemd relance les services quoi qu'il arrive : `Restart=always`, sans limite de relances, et un watchdog de 10 min.

| Bot | Rythme | Rôle |
|---|---|---|
| Vigies du cours (`armee-or-flux`) | continu | WebSocket Binance XAUUSDT (perpétuel or) et PAXGUSDT, bougies 1 min. Retard affiché en ms, reconnexion automatique, rattrapage REST des minutes perdues. |
| Vigie du cours | 30 s | Fraîcheur du prix. Écart PAXG/XAU > 1 %. Secours COMEX (GC=F) si Binance est muet. |
| Sentinelle éclair | 2 s | Mouvement brutal du cours (plus de 5× la normale en 1 ou 5 min), écart achat/vente MT5 anormal : alerte immédiate. |
| Niveaux clés | 10 s | Pivots du jour (P, R1, R2, S1, S2), plus haut / bas d'hier et de 5 jours, Fibonacci 3 mois, sommets / creux 4 h, chiffres ronds : alerte à chaque cassure. `/or_niveaux`. |
| Tendance multi-unités | 60 s | 15 min, 1 h, 4 h, 1 j (moyennes 20/50, RSI, ADX) ; alerte quand les 4 sont alignées. |
| Microstructure Binance | 30 s | Perpétuel or : taux de financement, positions ouvertes, ratio acheteurs / vendeurs ; carnet d'ordres PAXG. |
| Calendrier économique | 60 s | Annonces américaines à fort impact (emploi, inflation, PIB, Fed), alerte 30 et 5 min avant, **aucun nouvel ordre MT5 de 15 min avant à 15 min après**. `/or_calendrier`. |
| Actualités | 5 min | Titres sur l'or (Google Actualités), thèmes critiques (Fed, inflation, géopolitique, banques centrales, records). `/or_actus`. |
| COT CFTC | 6 h | Positions des gros spéculateurs sur l'or COMEX (hebdomadaire), alerte aux extrêmes de 3 ans. |
| Archiviste MT5 | 1 h | Rapatrie l'historique XAUUSD de ton courtier (1 j, 4 h, 1 h, 15 min) jusqu'au début de ce que le serveur fournit, puis le complète. Les chandeliers sont mesurés sur l'historique le plus long. |
| Archiviste | 60 s | Bougies 1 min → 15 min → 1 h → 4 h → 1 j. Mise à jour COMEX quotidienne. |
| Vigie des marchés liés | 15 min | 21 marchés : dollar (DXY), taux US 5 et 10 ans, obligations indexées sur l'inflation (TIP), argent, platine, palladium, cuivre, pétrole, S&P 500, Dow Jones, **CAC 40**, VIX, EUR/USD, dollar/yen, dollar/yuan, mines d'or (GDX), ETF GLD et SLV, Bitcoin, ratio or/argent. Corrélations sur 60 jours et « contexte » pour l'or. |
| Analyste du rythme | 5 min | Séance (Asie / Londres / New York), rang de volatilité, expansion, séries de bougies, régime. |
| Analyste des chandeliers | 60 s | **40 motifs** (Nison, Bulkowski : marteau, pendu, avalements, étoiles, pinces, trois méthodes, frappe à trois lignes…), chacun **mesuré sur l'or**. Fiable seulement si l'écart dépasse le seuil corrigé pour 40 tests (\|z\| ≥ 3,23). `/or_bougies` montre les résultats. |
| Pronostiqueurs + décision | 60 s | 7 pronostiqueurs (tendance, momentum, retour à la moyenne, chandeliers, canal, saisonnalité, volatilité) en 1 h, 4 h et 1 j. Chacun est noté en continu (Brier) contre le naïf. Consensus pondéré par la compétence. Décision seulement si l'avantage dépasse 1,5 × les coûts. |
| Stratège de fond | 1 h | « Garder l'or » comparé à « tendance 10 mois » (Faber) sur les clôtures COMEX. |
| Bilan historique | 7 j | Rejoue tout l'historique sans regarder le futur. |
| Commandes / Rapporteur | 10 s / 6 h | Commandes Telegram ou Termius. Rapport complet toutes les 6 h. |

Les comptes papier sont suivis **par profil de levier** : x1, x3, x5, x10, x20 (max. UE), x50 (max. Binance) et « pro 1 % risqué ». Ils comptent :

- les frais et le glissement ;
- le financement horaire ;
- les trous d'ouverture ;
- la liquidation, testée en premier.

## MetaTrader 5 : l'armée s'entraîne sur ton compte démo

Ubuntu ne peut pas lancer MT5 directement. Le service `armee-or-mt5` fait tourner le terminal officiel sous Wine, la méthode de MetaQuotes pour Linux, avec un écran virtuel. Un **pont** (`armee_or/pont_mt5.py`) y utilise la bibliothèque officielle MetaTrader5. Le reste de l'armée lui parle uniquement par `127.0.0.1`.

| Équipe | Numéro magique | Quand | Taille | Sortie |
|---|---|---|---|---|
| Décisions 4 h | 770004 | décision du chef (avantage > 1,5 × coûts) | profil choisi (défaut : 1 % du capital risqué) | stop 3 ATR ou 24 h |
| Décisions 1 j | 770024 | décision du chef | profil choisi | stop 3 ATR ou 5 jours |
| Entraînement 1 h | 770001 | chaque bougie d'1 h, sens du consensus | lot minimum (0,01) | stop 3 ATR ou 4 h |

- Chaque équipe a au plus une position à la fois. Une décision donne un seul ordre au plus.
- L'équipe d'entraînement trade **même quand l'avantage est inférieur aux coûts**. Elle mesure en vrai l'écart achat/vente, l'exécution et la justesse des pronostics. Elle perdra probablement un peu : c'est le prix de la mesure.
- **Tes ordres manuels ne sont jamais touchés** : le pont ne ferme que les positions qui portent un numéro magique de l'armée.
- Tu peux suivre les positions en direct dans l'app **MetaTrader 5 sur iPhone**, connectée au même compte démo.
- `or pause` ou `or mt5 fermer` arrêtent les nouveaux ordres. `or arreter` laisse les positions ouvertes avec leur stop.
- Si le pont perd la connexion au serveur MT5 pendant 10 minutes, il se relance avec le terminal. Le chef signale le problème sur Telegram.

Ce qui a été vérifié avant livraison :
- les 50 tests passent, dont 23 sur MT5 avec un faux terminal ;
- Wine 11 s'installe sur Ubuntu 24.04 ;
- la vraie bibliothèque MetaTrader5 (5.0.6180) tourne sous Wine et expose exactement les fonctions et constantes utilisées ;
- le vrai pont sous Wine répond au client Linux.

Comme dans le script officiel de MetaQuotes, l'installateur utilise **Wine Staging** : avec Wine « stable », l'installateur MT5 bloque sur « A debugger has been found running in your system ». Il ajoute aussi les composants Mono (.NET) et Gecko (HTML) sans aucune fenêtre à valider, et accepte la licence MT5 à ta place (touche Entrée simulée). Le terminal se connecte directement à ton compte grâce au fichier de démarrage officiel de MT5, effacé dès le démarrage.

`/or_mt5_ecran` t'envoie une photo de l'écran du terminal MT5 sur le serveur. Elle est mise à jour chaque minute. Si l'installation de MT5 échoue, Telegram reçoit une **photo de l'écran virtuel** et l'étape en cause, et `/or_mt5` l'affiche aussi. Pour recommencer, tape `or mt5 installer` : tes identifiants sont demandés en premier et conservés, même en cas d'échec.

Vérifié en réel sur un Ubuntu 24.04 dans le même état que ton serveur : passage à Wine Staging, mise à jour du préfixe, Mono 11.3, installation complète du **vrai terminal MT5** (build 6230) avec acceptation automatique de la licence, Python et MetaTrader5, lanceur du service.

Ce qui n'a **pas** pu être testé depuis ma machine : l'installation du terminal, la connexion à ton compte et le premier ordre réel de démo. `or mt5` et `or mt5 journal` te montrent où ça en est.

## Les données livrées (`donnees_initiales/`, voir `PROVENANCE.md`)

- **Or mensuel depuis 1833** et annuel : jeu de données public `datasets/gold-prices`.
- **COMEX GC=F quotidien** depuis 2000 : 6 102 bougies.
- **Binance PAXGUSDT** en 15 min depuis 10/2020 (207 363 bougies) et **XAUUSDT** en 15 min depuis 01/2026. Il s'agit des archives officielles `data.binance.vision`, dont chaque fichier est vérifié par SHA-256.

## Ce que l'historique a montré (honnêtement)

Mesures sans regarder le futur, frais compris, capital de départ 1 000 $ :

| Unité | Décisions | x1 | x3 | x10 | x20 | x50 | pro 1 % |
|---|---|---|---|---|---|---|---|
| 1 h | 0 | 1000 | 1000 | 1000 | 1000 | 1000 | 1000 |
| 4 h | 6 | 938 | 822 | 481 | 154 | **0 ruiné** | 982 |
| 1 j | 166 | 955 | 755 | **44 ruiné** | **0 ruiné** | **0 ruiné** | 1011 |

Sur la même période, **garder l'or a fait ×2,35**. Depuis 2000, le facteur est ×15,8.

- En 1 h, les pronostiqueurs font à peine mieux que le hasard (quelques dixièmes de %). C'est **moins que les frais** : le chef refuse donc de trader, et c'est voulu.
- Sur PAXG 1 h, la plupart des motifs de bougies sont suivis du mouvement **inverse**. Par exemple, après un avalement haussier, la hausse ne vient que 43 % du temps, contre 48 % en moyenne.
- En x50, la liquidation est à 1,5 % du prix d'entrée : ce seuil a été franchi dans 13,7 % des fenêtres de 24 h passées. En x20, la liquidation est à 4,5 %.
- La règle des 10 mois réduit la pire baisse (35 % au lieu de 62 % sur 1971-2026). En revanche, sur les vraies clôtures COMEX 2000-2026, elle rapporte **moins** que garder l'or (7,3 %/an contre 11,1 %/an).

## Limites

- **Influencer le rythme des bougies**, c'est de la manipulation de marché, interdite par le règlement européen MAR. L'armée observe et calcule, elle n'influence rien.
- **Aucune architecture ne garantit un profit.** Environ 89 % des particuliers sur CFD/Forex perdent de l'argent (AMF, 2014). Le levier maximal pour un particulier dans l'UE est de 20 sur l'or (ESMA).
- **MT5 démo** : les résultats de démo ne garantissent rien en réel, car l'exécution et les écarts diffèrent selon le courtier. Le compte « MetaQuotes-Demo » sert à s'entraîner, pas à trader de l'argent.
- **Autre courtier MT5** : `or mt5 compte`, puis le login, le mot de passe et le nom exact du serveur du courtier (ex. `XMGlobal-MT5 3`). Le pont trouve seul le nom de l'or chez ce courtier (XAUUSD, XAUUSD.a, GOLD, GOLDmicro…) et s'adapte à la taille de son contrat (100 oz, 10 oz, 1 oz…), visible dans chaque ordre. L'armée ne passe ses ordres que sur un compte **démo** : c'est une sécurité voulue.
- **Binance** a cessé de servir les résidents de l'UE au 1er juillet 2026 (MiCA), et XAUUSDT n'y est pas ouvert aux Européens. Les flux publics restent lisibles depuis le serveur, ce qui suffit à l'armée, qui ne passe aucun ordre.
- « Aucune erreur possible » n'existe pas. Ce qui existe : chaque erreur est isolée, relancée, comptée et signalée au chef, puis sur Telegram.

## Terminal de l'or (Termius et Telegram)
Inspiré des terminaux financiers professionnels : un écran par **code court**, ambre sur fond noir. Tout est lu dans la base de l'armée, donc l'affichage est instantané.

| Code | Écran |
|---|---|
| `or go` | **Écran de lancement en direct** (rafraîchi toutes les 2 s, Ctrl+C pour quitter) : cours et variation du jour, prix en €/once, achat/vente MT5, séances ouvertes, graphique 24 h, niveaux clés, tendances, marchés liés, flux Binance, agenda, actualités, état de l'armée |
| `or gp 4h` | Graphique (15m, 1h, 4h, 1d) avec haut, bas, ATR, RSI |
| `or gip` | Intraday minute par minute |
| `or eco` | Agenda des annonces américaines à fort impact, compte à rebours |
| `or top` | Actualités de l'or, thèmes critiques en rouge |
| `or wei` / `or corr` | Marchés liés (1 j, 5 j) et corrélations avec l'or sur 60 jours |
| `or rv` | Valeur relative or / argent sur 10 ans : rang, écart à la moyenne |
| `or niv` | Échelle des résistances et supports avec distances |
| `or cot` | Gros spéculateurs (CFTC) et rang sur 3 ans |
| `or des` | Fiche de l'instrument : courtier, contrat, frais mesurés, horaires en heure de Paris |
| `or risk` | Compte, positions, permis de trader |

- Sur Telegram, les mêmes écrans s'ouvrent avec `/or_go`, `/or_gp_4h`, `/or_rv`, `/or_corr`, `/or_wei`, etc. Ils sont en police à largeur fixe et calibrés pour un iPhone (36 colonnes).
- Les codes s'écrivent en minuscules ou en majuscules (`or GO`). L'écran s'adapte à la largeur de Termius : tourne le téléphone pour plus de détails.

## Alertes, brief, risque, sauvegardes, Trésor US
| Fonction | Telegram | Termius | Détail |
|---|---|---|---|
| **Alertes de prix** | `/or_alerte 4200` · `/or_alerte +1%` · `/or_alertes` · `/or_alerte_suppr 2` | `or alerte 4200` · `or alertes` | Vérifiées toutes les 2 s ; message important dès que l'or touche le prix, puis l'alerte est retirée (20 au maximum). |
| **Brief du matin** | `/or_brief` | `or brief` | Envoyé seul chaque jour de semaine à 8 h (Paris) : nuit asiatique, annonces du jour, niveaux, tendances, marchés et taux réel, titres, état de l'armée. |
| **Gestionnaire de risque** | `/or_risque` · `/or_risque_reprendre` | `or risque` · `or risque reprendre` | Perte du jour au-delà de 1 % : positions de l'armée fermées, plus d'ordre jusqu'au lendemain. Baisse de 5 % depuis le plus haut : **coupe-circuit**, tout est fermé et rien ne repart sans ton feu vert. Réglable (`OR_RISQUE_PERTE_JOUR_PCT`, `OR_RISQUE_BAISSE_MAX_PCT`). |
| **Sauvegardes** | `/or_sauvegarde` | `or sauvegarde` · `or restaurer [code]` | Chaque nuit vers 3 h : copie complète sur le serveur (3 gardées) et sauvegarde essentielle (tout sauf les bougies, re-téléchargeables) envoyée sur Telegram avec son code de restauration. Le journal des bots est limité à 7 jours. |
| **Trésor US** | `/or_wei` | `or wei` | Taux officiels quotidiens depuis 10 ans : taux réel 10 ans, nominal 10 ans, inflation attendue, pente 10 − 2 ans. Ils passent l'examen d'entrée comme les autres signaux. |

- Serveur perdu ? Sur le nouveau serveur, installe l'armée, puis tape `or restaurer CODE` avec le code reçu sous la dernière sauvegarde Telegram.
- Les réserves du fonds GLD et les chiffres publiés des annonces ne sont pas disponibles gratuitement, ils ne sont donc pas suivis.

## Réactivité
- Le chef d'orchestre passe **chaque seconde**.
- Les travaux lents (sources internet, gros calculs) tournent dans leurs propres fils : une source lente ne retarde jamais la sentinelle éclair ni l'exécutant MT5.
- Délais typiques :
  - cours MT5 lu chaque seconde, cours Binance en continu ;
  - décision prise quelques secondes après la clôture d'une bougie ;
  - ordre MT5 envoyé dans les 5 s qui suivent ;
  - alerte de mouvement brutal en 2 s.

## Apprentissage (`/or_apprentissage`)
L'armée apprend en continu, mais uniquement de ce qui a fait ses preuves, mesuré sans regarder le futur.

| Bot | Rythme | Rôle |
|---|---|---|
| Archiviste de la veille | 1 min | Archive par quart d'heure la microstructure Binance, le contexte des marchés liés, le ratio or/argent, l'écart achat/vente MT5, les actualités critiques et l'alignement des tendances. |
| Rattrapage de l'historique | 1 fois / jour | 10 ans des marchés liés en journalier, 2 ans en horaire (Yahoo), 10 ans de rapports COT (CFTC), historique du financement du perpétuel PAXG (Binance). Chaque valeur est datée à l'instant où elle était **connue**. |
| Examinateur des signaux | 1 fois / jour | Chaque série devient un pronostiqueur candidat. **Examen d'entrée** : calibration glissante, puis test de Diebold-Mariano contre le naïf, avec un seuil corrigé pour le nombre de tests (Bonferroni, recommandation Harvey-Liu-Zhu). Le signal doit aussi faire mieux sur les **deux moitiés** de l'historique. Seuls les admis entrent dans le consensus. |
| Mesure des frais réels | 1 h | Écart achat/vente, glissement (prix demandé contre prix obtenu), commissions et frais de nuit mesurés sur tes exécutions MT5. Ils remplacent progressivement l'estimation fixe dans la règle « avantage > 1,5 × coûts » (poids de la mesure = n / (n + 30)). |
| Journal d'apprentissage | 1 fois / semaine | Poids des pronostiqueurs et leur évolution, score **en direct** sur 7 jours, signaux admis ou rejetés, frais réels, chandeliers fiables, résultats MT5. |

### Vérifier (`/or_verif` ou `or verif`)
- **Mémoire** : chaque compteur de la base (bougies, bougies du courtier, observations, pronostics émis et jugés, décisions, ordres MT5) avec ce qui a été gagné en 24 h et en 7 jours. Un relevé est pris chaque heure.
- **Diagnostic des trades MT5** :
  - par équipe : nombre de trades, gagnants, résultat net ;
  - 1re moitié contre 2e moitié des trades ;
  - décomposition du résultat : mouvement du marché, écart achat/vente, commissions et nuits ;
  - taux de « bon sens » avant frais, comparé au pile ou face (z), et verdict : hasard, avantage ou désavantage.
- Un trade gagné ou perdu **ne change pas** les poids des pronostiqueurs : ils sont notés sur chaque bougie, soit beaucoup plus de données que quelques dizaines de trades. Les trades servent à mesurer les **frais réels**.

### Sans terminal
- `/or_maj` : met l'armée à jour depuis Telegram. Un petit service root installé par `or maj` lance la même mise à jour (version publiée sur GitHub uniquement) et envoie le résultat. Une première fois `or maj` dans un terminal reste nécessaire pour l'installer.
- `/or_journal` : les 25 dernières lignes du journal.

### Prise de gain (`/or_gain`)
- Règle demandée : toute position de l'armée est fermée dès que son gain (écart et nuits compris) atteint **+3 €** par défaut. Réglable avec `/or_gain_1`, `_2`, `_3`, `_5`, `_10`, ou `/or_gain_off` (terminal : `or mt5 gain 3`).
- Le stop (3 ATR) et l'horizon restent en place : une position qui ne passe jamais en gain est fermée comme avant.
- Mesure sur PAXG 2024-2026, 0,01 lot (1 once), sens au hasard, écart 0,35 $ :

| Règle | Gagnants | Gain moyen | Perte moyenne | Moyenne par trade |
|---|---|---|---|---|
| Horizon 4 h + stop | 47 % | +9,11 € | −8,91 € | −0,46 € |
| Gain pris dès +1 € | 89 % | +1,00 € | −10,74 € | −0,26 € (2,5 fois plus de trades) |
| Gain pris dès +3 € | 77 % | +2,93 € | −9,92 € | −0,09 € |

- La règle **augmente le nombre de trades gagnants**, mais ne rend pas le compte positif. Les pertes restent plus grosses que les gains, et chaque trade paie l'écart. Seul un vrai avantage dans le choix du sens peut rendre le résultat positif.

### Filtre de tendance (`/or_tendance`)
- Aucune position MT5 **contre la tendance** (EMA 20 contre EMA 100 des bougies fermées du courtier) pour l'entraînement (1 h) et les décisions 4 h. Activé par défaut ; `/or_tendance_off` pour l'arrêter.
- Pourquoi (PAXG, tout l'historique, consensus sans regard vers le futur, 2 moitiés) :

| Cas | Justes | Moyenne par trade | z |
|---|---|---|---|
| 1 h dans le sens de la tendance | 52,2 % / 52,2 % | +0,6 / +2,4 pb | +3,9 / +4,1 |
| 1 h contre la tendance | 51,7 % / 49,1 % | +0,7 / −1,5 pb | +4,1 / −2,1 |
| 4 h contre la tendance | 47,8 % / 48,5 % | −1,9 / −4,8 pb | −2,4 / −1,8 |
| 4 h contre une tendance forte (> 2 ATR) | 47,4 % / 46,0 % | +1,7 / −9,9 pb | −1,6 / −3,2 |

- En direct (oct. 2026), 31 trades sur 36 étaient des ventes pendant la hausse de l'or.
- L'avantage restant (environ +2 pb en 1 h dans le sens de la tendance) est tout juste au-dessus de l'écart réel mesuré sur MT5 (environ 1 pb) : c'est mince.
- Le 1 j n'est pas filtré (pas assez d'historique pour le mesurer).

### « Que du prouvé » : permis de trader (toutes les équipes MT5)
- Ton choix : aucune équipe, **entraînement compris**, ne passe d'ordre MT5 sans **permis**.
- Toutes les 6 h, la règle de chaque équipe (entraînement 1 h, décisions 4 h et 1 j) est rejouée sur tout l'historique. On ne regarde jamais le futur, on applique les frais réels du courtier et le filtre de tendance, et on utilise le même consensus qu'en direct, signaux admis compris.
- Le permis n'est accordé que si le résultat net moyen par décision est **positif sur les deux moitiés** de l'historique, avec au moins 30 décisions dans chacune.
- Chaque changement est annoncé sur Telegram (🪪). L'état est visible dans `/or_mt5`.
- **Mode agressif** : `/or_agressif_on` (ou `or mt5 agressif on`) pour les trois équipes MT5.
  - Plus besoin de permis.
  - Décisions 4 h et 1 j : un ordre à chaque penchant du consensus (sans la barre « 1,5 × frais »), avec 3 % du capital risqué. Si le lot minimum risque déjà plus que ça, il est pris quand même.
  - Entraînement : 2 × le lot minimum chaque heure, et prise de gain proportionnelle (+3 € par 0,01 lot).
  - Freins élargis : perte du jour 3 %, coupe-circuit 10 %.
  - Toujours en place : filtre de tendance, stop, horizon, pause autour des annonces, règle du week-end, compte démo.
  - `/or_agressif_off` revient aux réglages normaux.
- **Interrupteur** : `/or_permis_off` (ou `or mt5 permis off`) remet les bots en action même sans permis ; `/or_permis_on` rétablit « que du prouvé ». Bots actifs ou non, les garde-fous restent en place : filtre de tendance, stop, prise de gain, perte du jour, coupe-circuit.
- Mesure d'octobre 2026 (PAXG, net par décision, 1re / 2e moitié) :

| Frais aller-retour | Entraînement 1 h | Décisions 4 h | Décisions 1 j |
|---|---|---|---|
| 0,0565 % (aujourd'hui) | −5,6 / −3,4 pb | −21,1 / −10,6 pb | −68,9 / +33,6 pb |
| 0,015 % (bientôt) | −1,4 / +0,7 pb | −3,9 / −3,5 pb | −26,8 / +23,2 pb |
| 0,01 % | −0,9 / +1,2 pb | −3,2 / −2,6 pb | −26,9 / +25,0 pb |

- Aucun permis aujourd'hui : le compte MT5 ne bouge plus. L'armée continue d'observer, de noter ses pronostics, d'examiner de nouveaux signaux et de tenir ses comptes papier. Elle reprendra seule les ordres dès qu'une règle aura fait ses preuves.
- Testé aussi (XAUUSDT 2026, données fiables) : toutes les variantes « gain pris tout de suite » perdent, même avec 82 à 99 % de trades gagnants. « Sans stop » : 99,4 % de gagnants, mais une position bloquée 215 jours à −997 €. Sur PAXG avant 2026, les écarts larges (prix arrondis au dollar) faisaient croire à tort que ces règles gagnaient.
- `/or_verif` détaille aussi les **sorties** (prise de gain, stop, horizon, à la main) et le **taux de réussite nécessaire** pour être à zéro, compte tenu du gain moyen et de la perte moyenne.

### Correctifs du 15 octobre 2026 (après la nuit du 14 au 15)
- **Ce qui s'est passé** : 11 ventes sur 12 pendant que l'or remontait de 4 076 à 4 155 $. Petits gains (+6 à +9 €), grosses pertes (−44, −84, −29 €).
- **Défaut 1, l'équipe 4 h** : −187 € sur ses 4 trades en direct, soit les trois quarts des pertes totales, et perdante sur tout l'historique.
  - Correction : elle reste **sur la touche tant qu'elle n'a pas son permis**, même bots actifs ou en mode agressif.
- **Défaut 2, le retard du filtre de tendance** : la tendance EMA 20 / EMA 100 en 1 h réagit en retard aux retournements.
  - Correction : l'entraînement exige aussi **l'élan** (prix du bon côté de sa moyenne des 20 dernières heures).
  - Mesure de la règle d'entraînement : XAUUSDT 2026, −580 / −349 € devient −360 / −213 € ; PAXG 2025-2026, +212 / −1 605 € devient +367 / −1 389 €.
- **Testé, sans effet ou pire, donc non retenu** :
  - pause après un stop : effet incertain ;
  - stop plus serré (1,5 ou 2 ATR) : pire ;
  - horizon de 2 h : pire ;
  - retrait de la prise de gain pour l'équipe 1 j : plus de gain total, mais le pire trade passe de −139 à −367 €.
- Même corrigée, la règle d'entraînement reste **perdante en moyenne** sur l'historique : environ −0,3 € par trade d'une once.

### Correctif du 19 octobre 2026 : le frein du jour et l'équipe 1 j
- **Constat** : une position 1 j (achat 0,01 à 4 187,12, stop à 3 952,90, prévue pour 5 jours) est à −37,57 €.
  - C'est −42 $, soit une demi-journée de variation normale de l'or (75 $ par jour en ce moment).
  - Sur PAXG 2025-2026, cette règle gagne sur les deux moitiés (98 % de trades gagnants, pire −139 €).
- **Défaut trouvé** : en mode agressif, son stop (environ −209 €) est plus loin que le frein du jour (−3 %, environ 82 €). Le frein la fermait donc en plein creux.
  - Mesure : avec le frein, +399 € deviennent +116 € (4 coupures en 2 ans, toujours juste avant le rebond).
- **Correction** : le frein du jour ferme les positions **courtes** (entraînement, 4 h) et bloque les nouveaux ordres jusqu'au lendemain. La position 1 j garde son propre stop.
  - Le coupe-circuit (5 %, ou 10 % en mode agressif) ferme toujours **tout**.
- **Testé et non retenu** :
  - stop 1 j limité à 3 % du capital : +474 € deviennent +63 € ;
  - filtre de tendance ou d'élan sur l'équipe 1 j : mieux sur une moitié, moins bien sur l'autre.

### Audit complet du 19 octobre 2026 (« tous les défauts possibles »)
Chaque piste a été mesurée sur la règle réelle (prise de gain, stop, horizon, écart du courtier de 0,44 $), sur XAUUSDT 2026 et PAXG 2025-2026, en coupant l'historique en deux moitiés :

| Piste | Résultat | Décision |
|---|---|---|
| Équipe 4 h | −187 € en direct, perdante sur l'historique | sur la touche (15/10) |
| Retard du filtre de tendance | élan : pertes −35 à −40 % | corrigé (15/10) |
| **Nuit asiatique (0 h - 7 h UTC)** | entraînement : −0,86 et −0,61 € par trade, perdant sur les 4 moitiés | **plus d'entraînement de 21 h à 7 h UTC** : de −0,28 à +0,05 €/trade (XAUUSDT), de −0,21 à +0,01 € (PAXG) |
| Frein du jour qui coupe la 1 j | +399 € deviennent +116 € | corrigé : le frein ne ferme que les positions courtes |
| Positions à cheval sur la pause du soir | les éviter coûte −0,2 €/trade | non retenu |
| Pause après un stop | sans effet net | non retenu |
| Stop plus serré, horizon 2 h | pire | non retenu |
| Filtres sur l'équipe 1 j, stop 1 j plafonné | pire, ou incertain | non retenu |

- **Vérification en direct** : depuis l'arrivée de la prise de gain, l'entraînement gagne 27 trades sur 32 (84 %), comme le prévoyait la simulation (82 %). Le modèle décrit bien la réalité.
- **`/or_rentable`** (ou `or mt5 rentable`) ne garde que l'équipe 1 j, la seule gagnante sur l'historique récent. L'entraînement est arrêté, la 4 h reste sur la touche, les freins sont à 3 % / 10 %.
- Limite honnête : l'équipe 1 j a gagné parce que l'or montait (2024-2026) ; elle perdait en marché sans direction (2020-2023). Aucun réglage ne garantit un résultat positif.

### Diagnostic du 22 octobre 2026 : le vrai problème, et retour à « que du prouvé »
- **Constat** : en 2026, le consensus de l'équipe 1 j vaut **exactement le naïf** (0,605 : « l'or a monté 60 % du temps récemment »), donc elle achète **100 % du temps**. Les poids des bots sont à zéro : ils n'apportent aucune information.
  - Ses gains de 2025 (or +65 %) n'étaient qu'un pari sur la hausse.
  - La prise de gain à +3 € plafonnait les gains, alors que les pertes couraient jusqu'à 5 jours (achat à 4 187, fermé à −58,94 €).
- **Décision du propriétaire** : arrêt des ordres (`/or_permis_on`). La position ouverte se termine avec son stop ou son horizon. Terminal, alertes, brief et apprentissage continuent.
- **Permis renforcé** : une équipe doit gagner sur les deux moitiés **et faire mieux que la même règle appliquée au seul naïf**.
  - Mesure (frais 0,015 %, net par décision, 1re / 2e moitié, comparé au naïf) :
    - entraînement −1,4 / +0,7 pb (naïf −2,0 / +0,6) ;
    - 4 h −3,9 / −3,5 pb (naïf +1,0 / +2,3) ;
    - 1 j −26,8 / +23,2 pb (naïf −26,8 / +44,2).
  - Les bots ne battent le naïf nulle part de façon nette : aucune équipe n'a son permis.

### Fermetures et week-end
- Une position courte (entraînement 4 h, décisions 4 h sur 24 h) n'est ouverte que si son horizon tombe avant la fermeture du vendredi (20 h UTC) : rien ne reste ouvert à son insu pendant le week-end.
- Si l'horizon arrive marché fermé, la fermeture attend la réouverture, sans noter un échec toutes les 5 s (les anciennes lignes répétées sont nettoyées une fois).

Premier examen réel (sept. 2026) : 80 807 observations, 47 tests, seuil z ≥ 3,07, **aucun signal admis**. Le meilleur est la variation du pétrole sur 5 jours en 4 h (z = +0,74). Les signaux publics gratuits ne prédisent pas l'or mieux que le hasard une fois correctement mesurés. L'examen les tient donc à l'écart, et les réexamine chaque jour à mesure que l'historique s'allonge.
