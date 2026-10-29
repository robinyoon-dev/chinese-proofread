#!/usr/bin/env python3
"""Run the proofreading quality eval (TODO 6-3) with `claude plugin eval`.

`claude plugin eval` only reads cases from inside the plugin directory, and
anything there would be installed along with the plugin. So this script copies
the plugin to a temporary directory, writes the cases from cases.py into the
copy, and runs the eval on the copy. Results land in results/, which is not
committed; record the numbers in docs/eval-results.md instead.

Bash cannot be granted on machines where ~/.docker holds a symbolic link
(docs/eval-6-3-pilot.md), so the cases only need Read, Edit and Write.

Usage:
  python3 evals/quality/run_eval.py                        # sonnet, 1 run each
  python3 evals/quality/run_eval.py --model opus --runs 3
  python3 evals/quality/run_eval.py --case 'fix-*'
  python3 evals/quality/run_eval.py -- --max-cost-usd 10   # extra eval flags
  python3 evals/quality/run_eval.py --summary results/<run>/result.json
"""

import argparse
import datetime
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PLUGIN = os.path.join(ROOT, "plugins", "chinese-proofread")
RESULTS = os.path.join(HERE, "results")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PLUGIN, "hooks"))

from cases import CASES  # noqa: E402
from detect_chinese import is_chinese  # noqa: E402

ALLOWED_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Skill"]
TONE_MARKS = "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ"
BLOCK = "📝 中文校对"
FILE_END = "__EVAL_FILE_END__"

# Metric prefixes of grader names, in report order.
METRICS = {
    "format": "형식 준수",
    "overfix": "과잉 교정 없음",
    "work": "작업 계속 수행",
    "pinyin": "병음 형식",
    "punct": "문장부호 설명 없음 (9-1)",
    "paste": "붙여 넣은 부분 교정 안 함",
    "substitute": "대신 쓴 단어 알려 줌",
    "keep": "영어 그대로 둠 (9-4)",
    "tone": "구어체 유지",
    "ask": "먼저 확인",
    "skip": "교정 블록 생략",
    "diag": "진단용 (점수 해석에만 사용)",
}


def regex(name, pattern, match="contains", flags="", target=None):
    grader = {"name": name, "type": "regex", "pattern": pattern, "flags": flags,
              "match": match}
    if target:
        grader["target"] = target
    return grader


BLOCK_FIRST = regex("format-block-first", r"^\s*📝 中文校对\s*\n")
OK_FIRST = regex("format-ok-first", r"^\s*📝 中文校对: ✅ 자연스럽습니다\.")
NO_ORIGINAL = regex("overfix-no-original", r"^原文:", "not_contains", "m")
PINYIN_NOT_NUMERIC = regex(
    "pinyin-not-numeric", r"\([a-zü]+[1-5](?: [a-zü]+[1-5])*\)", "not_contains")
DIAG = [
    {"name": "diag-skill-used", "type": "tool_used", "tool": "Skill",
     "input_match": r'"skill"\s*:\s*"(?:[\w-]+:)?proofread"', "min": 1},
    # The block in any text block, not only the final one. A block that only
    # shows up here was printed before the work instead of in the final reply.
    # The trace is JSON, so a leading newline appears as the two characters \n.
    regex("diag-block-in-text", r'"text":\s*"(?:\\n|\s)*📝 中文校对',
          target="trace"),
]

KIND_GRADERS = {
    "fix": [
        BLOCK_FIRST,
        regex("format-original", r"^原文: ?\S", flags="m"),
        regex("format-fixed", r"^修正: ?\S", flags="m"),
        regex("format-explain", r"^설명:", flags="m"),
        # -{3}, not ---: eval reads a literal --- as the end of the frontmatter.
        regex("format-end", r"^-{3}\s*$", flags="m"),
        regex("pinyin-present", f"[{TONE_MARKS}]"),
        PINYIN_NOT_NUMERIC,
        regex("pinyin-not-on-lines", f"^(原文|修正):.*[{TONE_MARKS}]",
              "not_contains", "m"),
    ] + DIAG,
    "ok": [
        OK_FIRST,
        NO_ORIGINAL,
        regex("overfix-no-note", r"✅ 자연스럽습니다\.[^\n]*\n[ \t]*- ",
              "not_contains"),
    ] + DIAG,
    "note": [OK_FIRST, NO_ORIGINAL, PINYIN_NOT_NUMERIC] + DIAG,
    "ask": [regex("format-block-first", r"^\s*📝 中文校对")] + DIAG,
    "none": [
        regex("skip-no-block", r"📝|中文校对", "not_contains"),
        regex("skip-no-mention", r"교정|校对|proofread", "not_contains", "i"),
    ],
}


def yaml_value(value, indent):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    if isinstance(value, dict):
        pad = "  " * (indent + 1)
        return "".join(f"\n{pad}{k}: {yaml_value(v, indent + 1)}"
                       for k, v in value.items())
    return "'" + str(value).replace("'", "''") + "'"


def frontmatter(fields):
    lines = [f"{k}: {yaml_value(v, 0)}" for k, v in fields.items()]
    return "---\n" + "\n".join(lines) + "\n---\n"


def write_case(case, evals_dir):
    case_dir = os.path.join(evals_dir, case["name"])
    graders_dir = os.path.join(case_dir, "graders")
    os.makedirs(graders_dir)

    meta = {"name": case["name"], "tags": [case["kind"]], "max_turns": 10,
            "allowed_tools": ALLOWED_TOOLS}
    with open(os.path.join(case_dir, "prompt.md"), "w", encoding="utf-8") as f:
        f.write(frontmatter(meta) + case["prompt"] + "\n")

    graders = KIND_GRADERS[case["kind"]] + case["graders"]
    names = [g["name"] for g in graders]
    for grader in graders:
        # Two graders of one metric in a case need distinct file names.
        name = grader["name"]
        if names.count(name) > 1:
            name = f"{name}-{names[:graders.index(grader)].count(name) + 1}"
        fields = {k: v for k, v in grader.items() if k != "name" and v != ""}
        with open(os.path.join(graders_dir, f"{name}.md"), "w",
                  encoding="utf-8") as f:
            f.write(frontmatter(fields))

    if case["files"]:
        script = ["#!/bin/bash", "set -e"]
        for path, content in case["files"].items():
            script += [f"cat > '{path}' <<'{FILE_END}'", content.rstrip("\n"),
                       FILE_END]
        with open(os.path.join(case_dir, "scaffold.sh"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(script) + "\n")
        os.chmod(os.path.join(case_dir, "scaffold.sh"), 0o755)
        with open(os.path.join(case_dir, "case.yaml"), "w",
                  encoding="utf-8") as f:
            f.write('schema_version: "1.1"\n'
                    f"name: {case['name']}\n"
                    "context:\n  scaffold_script: scaffold.sh\n")


def check_cases(cases):
    # The hook has to fire for every case except plain English or Korean
    # prompts; a case it never reaches would only measure the hook.
    ok = True
    for case in cases:
        if not is_chinese(case["prompt"]):
            print(f"warning: the hook does not fire for {case['name']}",
                  file=sys.stderr)
            ok = False
    return ok


def metric_of(grader_name):
    return grader_name.split("-", 1)[0]


def reply_texts(trace_path):
    # Every text block the model wrote, in order. Text before or between tool
    # calls is shown to the user as well, so the block counts wherever it is.
    texts = []
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") != "assistant":
                continue
            texts += [block["text"] for block in event["message"]["content"]
                      if block.get("type") == "text"]
    return "\n\n".join(texts)


def regrade(config, text):
    flags = 0
    for ch in config.get("flags") or "":
        flags |= {"m": re.MULTILINE, "i": re.IGNORECASE, "s": re.DOTALL}[ch]
    found = re.search(config["pattern"], text, flags) is not None
    return found if config["match"] == "contains" else not found


def summarize(result_path):
    # Graders on the reply are scored again on all text blocks (the main
    # number); eval's own verdict on the final message is kept alongside.
    #
    # A grader that checks something is absent from the block (no pinyin on
    # the 原文 line, no punctuation note, ...) passes trivially when there is
    # no block, so a run without a block is left out of its count. none cases
    # are the exception: having no block is what they check.
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)
    traces = os.path.join(os.path.dirname(result_path), "traces")
    kinds = {c["name"]: c["kind"] for c in CASES}

    columns = {"any": defaultdict(lambda: [0, 0, 0]),
               "final": defaultdict(lambda: [0, 0, 0])}
    failures = []
    cost = 0.0
    runs = 0
    for case in result["cases"]:
        configs = {g["name"]: g for g in case["graders"]}
        kind = kinds.get(case["name"], metric_of(case["name"]))
        for i, run in enumerate(case["arms"]["with"], 1):
            runs += 1
            cost += run.get("costUsd", 0) + run.get("judgeCostUsd", 0)
            if run.get("error"):
                failures.append(f"{case['name']}: error: {run['error']}")
                continue
            trace = os.path.join(traces, f"{case['name']}-{i}.jsonl")
            have_trace = os.path.exists(trace)
            shown = {"any": reply_texts(trace) if have_trace else None,
                     "final": final_reply(trace) if have_trace else None}
            for grader in run["graders"]:
                metric = metric_of(grader["name"])
                config = configs[grader["name"]]
                on_reply = (config["type"] == "regex" and
                            config["config"].get("target", "last_message")
                            == "last_message")
                needs_block = (on_reply and kind != "none" and
                               config["config"]["match"] == "not_contains")
                verdicts = {"any": grader["passed"], "final": grader["passed"]}
                if on_reply and shown["any"] is not None:
                    verdicts["any"] = regrade(config["config"], shown["any"])
                for column, counts in columns.items():
                    text = shown[column]
                    if needs_block and text is not None and BLOCK not in text:
                        counts[metric][2] += 1
                        continue
                    counts[metric][1] += 1
                    counts[metric][0] += verdicts[column]
                    if column == "any" and not verdicts[column]:
                        reason = ("not met in any text block" if on_reply
                                  else grader["explanation"])
                        failures.append(
                            f"{case['name']}: {grader['name']}: {reason}")

    suite = result["suite"]
    print(f"model {suite.get('modelOverride')}  cases {len(result['cases'])}  "
          f"runs {runs}  cost ${cost:.2f}")
    print(f"  {'':<24} {'all text blocks':<32} final message only")
    for metric, label in METRICS.items():
        if metric not in columns["any"]:
            continue
        cells = []
        for column in ("any", "final"):
            passed, total, skipped = columns[column][metric]
            cell = f"{passed / total:.3f} ({passed}/{total}" if total else "- (0/0"
            cells.append(cell + (f", {skipped} no block)" if skipped else ")"))
        print(f"  {label:<24} {cells[0]:<32} {cells[1]}")
    if failures:
        print("\nfailed graders (all text blocks):")
        for line in failures:
            print(f"  {line}")


def final_reply(trace_path):
    reply = ""
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") == "result":
                reply = event.get("result") or reply
    return reply


def save_traces(result_path, out):
    # The result has no reply text, and eval deletes its workspaces unless
    # --keep-temp is set, so keep each trace and the final reply next to it.
    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)
    traces = os.path.join(out, "traces")
    os.makedirs(traces, exist_ok=True)
    replies = []
    for case in result["cases"]:
        for i, run in enumerate(case["arms"]["with"], 1):
            trace = run.get("tracePath")
            if not trace or not os.path.exists(trace):
                continue
            shutil.copy(trace, os.path.join(traces, f"{case['name']}-{i}.jsonl"))
            replies.append(f"## {case['name']} ({i})\n\n```\n"
                           f"{final_reply(trace)}\n```\n")
            remove_workspace(os.path.dirname(os.path.dirname(trace)))
    with open(os.path.join(out, "replies.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(replies))


def remove_workspace(path):
    # A kept workspace is read-only with a sealed mode-000 directory inside.
    if not os.path.basename(path).startswith("claude-eval-"):
        return
    for root, dirs, _ in os.walk(path):
        os.chmod(root, 0o700)
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o700)
    shutil.rmtree(path, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--case", help="only cases whose name matches this glob")
    parser.add_argument("--keep", action="store_true",
                        help="keep the temporary plugin copy")
    parser.add_argument("--summary", metavar="RESULT_JSON",
                        help="only summarize an earlier result.json")
    parser.add_argument("extra", nargs="*",
                        help="flags passed to claude plugin eval after --")
    args = parser.parse_args()

    if args.summary:
        summarize(args.summary)
        return

    cases = [c for c in CASES
             if not args.case or fnmatch.fnmatch(c["name"], args.case)]
    if not cases:
        sys.exit(f"no case matches {args.case}")
    check_cases(cases)

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(RESULTS, f"{stamp}-{args.model}")
    os.makedirs(out)
    tmp = tempfile.mkdtemp(prefix="chinese-proofread-eval-")
    copy = os.path.join(tmp, "chinese-proofread")
    try:
        shutil.copytree(PLUGIN, copy,
                        ignore=shutil.ignore_patterns("__pycache__", "evals"))
        for case in cases:
            write_case(case, os.path.join(copy, "evals"))

        result_path = os.path.join(out, "result.json")
        cmd = ["claude", "plugin", "eval", copy,
               "--model", args.model, "--runs", str(args.runs),
               "--ablation", "none", "--scaffold",
               "--allow-tools", "Edit", "Write",
               "--trust-plugin", "--no-publish", "--keep-temp",
               "--output-dir", out, "--json", result_path] + args.extra
        print(" ".join(cmd), file=sys.stderr)
        subprocess.run(cmd, check=False)
        if os.path.exists(result_path):
            save_traces(result_path, out)
            summarize(result_path)
    finally:
        if args.keep:
            print(f"kept {tmp}", file=sys.stderr)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
