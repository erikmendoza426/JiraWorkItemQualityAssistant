"""Single entry point: one issue, one stage. Used by poller, CLI, and the agent."""
import time
from assess import assess, audit, load_config
from testgen import generate_tests
from jira_client import (JiraClient, issue_to_work_item, result_to_adf, testcases_to_adf,
                         REVIEW_MARK, TESTS_MARK)

def process_issue(key: str, mode: str, post: bool = True, jc=None, cfg=None) -> dict:
    cfg, jc = cfg or load_config(), jc or JiraClient()
    label, mark = ((cfg["review_label"], REVIEW_MARK) if mode == "review"
                   else (cfg["tests_label"], TESTS_MARK))
    issue = jc.get_issue(key)
    if label not in issue["fields"].get("labels", []):
        return {"status": "refused", "reason": f"missing label '{label}'"}
    if any(mark in t for t in jc.comment_texts(key)):
        return {"status": "skipped_duplicate"}
    item = issue_to_work_item(issue)
    if mode == "review":
        result, usage, raw = assess(item, cfg, use_kb=True)
        body, summary = result_to_adf(result), result["category"]
    else:
        if not item["acceptance_criteria"]:
            return {"status": "refused", "reason": "no acceptance criteria"}
        result, usage = generate_tests(item, cfg)
        body, summary, raw = testcases_to_adf(result), f"{len(result['draft_test_cases'])} test cases", None
    audit({"ts": time.time(), "jira_key": key, "stage": mode, "model": cfg["model"],
           "rubric_version": cfg["rubric_version"], "usage": usage, "summary": summary,
           "llm_category": raw, "posted": post})
    if post:
        jc.add_comment(key, body)
    return {"status": "posted" if post else "draft_only", "summary": summary}