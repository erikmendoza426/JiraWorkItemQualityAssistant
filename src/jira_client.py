"""Minimal Jira Cloud client. Comment-only by design: it can read issues and
add comments, and has NO method that edits issue fields, status, or labels.

Setup: copy .env.example to .env and fill in JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN.
CLI:   python src/jira_client.py whoami
       python src/jira_client.py issue PROJ-1
       python src/jira_client.py search "project = PROJ AND labels = needs-refinement"
"""
import json, os, sys
import requests
from dotenv import load_dotenv

load_dotenv()

REVIEW_MARK = "[wiqa:review]"
TESTS_MARK = "[wiqa:tests]"

class JiraClient:
    def __init__(self):
        self.base = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def _req(self, method: str, path: str, **kw):
        r = requests.request(method, f"{self.base}{path}", auth=self.auth,
                             headers=self.headers, timeout=30, **kw)
        if not r.ok:
            raise RuntimeError(f"Jira {method} {path} -> {r.status_code}: {r.text[:500]}")
        if not r.text:
            return {}
        try:
            return r.json()
        except ValueError:
            raise RuntimeError(
                f"Jira returned non-JSON for {method} {r.url} (status {r.status_code}, "
                f"content-type {r.headers.get('content-type')}). First 300 chars:\n{r.text[:300]}\n"
                "Check JIRA_BASE_URL: it must be exactly https://YOURSITE.atlassian.net "
                "(no /jira/... path, no trailing slash path, no quotes).")

    def whoami(self) -> dict:
        return self._req("GET", "/rest/api/3/myself")

    def get_issue(self, key: str) -> dict:
        return self._req("GET", f"/rest/api/3/issue/{key}",
                         params={"fields": "summary,description,issuetype,labels,parent,issuelinks,status"})

    def search(self, jql: str, max_results: int = 20) -> list[dict]:
        data = self._req("GET", "/rest/api/3/search/jql",
                         params={"jql": jql, "maxResults": max_results,
                                 "fields": "summary,description,issuetype,labels,parent,issuelinks,status"})
        return data.get("issues", [])

    def comment_texts(self, key: str) -> list[str]:
        """Plain text of every comment on the issue (read-only; used to avoid duplicate AI comments)."""
        data = self._req("GET", f"/rest/api/3/issue/{key}/comment", params={"maxResults": 100})
        return [adf_to_text(c.get("body")) for c in data.get("comments", [])]

    def add_comment(self, key: str, adf_body: dict) -> dict:
        return self._req("POST", f"/rest/api/3/issue/{key}/comment", data=json.dumps({"body": adf_body}))

# ---------- ADF (Atlassian Document Format) -> plain text ----------
def adf_to_text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return "\n"
    inner = [adf_to_text(c) for c in node.get("content", [])]
    if t == "listItem":
        return "- " + "".join(inner).strip() + "\n"
    if t in ("paragraph", "heading"):
        return "".join(inner) + "\n"
    if t in ("bulletList", "orderedList", "doc", "codeBlock", "blockquote"):
        return "".join(inner)
    return "".join(inner)

def extract_acceptance_criteria(text: str) -> tuple[str, list[str]]:
    """Find an 'Acceptance Criteria' heading line; return (description_without_it, bullets)."""
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip().lower().rstrip(":").replace("*", "") in ("acceptance criteria", "acceptance criterion"):
            ac = [l.strip().lstrip("-•* ").strip() for l in lines[i + 1:] if l.strip()]
            return "\n".join(lines[:i]).strip(), ac
    return text.strip(), []

TYPE_MAP = {"Story": "User Story", "Bug": "Bug", "Task": "Task", "Subtask": "Task", "Sub-task": "Task"}

def issue_to_work_item(issue: dict) -> dict:
    f = issue["fields"]
    desc, ac = extract_acceptance_criteria(adf_to_text(f.get("description")))
    item = {
        "id": int(issue["id"]),
        "title": f.get("summary", ""),
        "type": TYPE_MAP.get(f["issuetype"]["name"], f["issuetype"]["name"]),
        "description": desc,
        "acceptance_criteria": ac,
        "tags": f.get("labels", []),
    }
    if f.get("parent"):
        item["linked_items"] = [f["parent"]["fields"]["summary"]]
    return item

# ---------- draft result -> ADF comment ----------
def _p(text, bold=False):
    node = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return {"type": "paragraph", "content": [node]}

def _bullets(items):
    return {"type": "bulletList", "content": [
        {"type": "listItem", "content": [_p(i)]} for i in items]}

def result_to_adf(result: dict) -> dict:
    c = [_p(f"AI DRAFT {REVIEW_MARK}: review before acting. Nothing on this issue was changed.", bold=True),
         _p(f"Category: {result['category']}", bold=True)]
    for label, key in (("Missing information", "missing_information"),
                       ("Clarification questions", "clarification_questions"),
                       ("Suggested acceptance criteria", "suggested_acceptance_criteria"),
                       ("Draft test cases", "draft_test_cases"),
                       ("Manual review reasons", "manual_review_reasons")):
        vals = result.get(key) or []
        if vals:
            c += [_p(label, bold=True), _bullets([v if isinstance(v, str) else json.dumps(v) for v in vals])]
    if len(c) == 2:
        c.append(_p("No gaps found against the team rubric."))
    return {"type": "doc", "version": 1, "content": c}

def testcases_to_adf(result: dict) -> dict:
    c = [_p(f"AI DRAFT {TESTS_MARK}: draft test cases for the approved acceptance criteria. Review before use.", bold=True)]
    for n, t in enumerate(result["draft_test_cases"], 1):
        c.append(_p(f"{n}. {t['title']}", bold=True))
        c.append(_p(f"Covers: {t['covers_criterion']}"))
        c.append({"type": "orderedList", "content": [
            {"type": "listItem", "content": [_p(st)]} for st in t["steps"]]})
        c.append(_p(f"Expected: {t['expected_result']}"))
    return {"type": "doc", "version": 1, "content": c}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    jc = JiraClient()
    if cmd == "whoami":
        me = jc.whoami(); print("Connected as:", me.get("displayName"), me.get("emailAddress", ""))
    elif cmd == "issue":
        print(json.dumps(issue_to_work_item(jc.get_issue(sys.argv[2])), indent=2))
    elif cmd == "search":
        for i in jc.search(sys.argv[2]):
            print(i["key"], "|", i["fields"]["issuetype"]["name"], "|", i["fields"]["summary"])
    else:
        print(__doc__)
