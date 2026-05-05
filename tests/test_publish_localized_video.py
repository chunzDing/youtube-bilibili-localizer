from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from publish_localized_video import classify_upload_failure, skill_root  # noqa: E402
from bilibili_auth import resolve_bili_cookie_path  # noqa: E402


class DummyResult:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


class PublishLocalizedVideoTests(unittest.TestCase):
    def test_cookie_resolution_priority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            explicit = Path(temp_dir) / "explicit.json"
            env_path = Path(temp_dir) / "env.json"
            explicit.write_text("{}", encoding="utf-8")
            env_path.write_text("{}", encoding="utf-8")
            resolved, source = resolve_bili_cookie_path(str(explicit), str(env_path), skill_root())
            self.assertEqual(resolved, explicit.resolve())
            self.assertEqual(source, "argument")

    def test_cookie_resolution_falls_back_to_default(self) -> None:
        root = skill_root()
        default_dir = root / ".auth"
        default_dir.mkdir(exist_ok=True)
        default_path = default_dir / "bilibili.cookies.json"
        try:
            default_path.write_text("{}", encoding="utf-8")
            resolved, source = resolve_bili_cookie_path(None, None, root)
            self.assertEqual(resolved, default_path.resolve())
            self.assertEqual(source, "default")
        finally:
            if default_path.exists():
                default_path.unlink()

    def test_upload_failure_classification_for_not_logged_in(self) -> None:
        message = classify_upload_failure(DummyResult(stderr='ResponseData { code: -101, message: "账号未登录" }'))
        self.assertIn("not logged in", message.lower())


if __name__ == "__main__":
    unittest.main()
