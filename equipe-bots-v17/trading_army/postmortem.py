class TradePostmortem:
    def analyze(self, decision, result, market_context=None):
        return {"intent_id": result.intent_id, "status": result.status, "decision": decision, "market_context": market_context or {}, "lessons": []}
