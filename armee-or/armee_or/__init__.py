"""ARMÉE DE L'OR — équipe de bots dédiée uniquement à l'or, indépendante des autres bots du serveur.

Chef d'orchestre (chef.py) : pilote, note et fait rendre des comptes à tous les bots.
Vigies : cours en direct (Binance XAUUSDT / PAXGUSDT par WebSocket, secours REST puis COMEX), marchés liés.
Analystes : chandeliers, rythme des bougies, saisonnalité. Pronostiqueurs : probabilités de hausse notées en continu.
Stratèges : levier (marge, liquidation, financement, Kelly), portefeuilles PAPIER par profil de levier.
Archivistes : historique de l'or depuis 1833, COMEX depuis 2000, bougies Binance depuis 2020.

R3 : observation et gestion des positions existantes sur compte démo seulement.
Aucune nouvelle ouverture MT5 : qualification selon le prompt maître encore incomplète.
"""
__version__ = "2.5-R6"
