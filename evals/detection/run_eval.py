#!/usr/bin/env python3
"""Measure how well is_chinese() decides when the hook should respond.

Labels come from each prompt's usage in dataset.jsonl, under two criteria:
  current  only sentences the user wrote in Chinese
  word     also Chinese words the user mixed into other languages (TODO 9-5)

Settings are picked on the dev split by category rather than by overall false
positive rate, because the dataset holds far more hard negatives than real use
does. A setting must catch every prompt in MUST_CATCH and reject every prompt
in MUST_REJECT. Among those, the defaults change only for a setting that
catches at least as many prompts with no more false positives and is strictly
better on one of the two; any other change trades false positives for recall,
and the sweep lists those trades for a person to judge. Run the test split
only once, after the settings are fixed.

Usage:
  python3 evals/detection/run_eval.py                 # defaults on dev
  python3 evals/detection/run_eval.py --sweep         # compare settings on dev
  python3 evals/detection/run_eval.py --split test    # final check, run once
  python3 evals/detection/run_eval.py --min-hanzi 3 --hanzi-ratio 0.4
"""

import argparse
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "plugins", "chinese-proofread", "hooks"))

from detect_chinese import is_chinese  # noqa: E402

DATASET = os.path.join(HERE, "dataset.jsonl")
DEFAULTS = (4, 1, 0.5)
POSITIVE = {"current": {"sentence"}, "word": {"sentence", "word"}}
# Prompts the hook is designed to catch (design decisions 2 and 10).
MUST_CATCH = {"zh_pure", "zh_traditional", "zh_with_code", "zh_english_substitute"}
# Common prompts that must never get the proofreading instructions.
MUST_REJECT = {"ko_pure", "en_or_code", "zh_short_reply"}


def load(split):
    with open(DATASET, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return [r for r in rows if split == "all" or r["split"] == split]


def predict(rows, settings):
    return [is_chinese(r["prompt"], *settings) for r in rows]


def score(rows, preds, criterion):
    tp = fp = fn = tn = 0
    for r, pred in zip(rows, preds):
        label = r["usage"] in POSITIVE[criterion]
        if label and pred:
            tp += 1
        elif label:
            fn += 1
        elif pred:
            fp += 1
        else:
            tn += 1
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "fpr": fp / (fp + tn) if fp + tn else 0.0,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
    }


def fmt_settings(settings):
    return "min_hanzi={} min_hanzi_mixed={} hanzi_ratio={}".format(*settings)


def fmt_score(s):
    return (f"recall {s['recall']:.3f} ({s['tp']}/{s['tp'] + s['fn']})  "
            f"FPR {s['fpr']:.3f} ({s['fp']}/{s['fp'] + s['tn']})  "
            f"precision {s['precision']:.3f}")


def report(rows, settings):
    preds = predict(rows, settings)
    print(fmt_settings(settings))
    for criterion in POSITIVE:
        s = score(rows, preds, criterion)
        print(f"\n[{criterion}] {fmt_score(s)}")
        print(f"  TP {s['tp']}  FN {s['fn']}  FP {s['fp']}  TN {s['tn']}")

        groups = defaultdict(lambda: [0, 0])
        for r, pred in zip(rows, preds):
            label = r["usage"] in POSITIVE[criterion]
            g = groups[(r["category"], r["usage"], label)]
            g[0] += pred == label
            g[1] += 1
        print("  per category (correct/total):")
        for (cat, usage, label), (ok, total) in sorted(groups.items()):
            mark = "" if ok == total else "  <-"
            print(f"    {cat:24} {usage:9} {str(label):5} {ok:3}/{total:<3}{mark}")

        errors = [(r, pred) for r, pred in zip(rows, preds)
                  if pred != (r["usage"] in POSITIVE[criterion])]
        if errors:
            print("  errors:")
            for r, pred in errors:
                kind = "FP" if pred else "FN"
                prompt = r["prompt"].replace("\n", "\\n")
                print(f"    {kind} {r['id']:26} {prompt[:60]}")


def grid():
    for min_hanzi in range(1, 9):
        for mixed in range(1, min_hanzi + 1):
            # min_hanzi_mixed above min_hanzi has no effect, so skip it.
            for tenths in range(0, 10):
                yield (min_hanzi, mixed, tenths / 10)


def meets_constraints(rows, preds):
    for r, pred in zip(rows, preds):
        if r["category"] in MUST_CATCH and not pred:
            return False
        if r["category"] in MUST_REJECT and pred:
            return False
    return True


def distance(settings):
    return sum(abs(a - b) for a, b in zip(settings, DEFAULTS))


def sweep(rows):
    results = []
    for settings in grid():
        preds = predict(rows, settings)
        if meets_constraints(rows, preds):
            results.append((settings, {c: score(rows, preds, c) for c in POSITIVE}))
    print(f"{len(results)} settings catch every prompt in {sorted(MUST_CATCH)}")
    print(f"and reject every prompt in {sorted(MUST_REJECT)}")

    for criterion in POSITIVE:
        # Keep one setting per (TP, FP) pair, the one closest to the defaults.
        best = {}
        for settings, s in sorted(results, key=lambda i: distance(i[0])):
            best.setdefault((s[criterion]["tp"], s[criterion]["fp"]), (settings, s))
        # Settings no other setting beats on both TP and FP.
        front = [v for (tp, fp), v in best.items()
                 if not any(t >= tp and f <= fp and (t, f) != (tp, fp) for t, f in best)]

        print(f"\n[{criterion}] settings where catching more costs more false positives:")
        for settings, s in sorted(front, key=lambda i: i[1][criterion]["fp"]):
            mark = "  (default)" if settings == DEFAULTS else ""
            print(f"  {fmt_settings(settings):48} {fmt_score(s[criterion])}{mark}")

        default = next((s[criterion] for settings, s in results if settings == DEFAULTS), None)
        if default is None:
            print("  default: does not meet the constraints")
            continue
        print(f"  default: {fmt_score(default)}")
        # Change the defaults only for a setting that is at least as good on
        # both TP and FP and strictly better on one of them.
        better = [(settings, s) for settings, s in results
                  if s[criterion]["tp"] >= default["tp"] and s[criterion]["fp"] <= default["fp"]
                  and (s[criterion]["tp"], s[criterion]["fp"]) != (default["tp"], default["fp"])]
        if better:
            settings, _ = min(better, key=lambda i: (-i[1][criterion]["tp"],
                                                     i[1][criterion]["fp"], distance(i[0])))
            print(f"  pick:    {fmt_settings(settings)} (beats the defaults)")
        else:
            print("  pick:    keep the defaults (no setting beats them on both TP and FP)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--sweep", action="store_true", help="compare settings")
    parser.add_argument("--min-hanzi", type=int, default=DEFAULTS[0])
    parser.add_argument("--min-hanzi-mixed", type=int, default=DEFAULTS[1])
    parser.add_argument("--hanzi-ratio", type=float, default=DEFAULTS[2])
    args = parser.parse_args()

    rows = load(args.split)
    print(f"split={args.split} prompts={len(rows)}")
    if args.split == "test":
        print("note: the test split is for a single final check after settings are fixed")
    if args.sweep:
        sweep(rows)
    else:
        report(rows, (args.min_hanzi, args.min_hanzi_mixed, args.hanzi_ratio))


if __name__ == "__main__":
    main()
