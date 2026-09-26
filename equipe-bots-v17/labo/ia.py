"""Idée en français -> spécification de stratégie, par Claude (sortie JSON structurée).

Claude ne produit JAMAIS de code exécuté : il choisit des blocs du catalogue (strategie.BLOCS) et leurs réglages.
La réponse est ensuite vérifiée et bornée par strategie.normaliser. Sans clé ANTHROPIC_API_KEY, le labo reste
utilisable avec les exemples.

Modèle : LABO_MODELE_IA (défaut claude-opus-5), avec repli automatique côté serveur si la demande est refusée.
Coût indicatif : quelques centimes par idée.
"""
from __future__ import annotations

import json
import os

from .strategie import BLOCS, LIMITES, TYPES, UNITES, normaliser

MODELE = os.getenv("LABO_MODELE_IA", "claude-opus-5")

_BLOC = {
    "type": "object",
    "properties": {"type": {"type": "string"}, "periode": {"type": "integer"}, "periode2": {"type": "integer"},
                   "seuil": {"type": "number"}, "seuil2": {"type": "number"}},
    "required": ["type", "periode", "periode2", "seuil", "seuil2"],
    "additionalProperties": False,
}


def _bloc_famille(famille):
    b = json.loads(json.dumps(_BLOC))
    b["properties"]["type"] = {"type": "string", "enum": TYPES[famille]}
    return b


SCHEMA = {
    "type": "object",
    "properties": {
        "nom": {"type": "string"},
        "explication": {"type": "string"},
        "remarques": {"type": "string"},
        "unite": {"type": "string", "enum": list(UNITES)},
        "tendance": _bloc_famille("tendance"),
        "confirmations": {"type": "array", "items": _bloc_famille("confirmation")},
        "filtre": _bloc_famille("filtre"),
        "stop_atr": {"type": "number"},
        "rr": {"type": "number"},
        "sortie_tendance": {"type": "boolean"},
    },
    "required": ["nom", "explication", "remarques", "unite", "tendance", "confirmations", "filtre", "stop_atr", "rr",
                 "sortie_tendance"],
    "additionalProperties": False,
}


def _catalogue():
    lignes = []
    for famille in ("tendance", "confirmation", "filtre"):
        lignes.append(f"{famille.upper()} :")
        for t in TYPES[famille]:
            _, desc, params = BLOCS[t]
            p = ", ".join(f"{k} de {a} à {b}" for k, (a, b, _) in params.items()) or "aucun réglage"
            lignes.append(f"  - {t} : {desc} ({p})")
    return "\n".join(lignes)


SYSTEME = f"""Tu es un chercheur quantitatif. Tu traduis une idée de stratégie de trading crypto, écrite en français \
par un débutant, en une spécification qui sera testée sur l'historique Binance (BTC, ETH, SOL).

Méthode imposée (une seule position à la fois, ACHAT SEULEMENT, spot, jamais de levier ni de vente à découvert) :
- 1 bloc de TENDANCE, 2 CONFIRMATIONS de types différents et si possible non corrélées (par exemple un élan et une \
force de tendance, pas deux oscillateurs qui disent la même chose), 1 FILTRE de volatilité ou de volume (ou « aucun ») ;
- stop = stop_atr × ATR 14 sous le prix (de {LIMITES['stop_atr'][0]} à {LIMITES['stop_atr'][1]}), objectif = rr fois \
ce risque (de {LIMITES['rr'][0]} à {LIMITES['rr'][1]}) ;
- unite : taille des bougies (15m, 1h ou 4h). Les frais (0,1 % par côté) pénalisent fortement les petites unités.

Blocs autorisés et bornes des réglages (utilise 0 pour les champs sans objet) :
{_catalogue()}

Règles :
- Reste fidèle à l'idée. Si elle demande quelque chose d'impossible ici (vente à découvert, levier, indicateur absent \
du catalogue, actif non crypto), choisis l'équivalent le plus proche et explique-le dans « remarques ».
- Choisis des réglages classiques et raisonnables ; n'essaie pas de deviner des réglages « magiques ».
- « nom » : 60 caractères au plus. « explication » : 2 phrases simples en français, sans jargon. \
« remarques » : ce que tu as dû adapter, ou une chaîne vide.
- Ne promets aucun résultat : la stratégie sera jugée par le backtest."""


class IAIndisponible(RuntimeError):
    pass


def _cle():
    return os.getenv("ANTHROPIC_API_KEY", "").strip()      # .env déjà chargé par la configuration v17


def generer(idee, client=None):
    """-> (spécification normalisée, remarques). Lève IAIndisponible avec un message clair en cas d'échec."""
    idee = (idee or "").strip()
    if len(idee) < 10:
        raise IAIndisponible("Décris ton idée en une ou deux phrases (10 caractères au moins).")
    if client is None:
        if not _cle():
            raise IAIndisponible("Pas de clé ANTHROPIC_API_KEY sur le serveur : utilise un exemple, ou ajoute la clé "
                                 "avec « bots config ».")
        import anthropic
        client = anthropic.Anthropic(api_key=_cle(), timeout=120.0, max_retries=2)
    sortie = {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    demande = dict(model=MODELE, max_tokens=16000, system=SYSTEME, messages=[{"role": "user", "content": idee[:2000]}])
    try:
        # extra_body / extra_headers : compatibles avec toutes les versions du SDK installées sur le serveur.
        try:
            r = client.messages.create(**demande, extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                                       extra_body={"fallbacks": "default", "output_config": sortie})
        except Exception as ex:
            if type(ex).__name__ != "BadRequestError":
                raise
            r = client.messages.create(**demande, extra_body={"output_config": sortie})   # sans repli automatique
    except Exception as ex:
        raise IAIndisponible(f"Claude injoignable ({type(ex).__name__}). Réessaie dans un instant.")
    if getattr(r, "stop_reason", None) == "refusal":
        raise IAIndisponible("Claude a refusé cette demande. Reformule ton idée de stratégie.")
    if getattr(r, "stop_reason", None) == "max_tokens":
        raise IAIndisponible("Réponse de Claude incomplète. Réessaie avec une idée plus courte.")
    texte = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text")
    try:
        brut = json.loads(texte)
        return normaliser(brut), str(brut.get("remarques") or "")[:500]
    except ValueError as ex:                      # JSON illisible ou SpecInvalide (sous-classe de ValueError)
        raise IAIndisponible(f"Stratégie proposée inutilisable ({str(ex)[:120]}). Réessaie ou reformule.")
