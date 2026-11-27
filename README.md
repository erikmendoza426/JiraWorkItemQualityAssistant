# WIQA: Jira Work Item Quality AI Assistant (COMP 684)

A human adds the label `needs-refinement` to a Jira work item. The AI reviews it against a team rubric (from a local KB) and posts a **draft comment**. After a human approves acceptance criteria and adds `ac-approved`, the AI drafts test cases. A human then records accept (`ai-accepted`)/edit(`ai-edited`)/reject(`ai-rejected`) with a label. The system is **comment-only**: it never edits fields, labels, state, or assignments. These labels are watched for in the Jira board automation rules and sends a POST web request.

```
Jira label added -> Jira Automation rule -> Webhook receiver (FastAPI) -> Queue
  -> Worker (fetch item, retrieve KB, Gemini on Vertex AI, validate) -> Jira comment
  -> human accept/edit/reject label -> /webhook/decision -> data store (SQLite) -> KB ingest
```

## Repo layout
| Path | Purpose |
|---|---|
| `src/receiver.py` | Webhook receiver API: validates secret, enqueues, returns immediately |
| `src/jobqueue.py` | In-process queue, retry, dead-letter file, SQLite data store |
| `src/worker.py` | `process_issue(key, mode)`: the single entry point for review / tests |
| `src/assess.py`, `testgen.py` | Prompt + Gemini call + schema validation |
| `src/retrieve.py`, `rules.py`, `schema.py` | KB retrieval, keyword risk rules, output schemas |
| `src/jira_client.py` | Jira REST client (read + comment only, no edit methods) |
| `src/poller.py` | Fallback trigger: polls Jira instead of using the webhook |
| `src/ingest.py` | Accepted/edited decisions -> `kb/past_items/` |
| `wiqa_agent/` | Headless ADK wrapper around `process_issue` (optional) |
| `kb/` | rubric, definition of done, past items |
| `eval/` | golden / holdout / smoke sets and `run_eval.py` |
| `config/config.yaml` | Vertex project, model, labels, retries, etc. |

## 1. Prerequisites
- Python 3.12, Git
- A Jira Cloud site and project (we use key `KAN`) where you can create Automation rules
- A Google Cloud project with **billing linked** and the **Vertex AI API enabled**, and your Google account granted **Vertex AI User** on it
- Google Cloud CLI (`gcloud`)
- A free ngrok account

### Jira access
Creating Automation rules requires project admin on the Jira project. Either:
- Use the shared team board (site: <your-site>.atlassian.net, project key <KEY>), owned by <name>. Only the owner needs to run the receiver and ngrok; everyone else adds labels and reviews comments.
- Or create your own free Jira Cloud site and project, then follow sections 2-4 yourself. Rules point to one ngrok URL, so each runner needs their own project and rules.
Set `jira_project` in `config/config.yaml` to your project key.
Run limits: the plan's Automation runs are shared across the site, so multiple people testing at once burns through the quota faster. Check the usage page under Automation.
One receiver per URL: being admin doesn't change that the rules point at one ngrok URL. Only edit the URL in the rules when the runner changes, or your teammate's changes will send requests to the wrong machine.

## 2. Setup
```powershell
git clone <repo-url>
cd <repo-folder>
python -m venv .venv
.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
gcloud auth application-default login
```
(If you move the project folder, delete and recreate `.venv`.)

### Configure
1. Copy `.env.example` to `.env` and fill in:
   - `JIRA_BASE_URL`: site root only, e.g. `https://yoursite.atlassian.net` (no `/jira/...` path)
   - `JIRA_EMAIL`, `JIRA_API_TOKEN`: create the token at id.atlassian.com (Security > API tokens)
   - `WEBHOOK_SECRET`: generate a random long string with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. In `config/config.yaml` set `project` to **your** GCP project ID (the ID, not the display name), plus `jira_project` and label names if different. Keep `location: global` for the preview Gemini model.
3. Check it works:
   ```powershell
   python src/jira_client.py whoami
   python src/assess.py eval/golden/g301.json
   ```

Comments are posted under whoever owns the API token.

## 3. Run it (two terminals, venv active in the first)
Terminal 1:
```powershell
python -m uvicorn --app-dir src receiver:app --port 8000
```
Terminal 2 (ngrok 3.30.0+ is required; run `ngrok update` if you get an "agent too old" error):
```powershell
ngrok config add-authtoken <your-ngrok-token>      # once
ngrok http 127.0.0.1:8000
```
Claim a free static domain in the ngrok dashboard (Domains) so the URL doesn't change, then run `ngrok http --url=<your-domain> 127.0.0.1:8000` (older builds use `--domain`). Check `https://<your-domain>/health` returns `{"ok":true}`.

## 4. Jira Automation rules
Project settings > Automation > Create rule. Each rule: trigger **Value changes for Labels**, a condition on the label, action **Send web request**.

| Rule | Condition | URL | Body |
|---|---|---|---|
| Review | labels contain `needs-refinement` | `/webhook/jira` | `{"issue_key":"{{issue.key}}","mode":"review"}` |
| Test Gen | labels contain `ac-approved` | `/webhook/jira` | `{"issue_key":"{{issue.key}}","mode":"tests"}` |
| Decision | labels contain `ai-accepted` / `ai-edited` / `ai-rejected` | `/webhook/decision` | `{"issue_key":"{{issue.key}}","decision":"accepted"}` (`edited` / `rejected` to match) |

For all rules: method POST, headers `X-Webhook-Secret: <your secret>` and `Content-Type: application/json`, "wait for response" off. Publish the rule (drafts don't run). Use the rule's **audit log** to debug. If the three decision labels are combined in one if/else rule, each branch needs its own condition and web request; if branches don't match, use three separate rules or a JQL condition like `labels = "ai-accepted"`.

Check your Jira plan's Automation run limit: every label change can trigger every rule.

## 5. Test the flow
1. Create a work item (Story/Bug/Task). Acceptance criteria go as bullets under a line reading `Acceptance criteria` at the end of the description.
2. Add `needs-refinement`. Within about 30 seconds a comment marked `[wiqa:review]` appears.
3. Edit the criteria, add `ac-approved`. A `[wiqa:tests]` comment appears.
4. Add `ai-accepted`, `ai-edited`, or `ai-rejected`. Check the store:
   ```powershell
   python -c "import sqlite3; print(sqlite3.connect('logs/store.db').execute('select * from decisions').fetchall())"
   ```

Test the receiver without Jira (PowerShell):
```powershell
$env:WS = "<your secret>"
Invoke-RestMethod -Method Post -Uri http://localhost:8000/webhook/jira -Headers @{ "X-Webhook-Secret" = $env:WS } -ContentType "application/json" -Body '{"issue_key":"KAN-5","mode":"review"}'
```
This posts a real comment if the label is present and no review comment exists yet.

Fallback trigger if the webhook path is down: `python src/poller.py --dry --once`, then `python src/poller.py`.

## 6. Troubleshooting
| Symptom | Cause / fix |
|---|---|
| `No module named 'google'` | venv not active, or recreate it and reinstall requirements |
| `KeyError: 'WEBHOOK_SECRET'` | add it to `.env` (verify with `python -c "from dotenv import dotenv_values; print(list(dotenv_values('.env').keys()))"`) |
| `403 ... REPLACE_WITH_GCP_PROJECT_ID` | set `project` in `config/config.yaml`; restart uvicorn |
| `ERR_NGROK_8012` | uvicorn not running, or use `ngrok http 127.0.0.1:8000` |
| `ERR_NGROK_121` | ngrok agent too old: `ngrok update` |
| `401` from receiver | secret in the Jira header differs from `.env` |
| `queued: true` but no comment | check uvicorn output and `logs/dlq.jsonl`; label missing returns `refused`, existing marker returns `skipped_duplicate` |
| Jira rule shows "No actions performed" | condition did not match the issue at that moment; the trigger also fires on label removal |
| Vertex `429` | quota burst; code backs off and retries |
| PowerShell curl JSON errors | use `Invoke-RestMethod` as above |

## 7. Known limitations
- The queue is in-memory: queued jobs are lost if uvicorn restarts. Dead-lettered jobs go to `logs/dlq.jsonl`.
- Comments post under the API token owner's account; production would use a bot account.
- Golden-set labels were AI-drafted; relabel independently before trusting scores. Do not tune against the holdout set.
- Decision events are not deduplicated.
- The KB is local JSON with keyword retrieval, not a managed RAG service.