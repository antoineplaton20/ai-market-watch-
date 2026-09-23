# -*- coding: utf-8 -*-
"""
UNIVERS DES BOTS — symboles Yahoo Finance des titres disponibles sur Trade Republic.
Tu peux ajouter / retirer des lignes librement : "SYMBOLE": "Nom utilisé pour chercher les actus".
Suffixes : aucun = USA · .DE Allemagne · .PA Paris · .AS Amsterdam · .MI Milan · .MC Madrid
           .SW Suisse · .L Londres · .CO Copenhague · .ST Stockholm · .HE Helsinki · .BR Bruxelles
           -EUR = crypto
"""

# ─── Modules spécialisés (surveillés en permanence pendant leur séance) ──────────────────────

IA_INFRA = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "ARM", "SMCI", "DELL", "CEG", "VST",
            "EQIX", "DLR", "MOD", "FCX", "MP", "VRT", "ANET", "ORCL", "PLTR",
            "ASML.AS", "SAP.DE", "SU.PA", "IFX.DE"]

POWER_COOLING = ["CEG", "VST", "NRG", "TLN", "EQIX", "DLR", "MOD", "SMCI", "DELL", "VRT", "ETN",
                 "GEV", "OKLO", "CCJ", "ENR.DE", "SU.PA", "LR.PA", "NEX.PA", "PRY.MI"]

SEMIS = ["NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "ARM", "MRVL", "QCOM", "AMAT", "LRCX", "KLAC",
         "ASML.AS", "ASM.AS", "BESI.AS", "IFX.DE", "STMPA.PA", "SOI.PA"]

MATIERES = ["FCX", "MP", "SCCO", "TECK", "RIO", "BHP", "CCJ", "ALB", "NEM", "GLEN.L", "AAL.L",
            "BOL.ST", "COPX"]

CRYPTO = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "ADA-EUR", "DOGE-EUR", "DOT-EUR",
          "LINK-EUR", "AVAX-EUR", "LTC-EUR", "TRX-EUR", "XLM-EUR"]

# ─── Matières premières via ETC (Exchange Traded Commodities) achetables sur Trade Republic ──────
# Le signal est calculé sur le contrat de référence (Yahoo "=F") ; sur TR tu achètes l'ETC qui le suit.
# (symbole Yahoo) : (nom simple, ce qu'il faut taper dans la recherche Trade Republic)
COMMOS = {
    "GC=F": ("Or", "Xetra-Gold (ou Invesco Physical Gold)"),
    "SI=F": ("Argent", "WisdomTree Physical Silver"),
    "PL=F": ("Platine", "WisdomTree Physical Platinum"),
    "HG=F": ("Cuivre", "WisdomTree Copper"),
    "CL=F": ("Pétrole WTI", "WisdomTree WTI Crude Oil"),
    "BZ=F": ("Pétrole Brent", "WisdomTree Brent Crude Oil"),
    "NG=F": ("Gaz naturel", "WisdomTree Natural Gas"),
    "ZW=F": ("Blé", "WisdomTree Wheat"),
    "ZC=F": ("Maïs", "WisdomTree Corn"),
    "ZS=F": ("Soja", "WisdomTree Soybeans"),
    "KC=F": ("Café", "WisdomTree Coffee"),
    "CC=F": ("Cacao", "WisdomTree Cocoa"),
    "SB=F": ("Sucre", "WisdomTree Sugar"),
}

# Taux de change (TR affiche tout en euros)
FX = ["EURUSD=X", "GBPEUR=X", "CHFEUR=X", "DKKEUR=X", "SEKEUR=X", "NOKEUR=X"]

# Symboles utilisés comme indicateurs mais NON achetables sur Trade Republic (ETF US hors UCITS)
NON_TR = {"COPX"}

# ─── Univers large du scanner "Tous marchés" (re-classé toutes les heures) ──────────────────

NOMS = {
    # USA — tech / IA / semis
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet Google",
    "META": "Meta Platforms", "TSLA": "Tesla", "AVGO": "Broadcom", "AMD": "AMD", "INTC": "Intel",
    "QCOM": "Qualcomm", "TXN": "Texas Instruments", "MU": "Micron", "AMAT": "Applied Materials",
    "LRCX": "Lam Research", "KLAC": "KLA Corp", "ADI": "Analog Devices", "MRVL": "Marvell",
    "ARM": "Arm Holdings", "SMCI": "Super Micro Computer", "DELL": "Dell", "HPE": "Hewlett Packard Enterprise",
    "ORCL": "Oracle", "CRM": "Salesforce", "ADBE": "Adobe", "NOW": "ServiceNow", "PLTR": "Palantir",
    "SNOW": "Snowflake", "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks", "NET": "Cloudflare",
    "DDOG": "Datadog", "MDB": "MongoDB", "SHOP": "Shopify", "UBER": "Uber", "NFLX": "Netflix",
    "ANET": "Arista Networks", "CSCO": "Cisco", "IBM": "IBM", "SNPS": "Synopsys", "CDNS": "Cadence",
    "ON": "ON Semiconductor", "NXPI": "NXP", "WDC": "Western Digital", "STX": "Seagate",
    "CIEN": "Ciena", "COHR": "Coherent", "LITE": "Lumentum", "CRWV": "CoreWeave", "NBIS": "Nebius",
    "IONQ": "IonQ", "RGTI": "Rigetti", "QBTS": "D-Wave", "SOUN": "SoundHound", "TSM": "TSMC",
    "ASML": "ASML", "SONY": "Sony", "BABA": "Alibaba", "PDD": "PDD Temu", "JD": "JD.com", "BIDU": "Baidu",
    # USA — énergie / électricité / data centers / matières
    "CEG": "Constellation Energy", "VST": "Vistra", "NRG": "NRG Energy", "TLN": "Talen Energy",
    "NEE": "NextEra Energy", "GEV": "GE Vernova", "ETN": "Eaton", "VRT": "Vertiv", "MOD": "Modine",
    "EQIX": "Equinix", "DLR": "Digital Realty", "OKLO": "Oklo", "SMR": "NuScale", "CCJ": "Cameco",
    "XOM": "ExxonMobil", "CVX": "Chevron", "OXY": "Occidental", "FCX": "Freeport-McMoRan",
    "SCCO": "Southern Copper", "TECK": "Teck Resources", "RIO": "Rio Tinto", "BHP": "BHP",
    "MP": "MP Materials", "ALB": "Albemarle", "NEM": "Newmont", "AA": "Alcoa", "COPX": "Global X Copper Miners",
    # USA — autres grandes valeurs
    "JPM": "JPMorgan", "BAC": "Bank of America", "GS": "Goldman Sachs", "V": "Visa", "MA": "Mastercard",
    "PYPL": "PayPal", "XYZ": "Block", "COIN": "Coinbase", "MSTR": "Strategy MicroStrategy", "HOOD": "Robinhood",
    "SOFI": "SoFi", "WMT": "Walmart", "COST": "Costco", "HD": "Home Depot", "MCD": "McDonald's",
    "KO": "Coca-Cola", "PEP": "PepsiCo", "LLY": "Eli Lilly", "NVO": "Novo Nordisk", "UNH": "UnitedHealth",
    "PFE": "Pfizer", "MRK": "Merck", "ABBV": "AbbVie", "BA": "Boeing", "LMT": "Lockheed Martin",
    "RTX": "RTX Raytheon", "NOC": "Northrop Grumman", "CAT": "Caterpillar", "DE": "Deere", "GE": "GE Aerospace",
    "DIS": "Disney", "RIVN": "Rivian", "NIO": "NIO", "ABNB": "Airbnb", "RKLB": "Rocket Lab",
    # Allemagne
    "SAP.DE": "SAP", "SIE.DE": "Siemens", "ENR.DE": "Siemens Energy", "IFX.DE": "Infineon",
    "ALV.DE": "Allianz", "DTE.DE": "Deutsche Telekom", "BAS.DE": "BASF", "BAYN.DE": "Bayer",
    "BMW.DE": "BMW", "MBG.DE": "Mercedes-Benz", "VOW3.DE": "Volkswagen", "ADS.DE": "Adidas",
    "MUV2.DE": "Munich Re", "DBK.DE": "Deutsche Bank", "RHM.DE": "Rheinmetall", "MTX.DE": "MTU Aero",
    "HAG.DE": "Hensoldt", "DHL.DE": "DHL Group", "CBK.DE": "Commerzbank",
    # France
    "MC.PA": "LVMH", "OR.PA": "L'Oréal", "RMS.PA": "Hermès", "TTE.PA": "TotalEnergies", "SAN.PA": "Sanofi",
    "AIR.PA": "Airbus", "SU.PA": "Schneider Electric", "LR.PA": "Legrand", "AI.PA": "Air Liquide",
    "BNP.PA": "BNP Paribas", "GLE.PA": "Société Générale", "ACA.PA": "Crédit Agricole", "CS.PA": "AXA",
    "EL.PA": "EssilorLuxottica", "KER.PA": "Kering", "SAF.PA": "Safran", "HO.PA": "Thales",
    "AM.PA": "Dassault Aviation", "DSY.PA": "Dassault Systèmes", "CAP.PA": "Capgemini",
    "STMPA.PA": "STMicroelectronics", "NEX.PA": "Nexans", "SOI.PA": "Soitec", "ORA.PA": "Orange",
    "ENGI.PA": "Engie", "VIE.PA": "Veolia", "SGO.PA": "Saint-Gobain", "RNO.PA": "Renault",
    "DG.PA": "Vinci", "EN.PA": "Bouygues",
    # Pays-Bas / Belgique
    "ASML.AS": "ASML", "ASM.AS": "ASM International", "BESI.AS": "BE Semiconductor", "ADYEN.AS": "Adyen",
    "PRX.AS": "Prosus", "INGA.AS": "ING", "PHIA.AS": "Philips", "HEIA.AS": "Heineken", "ABI.BR": "AB InBev",
    # Italie / Espagne
    "PRY.MI": "Prysmian", "ENEL.MI": "Enel", "ISP.MI": "Intesa Sanpaolo", "UCG.MI": "UniCredit",
    "RACE.MI": "Ferrari", "LDO.MI": "Leonardo", "ENI.MI": "Eni", "STLAM.MI": "Stellantis",
    "SAN.MC": "Banco Santander", "IBE.MC": "Iberdrola", "ITX.MC": "Inditex", "BBVA.MC": "BBVA",
    # Suisse / Royaume-Uni / Nordiques
    "NESN.SW": "Nestlé", "NOVN.SW": "Novartis", "ROG.SW": "Roche", "ABBN.SW": "ABB", "UBSG.SW": "UBS",
    "SHEL.L": "Shell", "AZN.L": "AstraZeneca", "HSBA.L": "HSBC", "BP.L": "BP", "GLEN.L": "Glencore",
    "AAL.L": "Anglo American", "BA.L": "BAE Systems", "RR.L": "Rolls-Royce",
    "NOVO-B.CO": "Novo Nordisk", "VWS.CO": "Vestas", "ERIC-B.ST": "Ericsson", "VOLV-B.ST": "Volvo",
    "BOL.ST": "Boliden", "SAAB-B.ST": "Saab", "NOKIA.HE": "Nokia",
    # ETF / ETC UCITS (achetables sur TR)
    "SXR8.DE": "iShares Core S&P 500", "EUNL.DE": "iShares MSCI World", "SXRV.DE": "iShares Nasdaq 100",
    "VVSM.DE": "VanEck Semiconductor ETF", "4GLD.DE": "Xetra-Gold",
    "XAIX.DE": "Xtrackers Artificial Intelligence & Big Data ETF", "2B76.DE": "iShares Automation & Robotics ETF",
    "IQQH.DE": "iShares Global Clean Energy ETF", "EXS1.DE": "iShares Core DAX ETF", "C40.PA": "Amundi CAC 40 ETF",
    "EXSA.DE": "iShares STOXX Europe 600 ETF", "IS3N.DE": "iShares Core MSCI Emerging Markets IMI ETF",
    "DFEN.DE": "VanEck Defense ETF",
    # Crypto
    "BTC-EUR": "Bitcoin", "ETH-EUR": "Ethereum", "SOL-EUR": "Solana", "XRP-EUR": "XRP Ripple",
    "ADA-EUR": "Cardano", "DOGE-EUR": "Dogecoin", "DOT-EUR": "Polkadot", "LINK-EUR": "Chainlink",
    "AVAX-EUR": "Avalanche", "LTC-EUR": "Litecoin", "TRX-EUR": "Tron", "XLM-EUR": "Stellar",
}

UNIVERS_SCANNER = [s for s in NOMS if not s.endswith("-EUR") and s not in NON_TR]

# ─── Contexte des marchés mondiaux (briefings + filtre de régime) ──────────────────────────

MACRO = {
    "^VIX": "VIX (peur)", "ES=F": "S&P 500 futures", "NQ=F": "Nasdaq futures",
    "^STOXX50E": "Euro Stoxx 50", "^GDAXI": "DAX", "^FCHI": "CAC 40",
    "DX-Y.NYB": "Dollar index", "^TNX": "Taux US 10 ans", "EURUSD=X": "EUR/USD",
    "CL=F": "Pétrole WTI", "BZ=F": "Pétrole Brent", "GC=F": "Or", "HG=F": "Cuivre", "NG=F": "Gaz naturel US",
    "BTC-EUR": "Bitcoin",
}

ASIE = {  # indices + géants IA asiatiques (séance pendant la nuit en France)
    "^N225": "Nikkei 225", "^HSI": "Hang Seng", "000001.SS": "Shanghai", "^KS11": "Kospi",
    "^TWII": "Taïwan", "^BSESN": "Inde Sensex",
    "2330.TW": "TSMC Taïwan", "005930.KS": "Samsung", "000660.KS": "SK Hynix",
    "8035.T": "Tokyo Electron", "6857.T": "Advantest", "9984.T": "SoftBank",
    "0700.HK": "Tencent", "9988.HK": "Alibaba HK", "1810.HK": "Xiaomi",
}

EST = {"WIG20.WA": "Pologne WIG20", "XU100.IS": "Turquie BIST 100", "EPOL": "ETF Pologne"}

CONTEXTE = {
    "NVDA": "leader des GPU IA, baromètre de tout le secteur",
    "AMD": "GPU/CPU data center, challenger de NVIDIA",
    "AVGO": "puces IA sur-mesure (ASIC) et réseau data center",
    "TSM": "fonderie qui fabrique la quasi-totalité des puces IA",
    "ASML": "monopole des machines de lithographie EUV", "ASML.AS": "monopole des machines de lithographie EUV",
    "MU": "mémoire HBM indispensable aux GPU IA", "ARM": "architecture de puces sous licence",
    "MRVL": "puces réseau/optique et ASIC pour data centers", "SMCI": "serveurs IA et refroidissement liquide",
    "DELL": "serveurs IA pour entreprises et hyperscalers", "VRT": "alimentation et refroidissement de data centers",
    "CEG": "n°1 du nucléaire US, contrats d'électricité avec les data centers",
    "VST": "producteur d'électricité (Texas), demande data centers", "NRG": "électricité, charge data centers",
    "TLN": "nucléaire avec campus data center adossé", "EQIX": "n°1 mondial des data centers (REIT)",
    "DLR": "REIT data centers loués aux hyperscalers", "MOD": "refroidissement pour data centers",
    "GEV": "turbines à gaz et réseau électrique", "ETN": "équipement électrique de data centers",
    "OKLO": "petits réacteurs nucléaires pour data centers", "CCJ": "uranium", "ENR.DE": "turbines et réseau électrique",
    "SU.PA": "gestion électrique et refroidissement de data centers", "LR.PA": "infrastructure électrique data centers",
    "NEX.PA": "câbles électriques haute tension", "PRY.MI": "câbles électriques haute tension",
    "IFX.DE": "semi-conducteurs de puissance", "STMPA.PA": "semi-conducteurs", "SOI.PA": "substrats pour puces",
    "ASM.AS": "équipement de dépôt pour puces avancées", "BESI.AS": "packaging avancé (hybrid bonding) pour HBM",
    "FCX": "cuivre : câblage, réseaux électriques, data centers", "MP": "terres rares US (aimants)",
    "SCCO": "cuivre", "TECK": "cuivre et métaux de base", "RIO": "minier, forte exposition cuivre",
    "BHP": "minier n°1 mondial", "ALB": "lithium (batteries, stockage)", "NEM": "or",
    "GLEN.L": "cuivre, cobalt, négoce de matières", "AAL.L": "cuivre", "BOL.ST": "cuivre et zinc européen",
    "COPX": "ETF US des mineurs de cuivre — indicateur seulement, non achetable sur TR",
}
