from __future__ import annotations

import os
import sys
import tempfile
import unittest
from argparse import Namespace
from json import dumps
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from publish_localized_video import (  # noqa: E402
    DEFAULT_TID_FALLBACK,
    TID_ENV_VAR,
    build_biliup_command,
    classify_upload_failure,
    fallback_description,
    normalize_upload_tid,
    resolve_upload_description,
    resolve_upload_tid,
    skill_root,
)
from bilibili_auth import default_biliup_login_path, resolve_bili_cookie_path  # noqa: E402


class DummyResult:
    def __init__(self, stdout: str = "", stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr


class PublishLocalizedVideoTests(unittest.TestCase):
    def make_args(self, **overrides: object) -> Namespace:
        values = {
            "biliup_bin": "biliup",
            "desc": None,
            "tags": "中文字幕,翻译,搬运",
            "tid": None,
            "copyright": 1,
            "is_only_self": 0,
            "cover": None,
        }
        values.update(overrides)
        return Namespace(**values)

    def write_segments(self, workdir: Path, segments: list[dict[str, str]]) -> None:
        (workdir / "translated_segments.json").write_text(
            dumps({"segments": segments}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

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
        default_path = default_biliup_login_path(root)
        try:
            default_path.write_text("{}", encoding="utf-8")
            resolved, source = resolve_bili_cookie_path(None, None, root)
            self.assertEqual(resolved, default_path.resolve())
            self.assertEqual(source, "default_formal")
        finally:
            if default_path.exists():
                default_path.unlink()

    def test_upload_failure_classification_for_not_logged_in(self) -> None:
        message = classify_upload_failure(DummyResult(stderr='ResponseData { code: -101, message: "账号未登录" }'))
        self.assertIn("complete biliup login", message.lower())

    def test_build_biliup_command_always_uses_resolved_tid(self) -> None:
        command = build_biliup_command(
            self.make_args(tid=188, copyright=1),
            Path("video.mp4"),
            "title",
            "desc",
            "https://example.com",
            None,
            231,
        )
        self.assertIn("--tid", command)
        self.assertEqual(command[command.index("--tid") + 1], "231")
        self.assertIn("--copyright", command)
        self.assertEqual(command[command.index("--copyright") + 1], "1")
        self.assertIn("--is-only-self", command)
        self.assertEqual(command[command.index("--is-only-self") + 1], "0")
        self.assertNotIn("--source", command)

    def test_build_biliup_command_adds_source_for_repost(self) -> None:
        command = build_biliup_command(
            self.make_args(copyright=2),
            Path("video.mp4"),
            "title",
            "desc",
            "https://example.com",
            None,
            188,
        )
        self.assertIn("--source", command)

    def test_build_biliup_command_allows_private_submission_when_requested(self) -> None:
        command = build_biliup_command(
            self.make_args(is_only_self=1),
            Path("video.mp4"),
            "title",
            "desc",
            "https://example.com",
            None,
            231,
        )
        self.assertIn("--is-only-self", command)
        self.assertEqual(command[command.index("--is-only-self") + 1], "1")

    def test_resolve_upload_tid_prefers_explicit_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolution = resolve_upload_tid(
                self.make_args(tid=188),
                Path(temp_dir),
                "普通标题",
                "标签",
                "",
            )
        self.assertEqual(resolution["tid"], 231)
        self.assertEqual(resolution["source"], "argument")
        self.assertEqual(resolution["parent_tid"], 188)

    def test_resolve_upload_tid_detects_technology_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workdir = Path(temp_dir)
            self.write_segments(
                workdir,
                [
                    {
                        "text": "This vibe coding workflow uses AI prompts to build apps.",
                        "translated_text": "这个 AI workflow 用 prompt 来构建 app。",
                    }
                ],
            )
            resolution = resolve_upload_tid(
                self.make_args(tags="AI,Prompt,SaaS"),
                workdir,
                "Vibe Coding with AI",
                "AI,Prompt,SaaS",
                "",
            )
        self.assertEqual(resolution["tid"], 231)
        self.assertEqual(resolution["source"], "rule")
        self.assertEqual(resolution["parent_tid"], 188)

    def test_resolve_upload_tid_uses_environment_fallback(self) -> None:
        previous = os.environ.get(TID_ENV_VAR)
        os.environ[TID_ENV_VAR] = "188"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                resolution = resolve_upload_tid(
                    self.make_args(tags=""),
                    Path(temp_dir),
                    "普通视频",
                    "",
                    "",
                )
        finally:
            if previous is None:
                os.environ.pop(TID_ENV_VAR, None)
            else:
                os.environ[TID_ENV_VAR] = previous
        self.assertEqual(resolution["tid"], 231)
        self.assertEqual(resolution["source"], "environment")
        self.assertEqual(resolution["parent_tid"], 188)

    def test_resolve_upload_tid_uses_default_fallback(self) -> None:
        previous = os.environ.get(TID_ENV_VAR)
        try:
            os.environ.pop(TID_ENV_VAR, None)
            with tempfile.TemporaryDirectory() as temp_dir:
                resolution = resolve_upload_tid(
                    self.make_args(tags=""),
                    Path(temp_dir),
                    "普通视频",
                    "",
                    "",
                )
        finally:
            if previous is not None:
                os.environ[TID_ENV_VAR] = previous
        self.assertEqual(resolution["tid"], 122)
        self.assertEqual(resolution["source"], "fallback")
        self.assertEqual(resolution["parent_tid"], DEFAULT_TID_FALLBACK)

    def test_normalize_upload_tid_maps_parent_category_to_upload_leaf(self) -> None:
        normalized = normalize_upload_tid(188)
        self.assertEqual(normalized["tid"], 231)
        self.assertEqual(normalized["parent_tid"], 188)
        self.assertEqual(normalized["parent_name"], "科技")
        self.assertEqual(normalized["name"], "计算机技术")

    def test_resolve_upload_tid_rejects_invalid_environment_tid(self) -> None:
        previous = os.environ.get(TID_ENV_VAR)
        os.environ[TID_ENV_VAR] = "abc"
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaises(SystemExit):
                    resolve_upload_tid(
                        self.make_args(tags=""),
                        Path(temp_dir),
                        "普通视频",
                        "",
                        "",
                    )
        finally:
            if previous is None:
                os.environ.pop(TID_ENV_VAR, None)
            else:
                os.environ[TID_ENV_VAR] = previous

    def test_resolve_upload_description_prefers_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolution = resolve_upload_description(
                self.make_args(desc="手动简介"),
                title="标题",
                tags="标签",
                source_url="https://example.com",
                workdir=Path(temp_dir),
            )
        self.assertEqual(resolution["desc"], "手动简介")
        self.assertEqual(resolution["source"], "argument")

    def test_resolve_upload_description_falls_back_when_missing_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            resolution = resolve_upload_description(
                self.make_args(),
                title="标题",
                tags="标签",
                source_url="https://example.com",
                workdir=Path(temp_dir),
            )
        self.assertEqual(resolution["source"], "fallback")
        self.assertEqual(resolution["desc"], fallback_description("https://example.com"))


if __name__ == "__main__":
    unittest.main()
