import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "plugins", "chinese-proofread", "hooks"))
from zhuyin import convert_block, to_zhuyin  # noqa: E402


class ToZhuyinTest(unittest.TestCase):
    def check(self, cases):
        for pinyin, expected in cases:
            with self.subTest(pinyin=pinyin):
                self.assertEqual(to_zhuyin(pinyin), expected)

    def test_tones(self):
        self.check([("mā", "ㄇㄚ"), ("má", "ㄇㄚˊ"), ("mǎ", "ㄇㄚˇ"),
                    ("mà", "ㄇㄚˋ"), ("ma", "˙ㄇㄚ")])

    def test_words_and_spaces(self):
        self.check([
            ("yùnxíng de gèng kuài", "ㄩㄣˋ ㄒㄧㄥˊ ˙ㄉㄜ ㄍㄥˋ ㄎㄨㄞˋ"),
            ("běndì fúwùqì", "ㄅㄣˇ ㄉㄧˋ ㄈㄨˊ ㄨˋ ㄑㄧˋ"),
            ("ànniǔ", "ㄢˋ ㄋㄧㄡˇ"),
            ("Běijīng", "ㄅㄟˇ ㄐㄧㄥ"),
        ])

    def test_finals_with_a_spelling_of_their_own(self):
        self.check([
            # The initial alone.
            ("zhīdào", "ㄓ ㄉㄠˋ"), ("sì", "ㄙˋ"), ("rì", "ㄖˋ"),
            # u after j, q and x is ü.
            ("qù", "ㄑㄩˋ"), ("juéde", "ㄐㄩㄝˊ ˙ㄉㄜ"), ("xuǎn", "ㄒㄩㄢˇ"),
            ("nǚ", "ㄋㄩˇ"), ("lüè", "ㄌㄩㄝˋ"),
            # iu, ui and un stand for iou, uei and uen.
            ("liù", "ㄌㄧㄡˋ"), ("duì", "ㄉㄨㄟˋ"), ("lùn", "ㄌㄨㄣˋ"),
            ("yǒu", "ㄧㄡˇ"), ("wèntí", "ㄨㄣˋ ㄊㄧˊ"), ("yòng", "ㄩㄥˋ"),
            ("érqiě", "ㄦˊ ㄑㄧㄝˇ"), ("yìdiǎnr", "ㄧˋ ㄉㄧㄢˇㄦ"),
        ])

    def test_apostrophe_splits_syllables(self):
        self.check([("xī'ān", "ㄒㄧ ㄢ"), ("xiān", "ㄒㄧㄢ"),
                    ("fāng’àn", "ㄈㄤ ㄢˋ")])

    def test_what_is_not_pinyin(self):
        for text in ["main", "local server", "API", "utils.py", "", "dàz",
                     "…", "처리하다"]:
            with self.subTest(text=text):
                self.assertIsNone(to_zhuyin(text))

    def test_untoned_words_must_be_neutral_syllables(self):
        # 的(de) and 们(men) are pinyin; English words that spell other
        # syllables are not.
        self.assertEqual(to_zhuyin("de"), "˙ㄉㄜ")
        self.assertEqual(to_zhuyin("zhe men"), "˙ㄓㄜ ˙ㄇㄣ")
        self.assertIsNone(to_zhuyin("change"))
        self.assertIsNone(to_zhuyin("hang"))
        self.assertIsNone(to_zhuyin("de server"))

    def test_other_words_among_pinyin_stay(self):
        self.check([
            ("zài utils.py de zuìhòu", "ㄗㄞˋ utils.py ˙ㄉㄜ ㄗㄨㄟˋ ㄏㄡˋ"),
            ("zài… jiā yí ge hánshù",
             "ㄗㄞˋ… ㄐㄧㄚ ㄧˊ ˙ㄍㄜ ㄏㄢˊ ㄕㄨˋ"),
            ("chǔlǐ, 처리하다", "ㄔㄨˇ ㄌㄧˇ, 처리하다"),
            ("Python de lièbiǎo", "Python ˙ㄉㄜ ㄌㄧㄝˋ ㄅㄧㄠˇ"),
            ("commit xìnxī", "commit ㄒㄧㄣˋ ㄒㄧ"),
            ("nǐ néng …… ma", "ㄋㄧˇ ㄋㄥˊ …… ˙ㄇㄚ"),
        ])


class ConvertBlockTest(unittest.TestCase):
    def test_explanation_lines_are_converted(self):
        block = ("📝 中文校对\n原文: 让他更快\n修正: 让它运行得更快\n설명:\n"
                 "- 사물은 他(tā) 대신 它(tā)로 가리킵니다.\n"
                 "- 运行得更快(yùnxíng de gèng kuài)로 씁니다.\n---")
        self.assertEqual(convert_block(block), (
            "📝 中文校对\n原文: 让他更快\n修正: 让它运行得更快\n설명:\n"
            "- 사물은 他(ㄊㄚ) 대신 它(ㄊㄚ)로 가리킵니다.\n"
            "- 运行得更快(ㄩㄣˋ ㄒㄧㄥˊ ˙ㄉㄜ ㄍㄥˋ ㄎㄨㄞˋ)로 씁니다.\n---"))

    def test_word_lines_and_quoted_words(self):
        block = "- 按键 → 按鈕(ànniǔ): `按键`(ànjiàn)은 키입니다.\n- 函式（hánshì）"
        self.assertEqual(
            convert_block(block),
            "- 按键 → 按鈕(ㄢˋ ㄋㄧㄡˇ): `按键`(ㄢˋ ㄐㄧㄢˋ)은 키입니다.\n"
            "- 函式（ㄏㄢˊ ㄕˋ）")

    def test_what_stays(self):
        for line in ["原文: 跑(pǎo)起来", "修正: 把本地服务器(fúwùqì)跑起来",
                     "- 本地服务器(local server)를 씁니다.",
                     "- local server(běndì fúwùqì)",
                     "📝 中文校对: ✅ 자연스럽습니다."]:
            with self.subTest(line=line):
                self.assertEqual(convert_block(line), line)


if __name__ == "__main__":
    unittest.main()
