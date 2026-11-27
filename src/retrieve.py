"""Local retrieval stub. Same interface a Vertex RAG Engine retrieval call will have later."""
import json, re
from pathlib import Path

def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", text.lower()))

def load_static(kb_dir: str) -> dict:
    d = Path(kb_dir)
    return {
        "rubric": json.loads((d / "rubric.json").read_text()),
        "definition_of_done": json.loads((d / "definition_of_done.json").read_text()),
    }

def retrieve_past_items(item: dict, kb_dir: str, k: int) -> list[dict]:
    """Keyword-overlap ranking over kb/past_items. Swap for Vertex RAG retrieval later."""
    q = _tokens(f"{item.get('title','')} {item.get('description','')}")
    scored = []
    for p in sorted((Path(kb_dir) / "past_items").glob("*.json")):
        doc = json.loads(p.read_text())
        if doc.get("id") == item.get("id"):
            continue
        d = _tokens(f"{doc.get('title','')} {doc.get('description','')}")
        scored.append((len(q & d) / (len(q) or 1), doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:k]]
