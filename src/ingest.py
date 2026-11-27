"""Accepted/edited review decisions -> kb/past_items. Run before a refresh: python src/ingest.py"""
import json
from assess import ROOT, load_config
from jira_client import JiraClient, issue_to_work_item
from jobqueue import db

jc = JiraClient()
with db() as c:
    rows = c.execute("""SELECT d.key, d.decision, r.summary FROM decisions d
                        JOIN reviews r ON r.key=d.key AND r.mode='review'
                        WHERE d.decision IN ('accepted','edited')""").fetchall()
for key, decision, category in rows:
    item = issue_to_work_item(jc.get_issue(key))
    item["outcome"] = category          # ASSUMPTION: match the format of your existing past_items
    out = ROOT / load_config()["kb_dir"] / "past_items" / f"jira-{key}.json"
    out.write_text(json.dumps(item, indent=2))
    print("ingested", key, decision)