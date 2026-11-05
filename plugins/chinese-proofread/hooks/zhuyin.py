"""Turn the pinyin in a proofreading block into zhuyin (bopomofo).

The model always writes pinyin, which the eval already checks; turning it into
zhuyin is a fixed mapping, so code does it instead of more instructions.

Only pinyin in parentheses right after a hanzi on an explanation line is
turned, like 它(tā) or 运行得更快(yùnxíng de gèng kuài). The 原文 and 修正
lines have no pinyin. Parentheses that do not read as pinyin as a whole, like
an English word, stay as they are.
"""

import re

TONES = {}
for base, marked in [("a", "āáǎà"), ("e", "ēéěè"), ("i", "īíǐì"),
                     ("o", "ōóǒò"), ("u", "ūúǔù"), ("ü", "ǖǘǚǜ")]:
    for tone, char in enumerate(marked, 1):
        TONES[char] = (base, tone)
TONE_SIGNS = {1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ"}
NEUTRAL = "˙"

INITIALS = {
    "b": "ㄅ", "p": "ㄆ", "m": "ㄇ", "f": "ㄈ", "d": "ㄉ", "t": "ㄊ",
    "n": "ㄋ", "l": "ㄌ", "g": "ㄍ", "k": "ㄎ", "h": "ㄏ", "j": "ㄐ",
    "q": "ㄑ", "x": "ㄒ", "zh": "ㄓ", "ch": "ㄔ", "sh": "ㄕ", "r": "ㄖ",
    "z": "ㄗ", "c": "ㄘ", "s": "ㄙ",
}
FINALS = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ",
    "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ",
    "ong": "ㄨㄥ", "i": "ㄧ", "ia": "ㄧㄚ", "ie": "ㄧㄝ", "iao": "ㄧㄠ",
    "iu": "ㄧㄡ", "ian": "ㄧㄢ", "in": "ㄧㄣ", "iang": "ㄧㄤ", "ing": "ㄧㄥ",
    "iong": "ㄩㄥ", "u": "ㄨ", "ua": "ㄨㄚ", "uo": "ㄨㄛ", "uai": "ㄨㄞ",
    "ui": "ㄨㄟ", "uan": "ㄨㄢ", "un": "ㄨㄣ", "uang": "ㄨㄤ", "ü": "ㄩ",
    "üe": "ㄩㄝ", "ue": "ㄩㄝ",
}
# Which finals each group of initials takes. A little looser than the real
# table; a wrong guess can only turn something that was not pinyin anyway.
LABIAL = "a o e ai ei ao ou an en ang eng i ie iao iu ian in ing u"
ALVEOLAR = ("a o e ai ei ao ou an en ang eng ong i ia ie iao iu ian in iang "
            "ing u uo ui uan un ü üe ue")
VELAR = "a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang"
PALATAL = "i ia ie iao iu ian in iang ing iong u ue uan un"
SIBILANT = "i a e ai ei ao ou an en ang eng ong u ua uo uai ui uan un uang"
GROUPS = [("b p m f", LABIAL), ("d t n l", ALVEOLAR), ("g k h", VELAR),
          ("j q x", PALATAL), ("zh ch sh r z c s", SIBILANT)]
# After j, q and x, u is written for ü.
PALATAL_U = {"u": "ㄩ", "ue": "ㄩㄝ", "uan": "ㄩㄢ", "un": "ㄩㄣ"}
WITHOUT_INITIAL = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ",
    "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ", "er": "ㄦ",
    "yi": "ㄧ", "ya": "ㄧㄚ", "yo": "ㄧㄛ", "ye": "ㄧㄝ", "yao": "ㄧㄠ",
    "you": "ㄧㄡ", "yan": "ㄧㄢ", "yin": "ㄧㄣ", "yang": "ㄧㄤ",
    "ying": "ㄧㄥ", "yong": "ㄩㄥ", "yu": "ㄩ", "yue": "ㄩㄝ", "yuan": "ㄩㄢ",
    "yun": "ㄩㄣ", "wu": "ㄨ", "wa": "ㄨㄚ", "wo": "ㄨㄛ", "wai": "ㄨㄞ",
    "wei": "ㄨㄟ", "wan": "ㄨㄢ", "wen": "ㄨㄣ", "wang": "ㄨㄤ",
    "weng": "ㄨㄥ",
}


def syllable_table():
    table = dict(WITHOUT_INITIAL)
    for initials, finals in GROUPS:
        for initial in initials.split():
            for final in finals.split():
                if initial in "jqx" and final in PALATAL_U:
                    sound = PALATAL_U[final]
                elif final == "i" and initial in ("zh", "ch", "sh", "r",
                                                  "z", "c", "s"):
                    # zhi, ci: the initial alone.
                    sound = ""
                else:
                    sound = FINALS[final]
                table[initial + final] = INITIALS[initial] + sound
    return table


SYLLABLES = syllable_table()
LONGEST = max(len(s) for s in SYLLABLES) + 1  # + 1 for an erhua r
# A hanzi, maybe closed by a quote or backtick, then parentheses.
AFTER_HANZI = re.compile(
    r"([㐀-䶿一-鿿][`'\"”’」]?)([(（])([^()（）\n]+)([)）])")
PINYIN_LINE = re.compile(r"^(原文|修正):")
# A run of pinyin letters; the parentheses are split into these and the rest.
WORD = re.compile("([a-zA-Zü" + "".join(TONES) + "'’]+)")
# Syllables the model writes without a tone mark: neutral-tone particles and
# suffixes.
NEUTRAL_SOUNDS = {SYLLABLES[s] for s in (
    "de le ma ne ba a ya la na wa zhe men me ge zi tou guo shang xia li lai "
    "qu shi").split()}


def plain(text):
    """The letters without tone marks, and the tone of each position."""
    letters, tones = [], []
    for char in text:
        base, tone = TONES.get(char, (char, 0))
        letters.append(base)
        tones.append(tone)
    return "".join(letters), tones


def sound_of(letters, tones):
    """The zhuyin of one syllable, or None if it is not one."""
    marked = [t for t in tones if t]
    if len(marked) > 1:
        return None
    erhua = ""
    if letters not in SYLLABLES and letters.endswith("r") and letters != "er":
        letters, erhua = letters[:-1], "ㄦ"
    sound = SYLLABLES.get(letters)
    if sound is None:
        return None
    if not marked:
        return NEUTRAL + sound + erhua
    return sound + TONE_SIGNS[marked[0]] + erhua


def split_part(text):
    """A part of a word without apostrophes, as zhuyin syllables, or None.

    A syllable that starts with a, o or e needs an apostrophe in front of it
    inside a word, so without one xian is a single syllable, not xi'an."""
    letters, tones = plain(text)
    # best[i]: the fewest syllables that spell letters[:i].
    best = {0: []}
    for end in range(1, len(letters) + 1):
        for start in range(max(0, end - LONGEST), end):
            if start not in best:
                continue
            if start > 0 and letters[start] in "aoe":
                continue
            sound = sound_of(letters[start:end], tones[start:end])
            if sound is None:
                continue
            found = best[start] + [sound]
            if end not in best or len(found) < len(best[end]):
                best[end] = found
    return best.get(len(letters))


def word_zhuyin(word):
    """The zhuyin syllables of one pinyin word, or None if it is not one.

    A word without tone marks counts only when every syllable is one that is
    often neutral, like 的(de); this keeps out English words that happen to
    spell pinyin, like change or men."""
    syllables = []
    for part in re.split(r"['’]", word.lower()):
        found = split_part(part) if part else None
        if found is None:
            return None
        syllables += found
    if not any(c in TONES for c in word) and not all(
            s.startswith(NEUTRAL) and s[1:] in NEUTRAL_SOUNDS
            for s in syllables):
        return None
    return syllables


def to_zhuyin(text):
    """The text in parentheses with its pinyin words in zhuyin, or None.

    Words that are not pinyin, like an identifier in zài utils.py de zuìhòu,
    a … or a gloss after a comma, stay as they are, as long as some word has
    a tone mark. Without one, every word must be pinyin."""
    parts = WORD.split(text)
    words = parts[1::2]
    if not words:
        return None
    turned = [word_zhuyin(w) for w in words]
    if any(t is None for t in turned) and not any(c in TONES for c in text):
        return None
    if all(t is None for t in turned):
        return None
    for i, (word, syllables) in enumerate(zip(words, turned)):
        parts[2 * i + 1] = word if syllables is None else " ".join(syllables)
    return "".join(parts)


def turn_parentheses(match):
    hanzi, opening, inside, closing = match.groups()
    zhuyin = to_zhuyin(inside)
    if zhuyin is None:
        return match.group(0)
    return hanzi + opening + zhuyin + closing


def convert_block(block):
    lines = block.split("\n")
    for i, line in enumerate(lines):
        if not PINYIN_LINE.match(line):
            lines[i] = AFTER_HANZI.sub(turn_parentheses, line)
    return "\n".join(lines)
