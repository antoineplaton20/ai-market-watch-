# Études reproductibles (R5.1 à R8, 25 et 26 octobre 2026)

Chaque chiffre cité dans `LISEZMOI.md` et `PROMPT_MAITRE.md` sur ces sujets sort de ces scripts. Rien n'est ajusté
après coup ; chaque variante essayée est listée.

Dossier MACRO (R7) : séries FRED (`DFII10`, `DGS10`, `T10YIE`, `DTWEXBGS`, `WALCL`, taux 3 mois `IR3TIB01*M156N`)
au format CSV de `fred.stlouisfed.org/graph/fredgraph.csv?id=…`, et COT de la CFTC (`publicreporting.cftc.gov`,
jeu 72hh-3qpy) en JSON (`cot_or.json`, `cot_SIF.json`…). R8 y ajoute `fomc.json`, `resultats_geants.json` et
`fng.json` (`telecharger_r8.py`), et `BAA10Y.csv`, `T10Y2Y.csv` (FRED).

Dossier DUKASCOPY (R8) : bougies d'une heure de `datafeed.dukascopy.com` (S&P 500, or, argent, pétrole, DAX),
fichiers mensuels `.bi5` téléchargés lentement par `corpus_r8/dukascopy.py` (8 s entre deux fichiers).

Dossier `corpus_r8/` (R8) : les collecteurs du corpus (podcasts, Odysee, forums, discours, Trading Rush,
TradingView), le choix et la transcription Whisper des épisodes, la carte de couverture, et les index publiables
(titres, auteurs, liens ; jamais les textes). Chaque collecteur se lance seul :
`python etudes/corpus_r8/podcasts.py etudes/corpus_r8/termes_podcasts.txt CORPUS/podcasts.json`,
`odysee.py requetes_odysee.txt CORPUS/odysee.json`, `forums.py CORPUS/forums.json`,
`discours.py noms_discours.txt CORPUS/discours.json`, `tradingrush.py CORPUS/tradingrush.json`,
`tradingview.py mots_tradingview.txt CORPUS/tradingview.json`,
`choisir_episodes.py CORPUS/podcasts.json CORPUS/selection.json`,
`transcrire.py CORPUS/selection.json CORPUS/transcriptions 30` (faster-whisper, à installer à part, et ffmpeg ; modèle « base », sur le processeur),
`analyse_corpus.py CORPUS`, `extraits.py CORPUS`, `index_corpus.py CORPUS etudes/corpus_r8`,
`dukascopy.py DOSSIER_DUKASCOPY USA500IDXUSD,XAUUSD,XAGUSD,LIGHTCMDUSD,DEUIDXEUR 2012 2026`.

| Script | Données | Commande (depuis `armee-or/`) |
|---|---|---|
| `regle_r4.py` : la règle de la démo R4 (sa propre fonction `signal`) rejouée trade par trade | PAXGUSDT 15 min 2021-2026, livré dans `donnees_initiales/binance` | `.venv/bin/python etudes/regle_r4.py donnees_initiales/binance .` |
| `variantes.py` : peut-on rendre chaque trade gagnant ? 8 variantes de la règle des 200 jours | 34 marchés Yahoo 2000-2026 (non livrés : usage personnel) | `.venv/bin/python etudes/variantes.py DOSSIER_YAHOO . etudes` |
| `recherche_r6.py` : les 10 règles publiées de la recherche R6, mêmes conditions | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/recherche_r6.py DOSSIER_YAHOO . etudes` |
| `robustesse_r6.py` : le momentum 12 mois face aux frais, aux familles, à 200 sous-paniers, par périodes de 5 ans | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/robustesse_r6.py DOSSIER_YAHOO . etudes` |
| `or_seances.py` : l'or selon les séances (Asie, New York) | PAXGUSDT 15 min 2021-2026, livré | `.venv/bin/python etudes/or_seances.py donnees_initiales/binance` |
| `grands_r61.py` : méthodes publiques de CFM, Bridgewater, Millennium/Citadel, et 10 marchés de plus | 34 marchés + 10 marchés Yahoo (Asie, Europe, obligations US) | `.venv/bin/python etudes/grands_r61.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA . etudes` |
| `robustesse_r61.py` : le risque égal par famille sans cryptos, sans forex, frais, 200 sous-paniers, périodes | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/robustesse_r61.py DOSSIER_YAHOO . etudes` |
| `donnees_r62.py` : le contrôle de qualité de chaque historique (mêmes contrôles que l'armée), l'or par trois sources | 34 marchés + 10 marchés Yahoo, PAXGUSDT et XAUUSDT livrés | `.venv/bin/python etudes/donnees_r62.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA .` |
| `methodes_r62.py` : les méthodes « un petit gain par trade » (verrou de gain, stop suiveur, ensemble), sur tous les marchés puis sur les seuls historiques propres | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/methodes_r62.py DOSSIER_YAHOO . etudes` |
| `robustesse_r62.py` : le stop suiveur et le verrou face aux frais, au financement, aux réglages voisins, à 200 sous-paniers, par périodes | 34 marchés Yahoo 2000-2026 | `.venv/bin/python etudes/robustesse_r62.py DOSSIER_YAHOO . etudes` |
| `telecharger_yahoo.py` : les historiques Yahoo des études, fenêtre fixe (01/01/2000 → 24/10/2026) | Yahoo (non livrés) | `.venv/bin/python etudes/telecharger_yahoo.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA` |
| `telecharger_r7.py` : archives mensuelles Binance, sommes SHA-256 vérifiées | PAXGUSDT, EURUSDT, BTCUSDT, ETHUSDT (5 min, 1 h ; or 1 min) | `.venv/bin/python etudes/telecharger_r7.py DOSSIER_BINANCE PAXGUSDT 5m 2020-09 2026-09` (idem 1h, 1m 2024-10, EURUSDT 2020-01, BTCUSDT et ETHUSDT 2019-01) |
| `inventaire_r7.py` : inventaire YouTube (133 recherches de `requetes_r7.txt`, triées par vues) et familles | YouTube (page de recherche, sans compte) | `.venv/bin/python etudes/inventaire_r7.py etudes/requetes_r7.txt SORTIE.json SORTIE.csv` |
| `recherche_r7.py` : les 55 règles des vidéos et 8 fiches, 169 essais règle × unité de temps (moteur `moteur_r7.py`, règles `catalogue_r7.py`) | Binance + Yahoo | `.venv/bin/python etudes/recherche_r7.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_MACRO . essais_r7.json 4` |
| `autres_r7.py` : portage, paires, COT, taux réels, régimes, saisonnalité, momentum relatif, écarts d'ouverture, apprentissage, méta-étiquetage, martingale et grille (`speciales_r7.py`) | Yahoo, Binance, FRED, CFTC | `.venv/bin/python etudes/autres_r7.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_MACRO . autres_r7.json` |
| `robustesse_r7.py` : le momentum relatif face aux contrôles | Yahoo | `.venv/bin/python etudes/robustesse_r7.py DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA .` |
| `fiches_r7.py` : les fiches H01 à H21 telles qu'écrites, et la batterie de contrôles des Turtles | Yahoo, GLD, SLV, SPY, Binance, FRED, CFTC | `.venv/bin/python etudes/fiches_r7.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA DOSSIER_MACRO .` |
| `analyse_r7.py` : jugement des essais, entrées au hasard, frais doublés, ordre probable des bougies, Sharpe dégonflé | sorties des deux scripts ci-dessus | `.venv/bin/python etudes/analyse_r7.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_MACRO . essais_r7.json autres_r7.json analyse_r7.json` |
| `telecharger_r8.py` : jours de décision de la Fed, résultats des 7 géants (SEC), indice peur et avidité | federalreserve.gov, data.sec.gov, api.alternative.me | `.venv/bin/python etudes/telecharger_r8.py DOSSIER_MACRO` |
| `recherche_r8.py` : les méthodes du corpus R8 jamais testées (règles N01 à N45 de `catalogue_r8.py`, EWMAC, pyramidage, sélections entre marchés, événements, Quantpedia, grands investisseurs) | Binance + Yahoo + FRED + dates R8 | `.venv/bin/python etudes/recherche_r8.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA DOSSIER_MACRO . essais_r8.json` |
| `validation_r8.py` : contre-épreuves en bougies d'une heure (Turtles heure par heure, Williams journalier contre dans la journée, bande de bruit sur la séance de New York) | Binance + Dukascopy + Yahoo | `.venv/bin/python etudes/validation_r8.py DOSSIER_BINANCE DOSSIER_YAHOO DOSSIER_YAHOO_EXTRA DOSSIER_MACRO . DOSSIER_DUKASCOPY` |

Résultats du 25/10/2026 :

- règle R4 : 2 783 trades, 44 % gagnants, −0,04 R par trade (perdante 2021-2024, +0,07 R en 2025, +0,06 R en 2026) ;
- R6 : momentum 12 mois +0,38 / +0,66 (stop 5 ATR compris) contre +0,08 / +0,46 pour le naïf, seul candidat retenu sur 13 essais (détail : `PROMPT_MAITRE.md` §5, fiches H27 à H39) ;
- R6.1 : risque égal par famille (Bridgewater) → momentum +0,51 / +0,92, règle 200 jours +0,47 / +0,83, naïf +0,37 / +0,77 ; CFM acheteur seul et 44 marchés rejetés ; limite de perte à la Millennium mesurée (fiches H40 à H43) ;
- R6.2 : 9 historiques Yahoo sur 44 écartés par le contrôleur ; sans eux, momentum +0,31 / +0,92 contre +0,23 / +0,74 pour le naïf ; verrou de gain neutre (+0,51 / +0,91, 42 % de trades gagnants au lieu de 34 %), adopté ; stop suiveur 3 ATR rejeté (pas robuste) ; ensemble inutile (fiches H44 à H47) ;
- R7 : 3 831 vidéos YouTube et 22 fiches, 251 essais comptés ; aucune règle des vidéos n'a le permis ; Turtles système 1 acheteur avec filtre, dans la journée : +0,46 / +1,23 (candidate, H01) ; à la clôture +0,19 / +1,01 ; momentum relatif +0,58 / +0,92 (pas mieux que l'équipe, H55) ; momentum de l'équipe : t = 3,71, Sharpe dégonflé 81 % sur 251 essais (H56) ;
- règle des 200 jours (l'équipe multi-marchés) : 22 % de trades gagnants, Sharpe +0,35 / +0,52 sur les deux moitiés ;
- forcer 70 à 81 % de trades gagnants (prise de gain à 0,5 ou 1 ATR) : Sharpe nul ou négatif ;
- 90 à 97 % de trades gagnants en ne fermant jamais à perte : pertes cachées dans les positions restées ouvertes
  (jusqu'à −310 % de la mise d'un marché), positions bloquées jusqu'à 18 ans, pire baisse −28 à −31 %.
