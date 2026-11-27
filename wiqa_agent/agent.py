"""Headless ADK worker. No chat, no LLM tool-routing: a fixed pipeline hosted as an agent.
Input message: JSON {"issue_key": "KAN-5", "mode": "review" | "tests"}
Output: JSON status from worker.process_issue.
"""
import asyncio, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types
from worker import process_issue


class WorkItemWorker(BaseAgent):
    async def _run_async_impl(self, ctx):
        try:
            req = json.loads(ctx.user_content.parts[0].text)
            if req.get("mode") not in ("review", "tests") or not req.get("issue_key"):
                res = {"status": "refused", "reason": "need issue_key and mode (review|tests)"}
            else:
                res = await asyncio.to_thread(process_issue, req["issue_key"], req["mode"])
        except Exception as e:
            res = {"status": "error", "reason": str(e)[:300]}
        yield Event(author=self.name,
                    content=types.Content(role="model", parts=[types.Part(text=json.dumps(res))]))


root_agent = WorkItemWorker(name="wiqa_worker",
                            description="Headless Jira work-item reviewer. Comment-only, draft-only.")