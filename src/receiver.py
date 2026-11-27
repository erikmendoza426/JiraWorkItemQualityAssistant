"""Validate + enqueue + return immediately."""
import hmac, os, re
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from assess import load_config
import jobqueue

load_dotenv()
SECRET, CFG = os.environ["WEBHOOK_SECRET"], load_config()
KEY_RE = re.compile(rf"^{re.escape(CFG['jira_project'])}-\d+$")
app = FastAPI()

@app.on_event("startup")
def _start(): jobqueue.start()

def _auth(secret):
    if not secret or not hmac.compare_digest(secret, SECRET):
        raise HTTPException(401, "bad secret")

class Hook(BaseModel):
    issue_key: str
    mode: str                      # review | tests

class Decision(BaseModel):
    issue_key: str
    decision: str                  # accepted | edited | rejected

@app.post("/webhook/jira")
def hook(h: Hook, x_webhook_secret: str = Header(None)):
    _auth(x_webhook_secret)
    if h.mode not in ("review", "tests") or not KEY_RE.match(h.issue_key):
        raise HTTPException(400, "invalid request")
    return {"queued": jobqueue.enqueue(h.issue_key, h.mode)}

@app.post("/webhook/decision")
def decision(d: Decision, x_webhook_secret: str = Header(None)):
    _auth(x_webhook_secret)
    if d.decision not in ("accepted", "edited", "rejected") or not KEY_RE.match(d.issue_key):
        raise HTTPException(400, "invalid request")
    import time
    with jobqueue.db() as c:
        c.execute("INSERT INTO decisions VALUES(?,?,?)", (time.time(), d.issue_key, d.decision))
    return {"ok": True}

@app.get("/health")
def health(): return {"ok": True}