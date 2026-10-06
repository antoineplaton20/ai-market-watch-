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

### Fermetures et week-end
- Une position courte (entraînement 4 h, décisions 4 h sur 24 h) n'est ouverte que si son horizon tombe avant la fermeture du vendredi (20 h UTC) : rien ne reste ouvert à son insu pendant le week-end.
- Si l'horizon arrive marché fermé, la fermeture attend la réouverture, sans noter un échec toutes les 5 s (les anciennes lignes répétées sont nettoyées une fois).

Premier examen réel (sept. 2026) : 80 807 observations, 47 tests, seuil z ≥ 3,07, **aucun signal admis**. Le meilleur est la variation du pétrole sur 5 jours en 4 h (z = +0,74). Les signaux publics gratuits ne prédisent pas l'or mieux que le hasard une fois correctement mesurés. L'examen les tient donc à l'écart, et les réexamine chaque jour à mesure que l'historique s'allonge.
