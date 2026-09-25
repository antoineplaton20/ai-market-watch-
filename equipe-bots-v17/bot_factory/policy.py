from dataclasses import dataclass

@dataclass
class PolicyDecision:
    allowed: bool
    reason: str

class PolicyEngine:
    """Deny-by-default for side effects. Planning/read-only are separated from acting."""
    WRITE_TOOLS = {"filesystem_write", "git_write", "api_write", "shell", "browser_action", "cloud_mutation", "trade"}
    def authorize(self, permissions, action, approved=False):
        if action in self.WRITE_TOOLS and not approved:
            return PolicyDecision(False, "side_effect_requires_explicit_approval")
        if action not in permissions and action not in {"read", "plan"}:
            return PolicyDecision(False, "permission_not_granted")
        return PolicyDecision(True, "allowed")
