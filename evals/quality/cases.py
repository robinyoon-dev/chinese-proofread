"""Cases for the proofreading quality eval (TODO 6-3, stage 1).

Each case is a prompt, the files its workspace starts with, and the graders
that check the reply. run_eval.py turns these into `claude plugin eval` case
directories in a temporary copy of the plugin, so the plugin directory itself
never holds eval files.

kind decides the format graders every case gets:
  fix   the user's Chinese has an error; expects a 原文 / 修正 block
  ok    natural Chinese; expects only the ✅ line
  note  natural Chinese with English words; expects the ✅ line, with or
        without explanation lines
  ask   the request has two readings; expects a question and no edits
  none  no Chinese sentence of the user's own; expects no block at all

Grader names start with the metric they count toward (see METRICS in
run_eval.py). `expect` records the intended correction for the LLM grader
added in stage 2; stage 1 does not score it.
"""

UTILS = '''\
def average(numbers):
    return sum(numbers) / len(numbers) + 1


def greet(name):
    print("Hello, " + name)
'''

API = '''\
import json


def parse_user(text):
    data = json.loads(text)
    return {"name": data["name"], "age": data["name"]}
'''

SLOW_API = '''\
import time


def get_user(user_id):
    time.sleep(2)
    return {"id": user_id}
'''

README = '''\
# utils

简单的工具函数。
'''

SHORT_VAR_UTILS = '''\
def average(n):
    s = sum(n)
    c = len(n)
    return s / c
'''

FONT_TEST = '''\
CHARS = ["A", "가", "あ"]


def test_chars_render():
    for ch in CHARS:
        assert len(ch) == 1
'''

CHANGES = '''\
- utils.py: average() 去掉了多加的 1
- utils.py: greet() 改成返回字符串
'''


def file_has(path, pattern, name="work-file", flags=""):
    return {"name": name, "type": "regex", "pattern": pattern, "flags": flags,
            "match": "contains", "target": {"source": "file", "path": path}}


def file_lacks(path, pattern, name="work-file", flags=""):
    return {"name": name, "type": "regex", "pattern": pattern, "flags": flags,
            "match": "not_contains", "target": {"source": "file", "path": path}}


def reply_has(pattern, name, flags=""):
    return {"name": name, "type": "regex", "pattern": pattern, "flags": flags,
            "match": "contains"}


def reply_lacks(pattern, name, flags=""):
    return {"name": name, "type": "regex", "pattern": pattern, "flags": flags,
            "match": "not_contains"}


def no_edits():
    return [
        # min defaults to 1, so "never called" needs min 0 as well.
        {"name": "ask-no-edit", "type": "tool_used", "tool": "Edit",
         "min": 0, "max": 0},
        {"name": "ask-no-write", "type": "tool_used", "tool": "Write",
         "min": 0, "max": 0},
        reply_has(r"[?？]", "ask-question"),
    ]


AVERAGE_FIXED = file_lacks("utils.py", r"\+ 1")
GREET_RETURNS = file_has("utils.py", r"def greet[\s\S]*return")
FINDS_PLUS_ONE = reply_has(r"\+ ?1", "work-answer")
# 9-1: a punctuation-only difference must not get its own explanation line.
# Only for ok cases; next to another fix, a punctuation note is fine.
NO_PUNCTUATION_NOTE = reply_lacks(r"마침표|문장부호|쉼표|구두점|전각", "punct-no-note")


def keeps_in_fix(word, name):
    # If there is a 修正 line, it still has the word.
    return reply_lacks(rf"^修正:(?!.*{word}).*$", name, "m")


def not_in_original(text, name="paste-not-proofread"):
    return reply_lacks(rf"^(原文|修正):.*(?:{text})", name, "m")


CASES = [
    # --- fix: errors the proofreading should catch ---
    {
        "name": "fix-ta-for-thing",
        "kind": "fix",
        "prompt": "帮我修改一下utils.py的bug，他让average的结果总是多一",
        "expect": "他 → 它 (사물)",
        "files": {"utils.py": UTILS},
        "graders": [AVERAGE_FIXED],
    },
    {
        "name": "fix-de-complement",
        "kind": "fix",
        "prompt": "帮我把greet函数写得更简洁地，用f-string",
        "expect": "写得更简洁地 → 写得更简洁 (得 보어 뒤 地 불필요)",
        "files": {"utils.py": UTILS},
        "graders": [file_has("utils.py", r"f[\"']Hello")],
    },
    {
        "name": "fix-place-word-order",
        "kind": "fix",
        "prompt": "帮我加一个函数在utils.py的最后，用来求最大值",
        "expect": "加一个函数在utils.py的最后 → 在utils.py的最后加一个函数 (장소 부사어는 동사 앞)",
        "files": {"utils.py": UTILS},
        "graders": [file_has("utils.py", r"max")],
    },
    {
        "name": "fix-shi-before-adjective",
        "kind": "fix",
        "prompt": "average函数的名字是太短了，帮我改成calculate_average",
        "expect": "是太短了 → 太短了 (형용사 술어 앞 是 불필요)",
        "files": {"utils.py": UTILS},
        "graders": [file_has("utils.py", r"def calculate_average")],
    },
    {
        "name": "fix-gei-word-order",
        "kind": "fix",
        "prompt": "帮我写一个测试给average函数，放在test_utils.py里",
        "expect": "写一个测试给average函数 → 给average函数写一个测试 (给 구는 동사 앞)",
        "files": {"utils.py": UTILS},
        "graders": [file_has("test_utils.py", r"average")],
    },
    {
        "name": "fix-le-in-modifier",
        "kind": "fix",
        "prompt": "我昨天写了的代码有问题，你帮我看看utils.py哪里错了",
        "expect": "写了的代码 → 写的代码 (관형어 안의 了 불필요)",
        "files": {"utils.py": UTILS},
        "graders": [FINDS_PLUS_ONE],
    },
    {
        "name": "fix-double-question",
        "kind": "fix",
        "prompt": "请你帮我检查一下utils.py有没有错误吗？",
        "expect": "有没有错误吗 → 有没有错误 (정반의문문에 吗 중복)",
        "files": {"utils.py": UTILS},
        "graders": [FINDS_PLUS_ONE],
    },
    {
        "name": "fix-zai-word-order",
        "kind": "fix",
        "prompt": "帮我把greet里的print改成return，因为我想要用这个结果在别的地方",
        "expect": "用这个结果在别的地方 → 在别的地方用这个结果 (장소 부사어는 동사 앞)",
        "files": {"utils.py": UTILS},
        "graders": [GREET_RETURNS],
    },
    # --- ok: natural sentences, no correction expected ---
    {
        "name": "ok-ask-problem",
        "kind": "ok",
        "prompt": "帮我看看utils.py里的average函数有什么问题。",
        "files": {"utils.py": UTILS},
        "graders": [FINDS_PLUS_ONE],
    },
    {
        "name": "ok-print-to-return",
        "kind": "ok",
        "prompt": "把greet函数里的print改成return。",
        "files": {"utils.py": UTILS},
        "graders": [GREET_RETURNS],
    },
    {
        "name": "ok-complexity",
        "kind": "ok",
        "prompt": "utils.py里average函数的时间复杂度是多少？",
        "files": {"utils.py": UTILS},
        "graders": [reply_has(r"O\(n\)", "work-answer")],
    },
    {
        "name": "ok-add-comment",
        "kind": "ok",
        "prompt": "帮我给average函数加个注释，说明一下参数和返回值。",
        "files": {"utils.py": UTILS},
        "graders": [file_has("utils.py", r"\"\"\"|'''|#")],
    },
    {
        "name": "ok-colloquial",
        "kind": "ok",
        # Not 老多算1: 老多 also reads as "a lot", so correcting it is fair.
        "prompt": "这个函数咋老是多算1啊？帮我瞅瞅呗。utils.py里的average。",
        "files": {"utils.py": UTILS},
        "graders": [FINDS_PLUS_ONE, keeps_in_fix("呗", "tone-keep")],
    },
    {
        "name": "fix-colloquial",
        "kind": "fix",
        "prompt": "哎呀，utils.py里的average又出错了，快帮我把他修好呗。",
        "expect": "他 → 它 (사물), 구어체(哎呀, 呗) 유지",
        "files": {"utils.py": UTILS},
        "graders": [AVERAGE_FIXED, keeps_in_fix("呗", "tone-keep")],
    },
    # --- punctuation-only differences (9-1) ---
    {
        "name": "ok-halfwidth-punctuation",
        "kind": "ok",
        "prompt": "帮我看看utils.py里的average函数有什么问题,顺便把它修好.",
        "files": {"utils.py": UTILS},
        "graders": [AVERAGE_FIXED, NO_PUNCTUATION_NOTE],
    },
    {
        "name": "ok-no-final-punctuation",
        "kind": "ok",
        "prompt": "把greet函数里的print改成return",
        "files": {"utils.py": UTILS},
        "graders": [GREET_RETURNS, NO_PUNCTUATION_NOTE],
    },
    {
        "name": "fix-with-halfwidth-punctuation",
        "kind": "fix",
        "prompt": "帮我修一下utils.py,他算出来的平均值不对.",
        # With another fix in the block, a punctuation note is fine.
        "expect": "他 → 它 (사물). 다른 교정과 함께라면 문장부호 설명은 허용",
        "files": {"utils.py": UTILS},
        "graders": [AVERAGE_FIXED],
    },
    # --- pasted code, logs and errors must not be proofread ---
    {
        "name": "ok-pasted-traceback",
        "kind": "ok",
        "prompt": (
            "这个报错是什么意思？\n\n"
            "```\n"
            "Traceback (most recent call last):\n"
            '  File "main.py", line 3, in <module>\n'
            "    print(average([]))\n"
            "ZeroDivisionError: division by zero\n"
            "```"
        ),
        "files": {},
        "graders": [
            reply_has(r"0으로|빈 (리스트|목록)|len", "work-answer"),
            not_in_original("Traceback|ZeroDivision"),
        ],
    },
    {
        "name": "ok-pasted-chinese-log",
        "kind": "ok",
        "prompt": (
            "帮我看看这个日志是什么问题：\n\n"
            "```\n"
            "[错误] 连接数据库失败了，请你重新再试一下一次\n"
            "```"
        ),
        "files": {},
        "graders": [
            reply_has(r"데이터베이스|DB|연결", "work-answer", "i"),
            not_in_original("连接数据库"),
        ],
    },
    {
        "name": "fix-pasted-chinese-comment",
        "kind": "fix",
        "prompt": (
            "这个代码是做什么的？请解释给我。\n\n"
            "```python\n"
            "# 这个函数是用来计算平均数的的\n"
            "def average(numbers):\n"
            "    return sum(numbers) / len(numbers)\n"
            "```"
        ),
        "expect": "请解释给我 → 请给我解释一下 (给 구는 동사 앞). 코드 주석의 的的는 교정하지 않음",
        "files": {},
        "graders": [
            reply_has(r"평균", "work-answer"),
            not_in_original("平均数的的"),
        ],
    },
    # --- English words used in place of unknown Chinese words ---
    {
        "name": "fix-substitute-installation",
        "kind": "fix",
        "prompt": "帮我在README里加一个installation的部分",
        "expect": "installation → 安装 (README는 유지)",
        "files": {"README.md": README},
        "graders": [
            reply_has(r"安装", "substitute-taught"),
            keeps_in_fix("README", "keep-english"),
            file_has("README.md", r"安装|install", flags="i"),
        ],
    },
    {
        "name": "fix-substitute-variable",
        "kind": "fix",
        "prompt": "帮我把utils.py里的variable名字改得清楚一点",
        "expect": "variable → 变量",
        "files": {"utils.py": SHORT_VAR_UTILS},
        # Models rewrite the whole file with Write as often as they use Edit.
        "graders": [reply_has(r"变量", "substitute-taught"),
                    file_lacks("utils.py", r"^\s+s = ", flags="m")],
    },
    {
        "name": "fix-substitute-edge-case",
        "kind": "fix",
        "prompt": "帮我检查一下utils.py有没有edge case没处理",
        "expect": "edge case → 边界情况",
        "files": {"utils.py": UTILS},
        "graders": [
            reply_has(r"边界|边缘", "substitute-taught"),
            reply_has(r"빈 (리스트|목록)|\[\]|ZeroDivision|0으로", "work-answer"),
        ],
    },
    {
        "name": "fix-substitute-output",
        "kind": "fix",
        "prompt": "帮我把greet函数的output改成中文",
        "expect": "output → 输出",
        "files": {"utils.py": UTILS},
        "graders": [reply_has(r"输出", "substitute-taught"), file_has("utils.py", r"你好")],
    },
    # --- English words Chinese developers keep in English (9-4) ---
    {
        "name": "note-keep-bug",
        "kind": "note",
        "prompt": "帮我fix一下utils.py里的bug",
        "files": {"utils.py": UTILS},
        "graders": [
            AVERAGE_FIXED,
            keeps_in_fix("bug", "keep-english"),
            reply_lacks(r"bug[는은] 중국어로", "keep-english-no-note"),
        ],
    },
    {
        "name": "note-keep-api-json",
        "kind": "note",
        "prompt": "这个API返回的JSON格式不对，帮我看看api.py里的parse_user函数。",
        "files": {"api.py": API},
        "graders": [
            reply_has(r"age", "work-answer"),
            keeps_in_fix("API", "keep-english"),
            reply_lacks(r"(API|JSON)[는은] 중국어로", "keep-english-no-note"),
        ],
    },
    {
        "name": "note-keep-commit",
        "kind": "note",
        "prompt": "根据changes.txt帮我写一个commit message。",
        "files": {"changes.txt": CHANGES},
        "graders": [
            reply_has(r"average", "work-answer"),
            keeps_in_fix("commit", "keep-english"),
        ],
    },
    {
        "name": "note-keep-pr",
        "kind": "note",
        "prompt": "帮我在README里加一条PR的规则：每个PR都要有测试。",
        "files": {"README.md": README},
        "graders": [
            file_has("README.md", r"PR"),
            keeps_in_fix("PR", "keep-english"),
            reply_lacks(r"PR[는은] 중국어로", "keep-english-no-note"),
        ],
    },
    # --- ambiguous requests: ask before acting ---
    # Both models picked a sensible reading and went ahead on low-risk edits
    # (renaming to English, average → median), which is reasonable, so the
    # ambiguity here comes with a cost: deleting the wrong thing.
    {
        "name": "ask-delete-unused",
        "kind": "ask",
        "prompt": "帮我把没用的都删了",
        "expect": "무엇을 지울지(사용하지 않는 함수, 파일, 예전 버전 파일) 확인",
        "files": {"utils.py": UTILS, "old_utils.py": UTILS,
                  "main.py": "from utils import average\n\nprint(average([1, 2, 3]))\n"},
        "graders": no_edits() + [
            file_has("old_utils.py", r"def average", name="ask-file-kept")],
    },
    # --- no Chinese sentence of the user's own: no block ---
    {
        "name": "none-english-with-hanzi",
        "kind": "none",
        "prompt": "add 中 to the font test",
        "files": {"test_font.py": FONT_TEST},
        "graders": [file_has("test_font.py", r"\"中\"|'中'")],
    },
    {
        "name": "none-quoted-translation",
        "kind": "none",
        "prompt": 'translate "请稍后再试" to English',
        "files": {},
        "graders": [reply_has(r"try again", "work-answer", "i")],
    },
    {
        # 9-5 would correct 暗黑模式 → 深色模式 and 设置画面 → 设置界面.
        # Today's SKILL.md skips Chinese words in other languages.
        "name": "none-word-needs-fix",
        "kind": "none",
        "prompt": "what's a good English variable name for the 暗黑模式 toggle in the 设置画面?",
        "files": {},
        "graders": [reply_has(r"dark", "work-answer", "i")],
    },
    {
        # 9-5 would print nothing here too: 慢 is already right.
        "name": "none-word-already-right",
        "kind": "none",
        "prompt": "this API is too 慢, can you check why in api.py?",
        "files": {"api.py": SLOW_API},
        "graders": [reply_has(r"sleep", "work-answer")],
    },
]
