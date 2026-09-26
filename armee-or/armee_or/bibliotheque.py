"""BIBLIOTHÈQUE — les connaissances des professionnels et chercheurs sur lesquelles s'appuie l'armée.

Chaque fiche dit d'où vient l'idée (travaux publiés, manuels de référence, régulateurs), ce que l'armée en fait,
et ce que la mesure sur l'or a montré. Rien n'est pris pour argent comptant : une idée n'influence les décisions
que si elle a fait ses preuves sur les données de l'or, frais compris.
"""
from __future__ import annotations

FICHES = [
    {"theme": "Tendance", "reference": "Moskowitz, Ooi, Pedersen — « Time Series Momentum », Journal of Financial "
     "Economics, 2012", "idee": "Sur 58 marchés (dont l'or), le rendement des 12 derniers mois prédit en partie le "
     "mois suivant.", "usage": "Pronostiqueur « momentum » ; règle de fond mensuelle.",
     "mesure": "Or 1971-2026 (moyennes mensuelles) : baisse maximale divisée par deux ; or COMEX 2000-2026 (clôtures "
     "de fin de mois) : moins rentable que garder l'or."},
    {"theme": "Tendance", "reference": "Hurst, Ooi, Pedersen — « A Century of Evidence on Trend-Following "
     "Investing », Journal of Portfolio Management, 2017", "idee": "Le suivi de tendance a fonctionné sur plus d'un "
     "siècle, surtout pendant les grandes crises.", "usage": "Justifie la règle de fond et le pronostiqueur « tendance ».",
     "mesure": "Utile pour limiter les pertes des grands marchés baissiers (or 1980-2001), coûteux en marché haussier."},
    {"theme": "Tendance", "reference": "M. Faber — « A Quantitative Approach to Tactical Asset Allocation », "
     "Journal of Wealth Management, 2007", "idee": "Rester investi seulement au-dessus de la moyenne mobile de 10 mois.",
     "usage": "Compte de fond « tendance 10 mois » comparé à « garder l'or ».", "mesure": "Voir ci-dessus."},
    {"theme": "Or et macroéconomie", "reference": "Erb & Harvey — « The Golden Dilemma », Financial Analysts "
     "Journal, 2013", "idee": "Le prix réel de l'or varie beaucoup ; il est lié aux taux d'intérêt réels et n'est "
     "une protection contre l'inflation que sur de très longues durées.", "usage": "Vigie des marchés liés (taux US, dollar).",
     "mesure": "Corrélation des 60 derniers jours recalculée à chaque passage."},
    {"theme": "Or valeur refuge", "reference": "Baur & Lucey — « Is Gold a Hedge or a Safe Haven? », Financial "
     "Review, 2010", "idee": "L'or protège pendant les chutes brutales des actions (quelques jours), pas toujours au-delà.",
     "usage": "S&P 500 et VIX dans la vigie des marchés liés.", "mesure": "Suivi en direct."},
    {"theme": "Saisonnalité", "reference": "D. G. Baur — « The Autumn Effect of Gold », Research in International "
     "Business and Finance, 2013", "idee": "L'or a historiquement mieux performé en septembre et novembre.",
     "usage": "Pronostiqueur « saisonnalité » (par heure en intrajournalier).", "mesure": "Compétence proche de zéro en 1 h."},
    {"theme": "Microstructure", "reference": "Caminschi & Heaney — « Fixing a Leaky Fixing », Journal of Futures "
     "Markets, 2014", "idee": "Des mouvements anormaux précédaient le fixing de Londres de l'après-midi.",
     "usage": "Séances et heure UTC dans l'analyste du rythme.", "mesure": "Profil horaire mesuré sur l'historique."},
    {"theme": "Chandeliers", "reference": "S. Nison — « Japanese Candlestick Charting Techniques », 1991",
     "idee": "Les motifs de bougies résument l'équilibre acheteurs / vendeurs.", "usage": "Analyste des chandeliers (16 motifs).",
     "mesure": "Sur PAXG 1 h : la plupart des motifs sont suivis du mouvement INVERSE plus souvent qu'à l'ordinaire."},
    {"theme": "Indicateurs", "reference": "J. W. Wilder — « New Concepts in Technical Trading Systems », 1978",
     "idee": "RSI, ATR (volatilité), ADX (force de tendance).", "usage": "Calculs de volatilité, stops et scores.",
     "mesure": "—"},
    {"theme": "Indicateurs", "reference": "J. Bollinger — « Bollinger on Bollinger Bands », 2001",
     "idee": "Écart à la moyenne en écarts-types.", "usage": "Pronostiqueur « retour à la moyenne ».",
     "mesure": "Seul pronostiqueur légèrement meilleur que le naïf sur les deux moitiés de l'historique 1 h."},
    {"theme": "Cassures", "reference": "C. Faith — « Way of the Turtle », 2007 (règles des « Turtles »)",
     "idee": "Acheter la cassure du plus haut de N jours, taille selon la volatilité (ATR).",
     "usage": "Pronostiqueurs « canal » et « volatilité ».", "mesure": "Compétence instable selon la période."},
    {"theme": "Gestion du risque", "reference": "J. L. Kelly — « A New Interpretation of Information Rate », "
     "Bell System Technical Journal, 1956", "idee": "Mise optimale selon la probabilité de gain ; au-delà, la ruine "
     "devient probable.", "usage": "Fraction de Kelly (divisée par 4) dans chaque fiche de levier.", "mesure": "—"},
    {"theme": "Sur-apprentissage", "reference": "Bailey, Borwein, López de Prado, Zhu — « The Probability of Backtest "
     "Overfitting », 2014 ; Bailey & López de Prado — « The Deflated Sharpe Ratio », 2014",
     "idee": "Plus on essaie de stratégies, plus un beau backtest peut être dû au hasard.",
     "usage": "Calibration glissante sans regarder le futur ; bilans séparés par moitié d'historique.", "mesure": "—"},
    {"theme": "Évaluation", "reference": "G. W. Brier — « Verification of Forecasts Expressed in Terms of "
     "Probability », Monthly Weather Review, 1950", "idee": "Noter un pronostic probabiliste.",
     "usage": "Chaque pronostiqueur est noté en continu contre le naïf ; poids nul s'il ne fait pas mieux.", "mesure": "—"},
    {"theme": "Efficience des marchés", "reference": "E. Fama, 1970 ; A. Lo — « The Adaptive Markets "
     "Hypothesis », 2004", "idee": "Les avantages exploitables sont rares, petits et disparaissent quand ils sont connus.",
     "usage": "Le chef d'orchestre se méfie de tout avantage qui ne dépasse pas les coûts.",
     "mesure": "Avantages mesurés en 1 h : quelques dixièmes de % de mieux que le naïf, inférieurs aux frais."},
    {"theme": "Levier (réglementation)", "reference": "ESMA — mesures d'intervention sur les CFD, 2018 (reprises par "
     "l'AMF)", "idee": "Levier maximal 20 sur l'or pour un particulier, coupure à 50 % de marge, pas de solde négatif.",
     "usage": "Profil « x20 (max. UE) » ; plafond du profil « pro ».", "mesure": "Historique : ruine fréquente à partir de x10."},
    {"theme": "Levier (réalité)", "reference": "AMF — étude sur les clients particuliers du Forex / CFD, 2014",
     "idee": "Environ 89 % des particuliers étudiés ont perdu de l'argent.", "usage": "Rappel dans chaque bilan de levier.",
     "mesure": "Confirmé par les comptes papier de l'armée sur l'historique."},
]


def texte(theme=None):
    lignes = []
    for f in FICHES:
        if theme and f["theme"] != theme:
            continue
        lignes.append(f"• [{f['theme']}] {f['reference']}\n  Idée : {f['idee']}\n  Usage : {f['usage']}"
                      + (f"\n  Mesure : {f['mesure']}" if f["mesure"] != "—" else ""))
    return "\n".join(lignes)
