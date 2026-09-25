"""Mise en forme française des montants (messages Telegram de la v17)."""


def _fr(texte):
    return texte.replace(",", " ").replace(".", ",")


def prix(x):
    x = float(x)
    if abs(x) >= 1000:
        return _fr(f"{x:,.0f}")
    if abs(x) >= 1:
        return _fr(f"{x:,.2f}")
    return _fr(f"{x:.6g}")


def dollars(x, signe=False):
    x = float(x)
    corps = _fr(f"{abs(x):,.2f}") + " $"
    if signe:
        return ("+" if x >= 0 else "-") + corps
    return ("-" if x < 0 else "") + corps


def pct(x, signe=True):
    x = float(x)
    return (("+" if x >= 0 else "") if signe else "") + _fr(f"{x:.1f}") + " %"


MODES = {"paper": "fictif (portefeuille v17, aucun ordre Binance)", "demo": "compte démo Binance (argent fictif, vrais ordres)",
         "testnet": "testnet Binance", "live": "ARGENT RÉEL"}
