"""Traduction d'une stratégie du labo en Pine Script v6, à coller dans l'éditeur Pine de TradingView.

Même logique que le moteur du labo : signal à la clôture, achat à l'ouverture suivante, stop sous la clôture
du signal (stop_atr × ATR 14), objectif rr × ce risque, frais 0,1 % par côté, une position à la fois.
Le testeur de stratégie de TradingView ne reproduira pas exactement les chiffres du labo (données, glissement,
ordre des événements dans une bougie) : c'est une seconde opinion utile, pas une copie conforme.
"""
from __future__ import annotations

import json


def _cond(b, nom):
    t = b["type"]
    p, p2, s, s2 = b.get("periode"), b.get("periode2"), b.get("seuil"), b.get("seuil2")
    if t == "prix_au_dessus_ema":
        return [f"{nom} = close > ta.ema(close, {p})"]
    if t == "ema_croisee":
        return [f"{nom} = ta.ema(close, {p}) > ta.ema(close, {p2})"]
    if t == "supertrend":
        return [f"[{nom}_st, {nom}_dir] = ta.supertrend({s}, {p})", f"{nom} = {nom}_dir < 0"]
    if t == "donchian_cassure":
        return [f"{nom} = close > ta.highest(high, {p})[1]"]
    if t == "rsi_au_dessus":
        return [f"{nom} = ta.rsi(close, {p}) > {s}"]
    if t == "rsi_sous":
        return [f"{nom} = ta.rsi(close, {p}) < {s}"]
    if t == "macd_positif":
        return [f"[{nom}_m, {nom}_s, {nom}_h] = ta.macd(close, {p}, {p2}, 9)", f"{nom} = {nom}_h > 0"]
    if t == "adx_fort":
        return [f"[{nom}_dp, {nom}_dm, {nom}_adx] = ta.dmi({p}, {p})", f"{nom} = {nom}_adx > {s}"]
    if t == "momentum_positif":
        return [f"{nom} = close > close[{p}]"]
    if t == "bollinger_bas":
        return [f"[{nom}_mid, {nom}_up, {nom}_lo] = ta.bb(close, {p}, {s})", f"{nom} = close < {nom}_lo"]
    if t == "volume_superieur":
        return [f"{nom} = volume > {s} * ta.sma(volume, {p})"]
    if t == "atr_pct_entre":
        return [f"{nom}_pct = ta.atr({p}) / close * 100", f"{nom} = {nom}_pct >= {s} and {nom}_pct <= {s2}"]
    if t == "aucun":
        return [f"{nom} = true"]
    raise ValueError(t)


def generer(spec):
    titre = json.dumps(f"Labo · {spec['nom']}"[:60], ensure_ascii=False)     # chaîne Pine correctement échappée
    lignes = [
        "//@version=6",
        f"// {spec['nom']} — généré par le labo de l'équipe de bots. Unité conseillée : {spec['unite']}.",
        "// Achat seulement, une position à la fois, frais 0,1 % par côté. Aucun ordre réel n'est passé par ce script.",
        f"strategy({titre}, overlay = true, initial_capital = 1000, default_qty_type = strategy.percent_of_equity,",
        "     default_qty_value = 100, commission_type = strategy.commission.percent, commission_value = 0.1,",
        "     pyramiding = 0, process_orders_on_close = false)",
        "",
        f"stopAtr = input.float({spec['stop_atr']}, \"Stop (× ATR)\", minval = 0.1)",
        f"rr = input.float({spec['rr']}, \"Objectif (× risque)\", minval = 0.1)",
        f"sortieTendance = input.bool({'true' if spec['sortie_tendance'] else 'false'}, \"Sortir si la tendance se retourne\")",
        "",
        "// Tendance",
        *_cond(spec["tendance"], "tendance"),
        "// Confirmations",
        *_cond(spec["confirmations"][0], "conf1"),
        *_cond(spec["confirmations"][1], "conf2"),
        "// Filtre",
        *_cond(spec["filtre"], "filtre"),
        "",
        "atr = ta.atr(14)",
        "signal = tendance and conf1 and conf2 and filtre and strategy.position_size == 0",
        "var float stopPx = na",
        "var float objectifPx = na",
        "if signal",
        "    stopPx := close - stopAtr * atr",
        "    objectifPx := close + rr * stopAtr * atr",
        "    strategy.entry(\"Achat\", strategy.long)",
        "strategy.exit(\"Sortie\", \"Achat\", stop = stopPx, limit = objectifPx)",
        "if sortieTendance and strategy.position_size > 0 and not tendance",
        "    strategy.close(\"Achat\", comment = \"Tendance\")",
        "",
        "plotshape(signal, \"Signal\", shape.triangleup, location.belowbar, color.new(color.green, 0), size = size.small)",
        "plot(strategy.position_size > 0 ? stopPx : na, \"Stop\", color.new(color.red, 0), style = plot.style_linebr)",
        "plot(strategy.position_size > 0 ? objectifPx : na, \"Objectif\", color.new(color.green, 0), style = plot.style_linebr)",
        "alertcondition(signal, \"Signal du labo\", \"Signal d'achat : {{ticker}} à {{close}}\")",
    ]
    return "\n".join(lignes) + "\n"
