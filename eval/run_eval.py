"""Run the golden set under both AI conditions, N runs per item.
Reports per-run and majority-vote accuracy, agreement, LLM-only vs rules-adjusted
category, and tokens. Saves raw results to eval/results/.

Usage: python eval/run_eval.py --runs 5 [--dir golden|holdout|smoke]
(Manual baseline is measured by hand. Gap-detection scoring: add later.)"""
import argparse, json, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from assess import assess, load_config

def majority(cats: list[str]) -> str:
    return Counter(cats).most_common(1)[0][0]

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--only", type=int, nargs="*", help="only run these work item ids (e.g. --only 303)")
    ap.add_argument("--dir", default="golden", help="golden (dev set), holdout (final numbers), or smoke")
    args = ap.parse_args()

    cfg = load_config()
    items = [json.loads(p.read_text()) for p in sorted((ROOT / "eval" / args.dir).glob("*.json"))]
    if args.only:
        items = [i for i in items if i["id"] in args.only]
    out = {"set": args.dir, "model": cfg["model"], "rubric_version": cfg["rubric_version"], "runs": args.runs,
           "top_k": cfg["top_k"], "ts": time.time(), "conditions": {}}

    for use_kb in (False, True):
        name = "with_kb" if use_kb else "no_kb"
        rows, tin, tout, n_calls = [], 0, 0, 0
        for it in items:
            want = it["_answer"]["category"]
            final, raw, outputs = [], [], []
            for _ in range(args.runs):
                try:
                    res, u, raw_cat = assess(it, cfg, use_kb=use_kb)
                    final.append(res["category"]); raw.append(raw_cat); outputs.append(res)
                    tin += u["inputTokens"]; tout += u["outputTokens"]
                except RuntimeError as e:      # malformed output after retries
                    final.append("ERROR"); raw.append("ERROR")
                    print(f"    ERROR id={it['id']}: {e}")
                n_calls += 1
            maj_f, maj_r = majority(final), majority(raw)
            rows.append({"id": it["id"], "want": want, "final": final, "llm_only": raw,
                         "outputs": outputs, "majority_final": maj_f, "majority_llm_only": maj_r,
                         "agreement": final.count(maj_f) / len(final)})
            print(f"  [{name}] id={it['id']} want={want!r} majority={maj_f!r} "
                  f"llm_only={maj_r!r} agreement={rows[-1]['agreement']:.0%} runs={final}")

        n = len(rows)
        per_run = sum(c == r["want"] for r in rows for c in r["final"]) / (n * args.runs)
        per_run_llm = sum(c == r["want"] for r in rows for c in r["llm_only"]) / (n * args.runs)
        summary = {
            "majority_accuracy": sum(r["majority_final"] == r["want"] for r in rows) / n,
            "majority_accuracy_llm_only": sum(r["majority_llm_only"] == r["want"] for r in rows) / n,
            "per_run_accuracy": per_run, "per_run_accuracy_llm_only": per_run_llm,
            "mean_agreement": sum(r["agreement"] for r in rows) / n,
            "avg_input_tokens_per_call": tin / n_calls, "avg_output_tokens_per_call": tout / n_calls,
        }
        out["conditions"][name] = {"summary": summary, "items": rows}
        print(f"[{name}] " + "  ".join(f"{k}={v:.2f}" for k, v in summary.items()) + "\n")

    (ROOT / "eval" / "results").mkdir(exist_ok=True)
    path = ROOT / "eval" / "results" / f"run_{int(out['ts'])}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"saved {path}")

if __name__ == "__main__":
    main()
