"""ARMÉE DE L'OR — équipe de bots dédiée uniquement à l'or, indépendante des autres bots du serveur.

Chef d'orchestre (chef.py) : pilote, note et fait rendre des comptes à tous les bots.
Vigies : cours en direct (Binance XAUUSDT / PAXGUSDT par WebSocket, secours REST puis COMEX), marchés liés.
Analystes : chandeliers, rythme des bougies, saisonnalité. Pronostiqueurs : probabilités de hausse notées en continu.
Stratèges : levier (marge, liquidation, financement, Kelly), portefeuilles PAPIER par profil de levier.
Archivistes : historique de l'or depuis 1833, COMEX depuis 2000, bougies Binance depuis 2020.

Aucun ordre réel : Binance ne sert plus les résidents de l'UE (MiCA, 1er juillet 2026) et aucune stratégie n'est
prouvée rentable. Tout est simulé sur les vrais cours, pour mesurer avant de risquer.
"""
__version__ = "1.0"
