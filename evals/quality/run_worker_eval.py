#!/usr/bin/env python3
"""Score the proofreading process itself, apart from the work (#18).

Each case's prompt goes to the same claude -p that proofread_worker.py starts,
and the regex graders of run_eval.py check its output. Graders of the work do
not apply here; run_eval.py scores those.
Output is scored as parse_output() sees it: nothing to proofread is empty text,
and anything it refuses is counted as invalid.

Results land in results/, which is not committed.

Usage:
  python3 evals/quality/run_worker_eval.py                  # sonnet, 1 run each
  python3 evals/quality/run_worker_eval.py --model haiku --runs 3
  python3 evals/quality/run_worker_eval.py --case 'fix-*'
  python3 evals/quality/run_worker_eval.py --level advanced --runs 3
  python3 evals/quality/run_worker_eval.py --summary results/<run>/worker.json
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from cases import LEVEL_CASES, at_level
from run_eval import CASES, KIND_GRADERS, METRICS, RESULTS, metric_of, regrade

from jobs import (BLOCK, DEFAULT_LEVEL, INTERNAL_ENV, LEVELS,  # noqa: E402
                  WORKER_TIMEOUT)
from proofread_worker import MODEL, command, message, parse_output  # noqa: E402

SKIPPED_METRICS = {"work", "ask"}
LANG = "Korean"
WORKERS = 4
EXPLANATION = re.compile(r"^- (.+)$", re.M)


def graders_of(case):
    return [g for g in KIND_GRADERS[case["kind"]] + case["graders"]
            if metric_of(g["name"]) not in SKIPPED_METRICS
            and g.get("type") == "regex" and "target" not in g]


def cases_at(level):
    return [c for c in (at_level(c, level) for c in CASES + LEVEL_CASES) if c]


def run_once(case, model, run, level):
    record = {"case": case["name"], "kind": case["kind"], "run": run}
    started = time.time()
    with tempfile.TemporaryDirectory() as cwd:
        try:
            result = subprocess.run(
                command(LANG, model, level) + ["--output-format", "json"],
                input=message(case["prompt"]), capture_output=True, text=True,
                encoding="utf-8", timeout=WORKER_TIMEOUT, cwd=cwd,
                env=dict(os.environ, **{INTERNAL_ENV: "1"}),
            )
        except subprocess.TimeoutExpired:
            return dict(record, status="timeout", seconds=WORKER_TIMEOUT)
    record["seconds"] = time.time() - started
    try:
        reply = json.loads(result.stdout)
    except ValueError:
        return dict(record, status="error", output=result.stdout + result.stderr)
    record["cost"] = reply.get("total_cost_usd", 0)
    record["output"] = reply.get("result") or ""
    if result.returncode != 0 or reply.get("is_error"):
        return dict(record, status="error")
    try:
        block = parse_output(record["output"])
    except RuntimeError:
        return dict(record, status="invalid")
    return dict(record, status="ok", text=block or "")


def summarize(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    level = data.get("level", DEFAULT_LEVEL)
    cases = {c["name"]: c for c in cases_at(level)}
    counts = defaultdict(lambda: [0, 0, 0])
    failures = []
    # How long the explanations are, to compare levels.
    explanations = []
    for record in data["records"]:
        case = cases.get(record["case"])
        if case is None:
            continue
        if record["status"] != "ok":
            failures.append(f"{record['case']}: {record['status']}: "
                            f"{record.get('output', '')[:80]!r}")
            continue
        text = record["text"]
        if case["kind"] == "fix":
            explanations.append(EXPLANATION.findall(text))
        for grader in graders_of(case):
            metric = metric_of(grader["name"])
            if (case["kind"] != "none" and grader["match"] == "not_contains"
                    and BLOCK not in text):
                counts[metric][2] += 1
                continue
            passed = regrade(grader, text)
            counts[metric][1] += 1
            counts[metric][0] += passed
            if not passed:
                failures.append(f"{record['case']} ({record['run']}): "
                                f"{grader['name']}")

    records = data["records"]
    statuses = defaultdict(int)
    for record in records:
        statuses[record["status"]] += 1
    timed = sorted(r["seconds"] for r in records)
    costs = [r["cost"] for r in records if "cost" in r]
    print(f"model {data['model']}  level {level}  calls {len(records)}  "
          f"{dict(statuses)}  total ${sum(costs):.3f}  "
          f"per call ${statistics.mean(costs):.5f}")
    print(f"  seconds: median {statistics.median(timed):.1f}  "
          f"p95 {timed[int(len(timed) * 0.95) - 1]:.1f}  max {timed[-1]:.1f}")
    for metric, label in METRICS.items():
        if metric not in counts:
            continue
        passed, total, skipped = counts[metric]
        note = f", {skipped} no block" if skipped else ""
        print(f"  {label:<24} {passed / total:.3f} ({passed}/{total}{note})")
    lines = [line for block in explanations for line in block]
    if lines:
        print(f"  explanations in fix cases: "
              f"{len(lines) / len(explanations):.2f} lines per block, "
              f"{statistics.mean(len(line) for line in lines):.0f} chars per line")
    if failures:
        print("\nfailed:")
        for line in failures:
            print(f"  {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--level", choices=LEVELS, default=DEFAULT_LEVEL)
    parser.add_argument("--case", help="only cases whose name matches this glob")
    parser.add_argument("--summary", metavar="WORKER_JSON",
                        help="only summarize an earlier worker.json")
    args = parser.parse_args()
    if args.summary:
        summarize(args.summary)
        return

    cases = [c for c in cases_at(args.level)
             if not args.case or fnmatch.fnmatch(c["name"], args.case)]
    if not cases:
        sys.exit(f"no case matches {args.case}")
    jobs = [(c, args.model, run, args.level) for c in cases
            for run in range(1, args.runs + 1)]
    with ThreadPoolExecutor(WORKERS) as pool:
        records = list(pool.map(lambda job: run_once(*job), jobs))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-worker-{args.model}"
    if args.level != DEFAULT_LEVEL:
        name += "-" + args.level
    out = os.path.join(RESULTS, name)
    os.makedirs(out)
    path = os.path.join(out, "worker.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "level": args.level,
                   "records": records}, f,
                  ensure_ascii=False, indent=1)
    summarize(path)
    print(f"\n{path}")


if __name__ == "__main__":
    main()
