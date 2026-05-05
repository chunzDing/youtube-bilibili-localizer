from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from translation_utils import clean_title_text, load_glossary  # noqa: E402


class TranslationUtilsTests(unittest.TestCase):
    def test_glossary_protection_and_normalization(self) -> None:
        glossary = load_glossary(ROOT / "references" / "glossary.zh.json")
        prepared, placeholders = glossary.protect_text("Base44 is a SaaS tool for vibe coding.")
        self.assertIn("__YBL_TERM_0__", prepared)
        normalized = glossary.normalize_translation(
            "__YBL_TERM_0__ 是一个 saas 工具，用于 vibe coding 和 prompt workflow。",
            placeholders,
        )
        self.assertIn("Base44", normalized)
        self.assertIn("SaaS", normalized)
        self.assertIn("氛围编程", normalized)
        self.assertIn("提示词", normalized)
        self.assertIn("工作流", normalized)

    def test_clean_title_text_strips_existing_prefix_noise(self) -> None:
        self.assertEqual(clean_title_text("【中文字幕】  Vibe Coding 入门"), "Vibe Coding 入门")
        self.assertEqual(clean_title_text("[中文翻译] Base44 Master Class"), "Base44 Master Class")


if __name__ == "__main__":
    unittest.main()
