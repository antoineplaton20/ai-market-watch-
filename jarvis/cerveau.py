# -*- coding: utf-8 -*-
"""Cerveau de Jarvis : boucle agentique Claude + outils + mémoire + historique par conversation."""
import json
import logging
import re
from datetime import datetime
from typing import Callable

import anthropic

from . import memoire, outils
from .config import CONVERSATIONS, EFFORT, FUSEAU, HISTORIQUE_MAX, MAX_TOKENS, MAX_TOURS_OUTILS, MODELE, NOM_UTILISATEUR

log = logging.getLogger("jarvis")

# Fixe (aucune date ni valeur variable) pour que le cache de prompt fonctionne d'un message à l'autre.
SYSTEME = f"""Tu es JARVIS, l'assistant personnel de ton utilisateur, que tu appelles « {NOM_UTILISATEUR} ». \
Tu t'inspires du J.A.R.V.I.S. de Tony Stark : calme, précis, loyal, une pointe d'humour britannique, jamais servile.

# Ta façon de travailler
- Tu réponds en français (sauf si on te parle dans une autre langue), clairement et sans remplissage.
- Tu ne devines pas quand tu peux vérifier : pour l'actualité, un fait récent, un prix, une donnée précise, \
utilise la recherche web et la lecture de pages, puis cite tes sources (titre + lien).
- Pour tout cours, tendance ou indicateur, utilise l'outil cours_marche. Pour les bots de trading, utilise \
etat_bots et les outils de lecture du projet (le code des bots est dans le dépôt).
- Sur un problème difficile, raisonne étape par étape, envisage plusieurs pistes, vérifie tes calculs, puis \
donne une conclusion nette avec ton niveau de confiance.
- Tu es honnête sur tes limites : si une information est incertaine, introuvable ou si un problème n'a pas \
de solution connue, dis-le franchement, puis propose la meilleure approche possible. N'invente jamais un \
chiffre, une source ou un résultat.

# Finance et trading
- L'utilisateur trade avec de petits montants (Trade Republic, 1 € de frais par ordre ; démo Binance avec \
le moteur V17). Tiens compte des frais dans tout calcul de gain.
- Donne des analyses argumentées (tendance, niveaux, risque, scénario inverse) mais rappelle qu'aucune \
prévision n'est garantie. Ne pousse jamais à risquer plus que ce qu'il peut perdre.
- piloter_bots a un effet réel : appelle-le seulement si l'utilisateur l'a demandé ; la confirmation lui est \
demandée automatiquement.

# Mémoire long terme
Tu as une mémoire persistante dans /memories (outil memory). Au début de chaque conversation, consulte \
/memories pour retrouver le profil de l'utilisateur, ses préférences, ses projets et décisions passées. \
Quand tu apprends quelque chose de durable (préférence, objectif, décision, information personnelle utile, \
leçon d'une analyse), enregistre-le de façon organisée (ex. /memories/profil.md, /memories/trading.md, \
/memories/projets.md). N'y stocke jamais de mot de passe ni de clé secrète.

# Format
- Messages lus sur téléphone (Telegram) ou dans un terminal : phrases courtes, listes si utile, pas de \
tableaux larges. Markdown simple uniquement (gras, italique, listes, liens, blocs de code).
- Chaque message utilisateur commence par [date heure] : c'est l'heure actuelle chez lui."""

BETAS = ["server-side-fallback-2026-07-01"]


def _vers_json(bloc) -> dict:
    """Bloc de réponse -> dict renvoyable tel quel à l'API (thinking, recherche web, etc. inclus)."""
    return bloc.model_dump(mode="json", exclude_none=True)


class Jarvis:
    def __init__(self):
        self.client = anthropic.Anthropic()
        self.outils = [*outils.OUTILS_SERVEUR, memoire.OUTIL_MEMOIRE, *outils.OUTILS_LOCAUX]
        self.en_attente: dict[str, dict] = {}      # actions à confirmer, par conversation

    # ── Historique ──────────────────────────────────────────────────────────
    def _fichier(self, conv: str):
        return CONVERSATIONS / f"{re.sub(r'[^A-Za-z0-9_-]', '_', conv)}.json"

    def charger(self, conv: str) -> list:
        try:
            return json.loads(self._fichier(conv).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def sauver(self, conv: str, messages: list):
        if len(messages) > HISTORIQUE_MAX:
            # On coupe par gros morceaux (moins d'invalidations du cache), sur un vrai message utilisateur
            # pour ne jamais séparer un appel d'outil de son résultat. La mémoire long terme garde l'essentiel.
            cible = len(messages) - HISTORIQUE_MAX // 2
            debuts = [i for i, m in enumerate(messages) if m["role"] == "user" and self._texte_utilisateur(m)]
            coupe = next((i for i in debuts if i >= cible), None)
            if coupe:
                messages = messages[coupe:]
        self._fichier(conv).write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _texte_utilisateur(m) -> bool:
        c = m["content"]
        return isinstance(c, str) or not any(b.get("type") == "tool_result" for b in c)

    @staticmethod
    def _inacheve(m) -> bool:
        if m["role"] == "user":
            return True                                   # résultats d'outils non traités
        types = [b.get("type") for b in m["content"]]
        return "tool_use" in types or (types and types[-1] == "server_tool_use")

    def oublier(self, conv: str):
        self._fichier(conv).unlink(missing_ok=True)
        self.en_attente.pop(conv, None)

    # ── Outils ──────────────────────────────────────────────────────────────
    def _executer_outil(self, conv: str, bloc, confirmer: Callable[[str], bool | None]) -> dict:
        res = {"type": "tool_result", "tool_use_id": bloc.id}
        try:
            if bloc.name == "memory":
                res["content"] = memoire.executer(bloc.input)
                return res
            erreur = outils.valider(bloc.name, bloc.input)
            if erreur:
                return {**res, "content": erreur, "is_error": True}
            if bloc.name in outils.ACTIONS_A_CONFIRMER:
                question = f"{bloc.name} : {json.dumps(bloc.input, ensure_ascii=False)}"
                ok = confirmer(question)
                if ok is None:          # confirmation asynchrone (Telegram : /oui ou /non)
                    self.en_attente[conv] = {"nom": bloc.name, "entree": bloc.input}
                    res["content"] = ("En attente : l'utilisateur doit confirmer avec /oui (ou annuler avec /non). "
                                      "Dis-lui simplement ce qui va se passer.")
                    return res
                if not ok:
                    res["content"] = "Action refusée par l'utilisateur. Ne pas la relancer sans nouvelle demande."
                    return res
            log.info("outil %s %s", bloc.name, bloc.input)
            res["content"] = outils.FONCTIONS[bloc.name](**bloc.input)
        except Exception as e:
            log.exception("outil %s", bloc.name)
            res.update(content=f"Erreur : {type(e).__name__}: {e}", is_error=True)
        return res

    def executer_action_en_attente(self, conv: str) -> str | None:
        action = self.en_attente.pop(conv, None)
        if not action:
            return None
        log.info("action confirmée %s", action)
        try:
            return outils.FONCTIONS[action["nom"]](**action["entree"])
        except Exception as e:
            return f"Erreur : {type(e).__name__}: {e}"

    # ── Conversation ────────────────────────────────────────────────────────
    def repondre(self, conv: str, contenu, confirmer: Callable[[str], bool | None] = lambda q: None) -> str:
        """`contenu` : texte, ou liste de blocs (texte + images/PDF). Renvoie la réponse finale."""
        now = datetime.now(FUSEAU)
        jour = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")[now.weekday()]
        horodatage = now.strftime(f"[{jour} %d/%m/%Y %H:%M]")
        if isinstance(contenu, str):
            contenu = [{"type": "text", "text": f"{horodatage} {contenu}"}]
        else:
            contenu = [{"type": "text", "text": horodatage}, *contenu]
        historique = self.charger(conv)
        messages = [*historique, {"role": "user", "content": contenu}]
        textes: list[str] = []

        try:
            for _ in range(MAX_TOURS_OUTILS):
                with self.client.beta.messages.stream(
                    model=MODELE,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEME,
                    messages=messages,
                    tools=self.outils,
                    thinking={"type": "adaptive"},
                    output_config={"effort": EFFORT},
                    cache_control={"type": "ephemeral"},
                    betas=BETAS,
                    fallbacks="default",
                ) as flux:
                    rep = flux.get_final_message()
                log.info("stop=%s in=%s out=%s cache=%s", rep.stop_reason, rep.usage.input_tokens,
                         rep.usage.output_tokens, rep.usage.cache_read_input_tokens)

                if rep.stop_reason == "refusal":
                    self.sauver(conv, historique)          # on n'empoisonne pas l'historique
                    return "Je ne peux pas vous aider sur ce point, " + NOM_UTILISATEUR + "."

                messages.append({"role": "assistant", "content": [_vers_json(b) for b in rep.content]})
                textes = [b.text for b in rep.content if b.type == "text" and b.text.strip()] or textes
                appels = [b for b in rep.content if b.type == "tool_use"]

                if rep.stop_reason == "pause_turn":
                    continue                              # recherche web longue : le serveur reprend
                if appels:
                    if rep.stop_reason == "max_tokens":
                        resultats = [{"type": "tool_result", "tool_use_id": b.id, "is_error": True,
                                      "content": "Appel tronqué (limite de longueur). Recommence plus court."}
                                     for b in appels]
                    else:
                        resultats = [self._executer_outil(conv, b, confirmer) for b in appels]
                    messages.append({"role": "user", "content": resultats})
                    continue
                break
            else:
                textes.append("(J'ai atteint ma limite d'étapes pour cette demande : dites-moi si je continue.)")
        except anthropic.AuthenticationError:
            return "Clé ANTHROPIC_API_KEY invalide ou absente : vérifiez jarvis/.env."
        except anthropic.RateLimitError:
            return "Trop de demandes en même temps côté Anthropic. Réessayez dans une minute."
        except anthropic.APIStatusError as e:
            log.exception("API")
            return f"Erreur de l'API Claude ({e.status_code}) : {e.message}"
        except anthropic.APIConnectionError:
            return "Impossible de joindre l'API Claude (réseau). Réessayez plus tard."

        # Si la boucle s'est arrêtée en plein travail (limite d'étapes), on retire la fin inachevée
        # (appels d'outils sans suite) pour garder un historique valide.
        while len(messages) > len(historique) + 1 and self._inacheve(messages[-1]):
            messages.pop()
        self.sauver(conv, messages)
        return "\n\n".join(textes) or "(Aucune réponse.)"
