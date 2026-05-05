from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bilibili_auth import (  # noqa: E402
    build_biliup_cookie_payload,
    default_bili_cookie_path,
    load_biliup_cookie_payload,
    save_biliup_cookie_payload,
    validate_biliup_cookie_payload,
)


class BilibiliAuthTests(unittest.TestCase):
    def test_build_and_validate_cookie_payload(self) -> None:
        payload = build_biliup_cookie_payload(
            {
                "SESSDATA": "sess",
                "bili_jct": "csrf",
                "DedeUserID": "123456",
                "sid": "abc",
            }
        )
        validate_biliup_cookie_payload(payload)
        cookies = {item["name"]: item["value"] for item in payload["cookie_info"]["cookies"]}
        self.assertEqual(cookies["SESSDATA"], "sess")
        self.assertEqual(cookies["sid"], "abc")

    def test_default_cookie_path(self) -> None:
        self.assertEqual(
            default_bili_cookie_path(ROOT),
            ROOT / ".auth" / "bilibili.cookies.json",
        )

    def test_save_and_load_cookie_payload(self) -> None:
        payload = build_biliup_cookie_payload(
            {
                "SESSDATA": "sess",
                "bili_jct": "csrf",
                "DedeUserID": "123456",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cookies.json"
            save_biliup_cookie_payload(path, payload)
            loaded = load_biliup_cookie_payload(path)
            self.assertEqual(loaded["mid"], 123456)


if __name__ == "__main__":
    unittest.main()
