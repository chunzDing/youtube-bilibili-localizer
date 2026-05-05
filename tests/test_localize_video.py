from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from localize_video import Segment, refine_segments  # noqa: E402


class LocalizeVideoTests(unittest.TestCase):
    def test_refine_segments_merges_short_fragments(self) -> None:
        segments = [
            Segment(0.0, 0.7, "And now"),
            Segment(0.7, 2.2, "we build the workflow for the AI agent."),
        ]
        refined, changed = refine_segments(segments, "high")
        self.assertTrue(changed)
        self.assertEqual(len(refined), 1)
        self.assertIn("workflow", refined[0].text)

    def test_refine_segments_splits_long_segment(self) -> None:
        long_text = "This is a long clause, and it keeps going, and it keeps explaining, and it keeps stacking details."
        segments = [Segment(0.0, 12.0, long_text)]
        refined, changed = refine_segments(segments, "high")
        self.assertTrue(changed)
        self.assertGreater(len(refined), 1)
        self.assertAlmostEqual(refined[0].start, 0.0)
        self.assertAlmostEqual(refined[-1].end, 12.0)

    def test_standard_quality_keeps_original_segments(self) -> None:
        segments = [Segment(0.0, 1.0, "Short text")]
        refined, changed = refine_segments(segments, "standard")
        self.assertFalse(changed)
        self.assertEqual(refined[0].text, "Short text")


if __name__ == "__main__":
    unittest.main()
