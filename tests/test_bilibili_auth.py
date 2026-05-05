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
    default_biliup_login_path,
    default_bili_cookie_path,
    ensure_biliup_cookie_path,
    is_formal_biliup_login_payload,
    load_biliup_cookie_payload,
    resolve_bili_cookie_path,
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
        self.assertEqual(
            default_biliup_login_path(ROOT),
            ROOT / "cookies.json",
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

    def test_formal_login_payload_detection(self) -> None:
        payload = {
            "token_info": {
                "access_token": "access",
                "refresh_token": "refresh",
            }
        }
        self.assertTrue(is_formal_biliup_login_payload(payload))
        self.assertFalse(is_formal_biliup_login_payload({"token_info": {"access_token": "", "refresh_token": ""}}))

    def test_cookie_resolution_prefers_formal_default_login_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            login_path = default_biliup_login_path(root)
            login_path.write_text("{}", encoding="utf-8")
            resolved, source = resolve_bili_cookie_path(None, None, root)
            self.assertEqual(resolved, login_path.resolve())
            self.assertEqual(source, "default_formal")

    def test_ensure_biliup_cookie_path_raises_when_formal_login_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            from unittest.mock import patch

            with patch("bilibili_auth.start_biliup_login", return_value=root / "cookies.json"):
                with self.assertRaises(RuntimeError) as ctx:
                    ensure_biliup_cookie_path(None, None, root, biliup_bin="biliup")
        self.assertIn("Opened a biliup login window", str(ctx.exception))

    def test_ensure_biliup_cookie_path_accepts_explicit_cookie_without_tokens_when_valid(self) -> None:
        payload = build_biliup_cookie_payload(
            {
                "SESSDATA": "sess",
                "bili_jct": "csrf",
                "DedeUserID": "123456",
            }
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cookie_path = root / "explicit.json"
            save_biliup_cookie_payload(cookie_path, payload)
            from unittest.mock import patch

            with patch("bilibili_auth.verify_cookie_payload", return_value=(True, "ok")):
                resolved, source = ensure_biliup_cookie_path(str(cookie_path), None, root, biliup_bin="biliup")
        self.assertEqual(resolved, cookie_path.resolve())
        self.assertEqual(source, "argument")


if __name__ == "__main__":
    unittest.main()
