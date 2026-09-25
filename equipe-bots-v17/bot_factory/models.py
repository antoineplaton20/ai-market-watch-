from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class BotSpec:
    id: str
    name: str
    department: str
    mission: str
    specialty: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    model_policy: str = "local_first"
    memory: str = "none"
    supervisor: Optional[str] = None
    permissions: List[str] = field(default_factory=lambda: ["read"])
    evaluation: List[str] = field(default_factory=list)
    risk_level: str = "low"
    status: str = "planned"

@dataclass
class TeamSpec:
    id: str
    name: str
    mission: str
    manager: str
    members: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    approval_mode: str = "supervised"
