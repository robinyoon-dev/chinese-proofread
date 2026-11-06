#!/usr/bin/env python3
"""Score the proofreading process itself, apart from the work (#18).

Each case's prompt goes to the same claude -p that proofread_worker.py starts,
and the regex graders of run_eval.py check its output. Graders of the work do
not apply here; run_eval.py scores those.
Output is scored as parse_output() sees it: nothing to proofread is empty text,
and anything it refuses is counted as invalid.

--lang sets the explanation language (#34). Graders that look for Korean are
swapped for English ones (ENGLISH_GRADERS in run_eval.py), and the output is
scored after fit_language(), as the user sees it.

--learner runs only the cases of errors English speakers often make
(LEARNER_CASES), so the main numbers keep their denominators.

Results land in results/, which is not committed.

Usage:
  python3 evals/quality/run_worker_eval.py                  # sonnet, 1 run each
  python3 evals/quality/run_worker_eval.py --model haiku --runs 3
  python3 evals/quality/run_worker_eval.py --case 'fix-*'
  python3 evals/quality/run_worker_eval.py --level advanced --runs 3
  python3 evals/quality/run_worker_eval.py --region taiwan --runs 3
  python3 evals/quality/run_worker_eval.py --lang english --runs 3
  python3 evals/quality/run_worker_eval.py --learner --lang english --runs 3
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

from cases import LEARNER_CASES, LEVEL_CASES, REGION_CASES, at_level
from run_eval import (CASES, KIND_GRADERS, METRICS, RESULTS, in_language,
                      metric_of, regrade)

from jobs import (BLOCK, DEFAULT_LEVEL, DEFAULT_REGION,  # noqa: E402
                  INTERNAL_ENV, LEVELS, REGIONS, WORKER_TIMEOUT)
from proofread_worker import (MODEL, command, fit_language,  # noqa: E402
                              message, parse_output)

SKIPPED_METRICS = {"work", "ask"}
LANGS = ("korean", "english")
DEFAULT_LANG = "korean"
WORKERS = 4
EXPLANATION = re.compile(r"^- (.+)$", re.M)


def graders_of(case, lang=DEFAULT_LANG):
    graders = in_language(KIND_GRADERS[case["kind"]] + case["graders"], lang)
    return [g for g in graders
            if metric_of(g["name"]) not in SKIPPED_METRICS
            and g["name"] not in case.get("without", ())
            and g.get("type") == "regex" and "target" not in g]


def cases_at(level, region=DEFAULT_REGION, learner=False):
    # The main cases are in simplified characters, which taiwan corrects.
    if learner:
        base = LEARNER_CASES
    elif region == "taiwan":
        base = REGION_CASES
    else:
        base = CASES + LEVEL_CASES
    return [c for c in (at_level(c, level) for c in base) if c]


def run_once(case, model, run, level, region, lang):
    record = {"case": case["name"], "kind": case["kind"], "run": run}
    started = time.time()
    with tempfile.TemporaryDirectory() as cwd:
        try:
            result = subprocess.run(
                command(lang.capitalize(), model, level, region)
                + ["--output-format", "json"],
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
        block = fit_language(parse_output(record["output"]), lang)
    except RuntimeError:
        return dict(record, status="invalid")
    return dict(record, status="ok", text=block or "")


def summarize(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    level = data.get("level", DEFAULT_LEVEL)
    region = data.get("region", DEFAULT_REGION)
    lang = data.get("lang", DEFAULT_LANG)
    learner = data.get("learner", False)
    cases = {c["name"]: c for c in cases_at(level, region, learner)}
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
        for grader in graders_of(case, lang):
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
    print(f"model {data['model']}  level {level}  region {region}  "
          f"lang {lang}{'  learner' if learner else ''}  "
          f"calls {len(records)}  "
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
    parser.add_argument("--region", choices=REGIONS, default=DEFAULT_REGION)
    parser.add_argument("--lang", choices=LANGS, default=DEFAULT_LANG,
                        type=str.lower)
    parser.add_argument("--learner", action="store_true",
                        help="run only the English speakers' error cases")
    parser.add_argument("--case", help="only cases whose name matches this glob")
    parser.add_argument("--summary", metavar="WORKER_JSON",
                        help="only summarize an earlier worker.json")
    args = parser.parse_args()
    if args.summary:
        summarize(args.summary)
        return

    if args.learner and args.region == "taiwan":
        sys.exit("the learner cases are in simplified characters")
    cases = [c for c in cases_at(args.level, args.region, args.learner)
             if not args.case or fnmatch.fnmatch(c["name"], args.case)]
    if not cases:
        sys.exit(f"no case matches {args.case}")
    jobs = [(c, args.model, run, args.level, args.region, args.lang)
            for c in cases
            for run in range(1, args.runs + 1)]
    with ThreadPoolExecutor(WORKERS) as pool:
        records = list(pool.map(lambda job: run_once(*job), jobs))

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-worker-{args.model}"
    if args.level != DEFAULT_LEVEL:
        name += "-" + args.level
    if args.region != DEFAULT_REGION:
        name += "-" + args.region
    if args.lang != DEFAULT_LANG:
        name += "-" + args.lang
    if args.learner:
        name += "-learner"
    out = os.path.join(RESULTS, name)
    os.makedirs(out)
    path = os.path.join(out, "worker.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"model": args.model, "level": args.level,
                   "region": args.region, "lang": args.lang,
                   "learner": args.learner, "records": records}, f,
                  ensure_ascii=False, indent=1)
    summarize(path)
    print(f"\n{path}")


if __name__ == "__main__":
    main()
