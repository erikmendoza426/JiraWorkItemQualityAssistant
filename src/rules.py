"""Deterministic category rules. Override the LLM when risky terms appear."""
import re

RISK_PATTERNS = {
    "authorization/security": r"\b(auth|authn|authz|authoriz\w*|authentic\w*|permission\w*|role\w*|jwt|token\w*|oauth|password\w*|encrypt\w*|secret\w*|credential\w*|admin)\b",
    "production infrastructure": r"\b(production|prod|infrastructure|terraform|kubernetes|k8s|deploy\w*|rollout|dns|load balancer)\b",
    "data change": r"\b(migrat\w*|schema|drop (table|column|field)|database|column|backfill|delete all)\b",
    "API breakage": r"\b(breaking change|deprecat\w*|api contract|api response|remove endpoint|rename endpoint)\b",
}

def risk_hits(item: dict) -> list[str]:
    text = " ".join(str(item.get(k, "")) for k in ("title", "description")).lower()
    return [name for name, pat in RISK_PATTERNS.items() if re.search(pat, text)]

def apply_rules(result: dict, item: dict) -> dict:
    hits = risk_hits(item)
    if hits and result["category"] != "Requires Manual Review":
        result["category"] = "Requires Manual Review"
        result["manual_review_reasons"] = [f"Rule match: {h}" for h in hits]
    elif hits:
        result.setdefault("manual_review_reasons", [f"Rule match: {h}" for h in hits])
    return result
