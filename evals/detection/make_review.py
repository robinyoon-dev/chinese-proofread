#!/usr/bin/env python3
"""Build review.html, a page for reviewing the labels in dataset.jsonl.

The page embeds the dataset, so it opens from the file system without a
server. Review notes are kept in the browser's localStorage and can be
copied as text with the button at the top of the page.

Usage:
  python3 evals/detection/make_review.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(HERE, "dataset.jsonl")
OUTPUT = os.path.join(HERE, "review.html")

PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>판별 데이터셋 검토</title>
<style>
:root {
  --bg: #f7f8fa; --panel: #ffffff; --fg: #1d2330; --muted: #667085;
  --line: #dde1e8; --true: #1f7a4d; --true-bg: #e3f4ea;
  --false: #a23b3b; --false-bg: #f8e6e6; --flag: #b7791f; --flag-bg: #fdf3dc;
  --code-bg: #f1f3f6;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171d; --panel: #1c2028; --fg: #e6e9ef; --muted: #98a2b3;
    --line: #2e3440; --true: #6fd3a0; --true-bg: #1d3a2c;
    --false: #f09a9a; --false-bg: #402424; --flag: #f2c46d; --flag-bg: #3d321b;
    --code-bg: #232833; color-scheme: dark;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
}
header {
  position: sticky; top: 0; z-index: 1; background: var(--panel);
  border-bottom: 1px solid var(--line); padding: 12px 16px;
  display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center;
}
header h1 { font-size: 16px; margin: 0; }
header .stats { color: var(--muted); font-variant-numeric: tabular-nums; }
header .controls { display: flex; flex-wrap: wrap; gap: 8px; margin-left: auto; }
select, button, input[type=search] {
  font: inherit; color: var(--fg); background: var(--panel);
  border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px;
}
button { cursor: pointer; }
button:focus-visible, select:focus-visible, input:focus-visible, textarea:focus-visible {
  outline: 2px solid var(--flag); outline-offset: 1px;
}
main { max-width: 1100px; margin: 0 auto; padding: 16px; display: grid; gap: 24px; }
section h2 { font-size: 15px; margin: 0 0 8px; display: flex; gap: 8px; align-items: baseline; }
section h2 .count { color: var(--muted); font-weight: normal; font-size: 13px; }
table { width: 100%; border-collapse: collapse; background: var(--panel);
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-top: 1px solid var(--line); }
th { font-size: 12px; color: var(--muted); font-weight: 600; border-top: none; }
td.id { color: var(--muted); font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.prompt pre {
  margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 15px;
  font-family: inherit; background: var(--code-bg); padding: 6px 8px; border-radius: 4px;
}
/* Pick CJK fonts by the prompt's language so simplified and traditional
   hanzi each render with their own glyph shapes. */
td.prompt pre:lang(zh-Hans), td.prompt pre:lang(en) {
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Noto Sans SC",
    "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}
td.prompt pre:lang(zh-Hant) {
  font-family: "Microsoft JhengHei", "PingFang TC", "Noto Sans CJK TC", "Noto Sans TC",
    "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}
td.prompt pre:lang(ko) {
  font-family: "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR",
    "Microsoft YaHei", "PingFang SC", sans-serif;
}
td.note { color: var(--muted); font-size: 13px; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.badge.true { color: var(--true); background: var(--true-bg); }
.badge.false { color: var(--false); background: var(--false-bg); }
.badge.usage { color: var(--fg); border: 1px solid var(--line); }
.badge.split { color: var(--muted); border: 1px solid var(--line); font-weight: normal; }
tr.flagged td { background: var(--flag-bg); }
td.review { width: 220px; }
td.review label { display: flex; gap: 6px; align-items: center; font-size: 13px; }
td.review textarea {
  width: 100%; margin-top: 4px; font: inherit; font-size: 13px; color: var(--fg);
  background: var(--panel); border: 1px solid var(--line); border-radius: 4px;
  min-height: 2.2em; resize: vertical;
}
.table-wrap { overflow-x: auto; }
.toast { color: var(--true); font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>판별 데이터셋 검토</h1>
  <span class="stats" id="stats"></span>
  <div class="controls">
    <input type="search" id="q" placeholder="문장 검색">
    <select id="usage"><option value="">usage 전체</option><option value="sentence">sentence</option><option value="word">word</option><option value="reply">reply</option><option value="quoted">quoted</option><option value="none">none</option></select>
    <select id="split"><option value="">세트 전체</option><option value="dev">조정용(dev)</option><option value="test">확인용(test)</option></select>
    <select id="flagged"><option value="">표시 전체</option><option value="1">검토 표시한 문장만</option></select>
    <button id="copy">검토 결과 복사</button>
    <span class="toast" id="toast"></span>
  </div>
</header>
<main id="main"></main>
<script>
const ROWS = __DATA__;
const KEY = "chinese-proofread-review";
// Labels derived from usage: the current rule proofreads only sentences;
// the word rule also proofreads Chinese words mixed into other languages.
const USAGE = {
  sentence: {desc: "직접 쓴 중국어 문장", current: true, word: true},
  word: {desc: "다른 언어 문장에 섞어 쓴 중국어 단어", current: false, word: true},
  reply: {desc: "짧은 중국어 대답", current: false, word: false},
  quoted: {desc: "인용하거나 붙여 넣은 중국어", current: false, word: false},
  none: {desc: "중국어 없음", current: false, word: false},
};
let review = {};
try { review = JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) {}
function save() { try { localStorage.setItem(KEY, JSON.stringify(review)); } catch (e) {} }

const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function lang(cat) {
  if (cat === "zh_traditional") return "zh-Hant";
  if (cat.startsWith("zh_")) return "zh-Hans";
  if (cat.startsWith("ko_")) return "ko";
  return "en";
}

function render() {
  const q = $("q").value.trim(), usage = $("usage").value, split = $("split").value, flagged = $("flagged").value;
  const rows = ROWS.filter(r =>
    (!q || r.prompt.includes(q) || r.id.includes(q) || r.note.includes(q)) &&
    (!usage || r.usage === usage) &&
    (!split || r.split === split) &&
    (!flagged || (review[r.id] && review[r.id].flag)));
  const groups = new Map();
  for (const r of rows) {
    if (!groups.has(r.category)) groups.set(r.category, []);
    groups.get(r.category).push(r);
  }
  let html = "";
  for (const [cat, items] of groups) {
    html += `<section><h2>${esc(cat)} <span class="count">${items.length}개</span></h2>
      <div class="table-wrap"><table>
      <tr><th>ID</th><th>문장</th><th>usage</th><th>현재 기준</th><th>단어 포함 기준</th><th>메모</th><th>검토</th></tr>`;
    for (const r of items) {
      const rv = review[r.id] || {};
      html += `<tr class="${rv.flag ? "flagged" : ""}" data-id="${esc(r.id)}">
        <td class="id">${esc(r.id)}<br><span class="badge split">${r.split}</span></td>
        <td class="prompt"><pre lang="${lang(r.category)}">${esc(r.prompt)}</pre></td>
        <td><span class="badge usage" title="${USAGE[r.usage].desc}">${r.usage}</span></td>
        <td><span class="badge ${USAGE[r.usage].current}">${USAGE[r.usage].current}</span></td>
        <td><span class="badge ${USAGE[r.usage].word}">${USAGE[r.usage].word}</span></td>
        <td class="note">${esc(r.note)}</td>
        <td class="review"><label><input type="checkbox" id="flag-${esc(r.id)}" ${rv.flag ? "checked" : ""}> 검토 필요</label>
          <textarea id="comment-${esc(r.id)}" placeholder="의견">${esc(rv.comment || "")}</textarea></td></tr>`;
    }
    html += "</table></div></section>";
  }
  $("main").innerHTML = html || "<p>조건에 맞는 문장이 없습니다.</p>";
  const counts = Object.keys(USAGE).map(u => `${u} ${ROWS.filter(r => r.usage === u).length}`).join(" / ");
  const nTest = ROWS.filter(r => r.split === "test").length;
  const nFlag = Object.values(review).filter(v => v.flag).length;
  $("stats").textContent = `전체 ${ROWS.length}개 · ${counts} · 확인용 ${nTest}개 · 표시 ${nFlag}개 · 보이는 문장 ${rows.length}개`;
}

$("main").addEventListener("input", e => {
  const tr = e.target.closest("tr"); if (!tr) return;
  const id = tr.dataset.id, rv = review[id] || (review[id] = {});
  if (e.target.type === "checkbox") { rv.flag = e.target.checked; tr.classList.toggle("flagged", rv.flag); }
  else rv.comment = e.target.value;
  if (!rv.flag && !rv.comment) delete review[id];
  save();
  const nFlag = Object.values(review).filter(v => v.flag).length;
  $("stats").textContent = $("stats").textContent.replace(/표시 \\d+개/, `표시 ${nFlag}개`);
});
for (const id of ["q", "usage", "split", "flagged"]) $(id).addEventListener("input", render);

$("copy").addEventListener("click", async () => {
  const lines = ROWS.filter(r => review[r.id]).map(r => {
    const rv = review[r.id];
    return `- ${r.id} (${r.usage})${rv.flag ? " [검토 필요]" : ""}: ${rv.comment || ""}`.trimEnd();
  });
  const text = lines.length ? lines.join("\\n") : "검토 의견이 없습니다.";
  try { await navigator.clipboard.writeText(text); $("toast").textContent = `${lines.length}개를 복사했습니다.`; }
  catch (e) { $("toast").textContent = "복사하지 못했습니다."; console.log(text); }
});

render();
</script>
</body>
</html>
"""


def main():
    with open(DATASET, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__DATA__", data))
    print(f"Wrote {OUTPUT} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
