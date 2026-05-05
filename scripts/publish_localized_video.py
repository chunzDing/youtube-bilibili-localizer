from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


TITLE_PREFIX = "【中文字幕】"
DEFAULT_TAGS = "中文字幕,翻译,搬运"


class TranslationFailure(RuntimeError):
    pass


def is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value, re.IGNORECASE))


def quote_arg(value: str) -> str:
    if not value or any(ch.isspace() for ch in value) or any(ch in value for ch in "\"'[]"):
        return json.dumps(value, ensure_ascii=False)
    return value


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(quote_arg(part) for part in cmd), flush=True)
    return subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
    )


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def localizer_script() -> Path:
    path = skill_root() / "scripts" / "localize_video.py"
    if not path.exists():
        raise SystemExit(f"localizer script not found: {path}")
    return path


def default_python_exe() -> str:
    root = skill_root()
    win_python = root / ".venv" / "Scripts" / "python.exe"
    posix_python = root / ".venv" / "bin" / "python"
    if win_python.exists():
        return str(win_python)
    if posix_python.exists():
        return str(posix_python)
    return sys.executable


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fallback_title(value: str) -> str:
    stripped = value.rstrip("/")
    return stripped.rsplit("/", 1)[-1] or "video"


def normalize_language_code(language: str | None) -> str | None:
    if not language:
        return None
    return language.strip().lower().replace("_", "-").split("-", 1)[0] or None


def clean_title(title: str) -> str:
    title = re.sub(
        r"^[\[\(【]\s*(中文字幕|中英字幕|中字|中文翻译|中文配音|Chinese subtitles?)\s*[\]\)】]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"\s+", " ", title).strip()
    return title or "视频"


def fetch_metadata(
    input_value: str,
    cookies_from_browser: str | None,
    cookies_path: str | None,
    yt_dlp_impersonate: str | None,
) -> dict[str, Any]:
    if not is_url(input_value):
        path = Path(input_value)
        return {"title": path.stem or "video", "webpage_url": str(path)}

    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        "--no-warnings",
    ]
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
    if yt_dlp_impersonate:
        cmd.extend(["--impersonate", yt_dlp_impersonate])
    cmd.append(input_value)

    result = run(cmd, check=False)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        return {
            "title": fallback_title(input_value),
            "webpage_url": input_value,
            "metadata_error": result.stderr.strip(),
        }
    return json.loads(result.stdout)


def create_volc_translate_api() -> Any:
    try:
        from volcenginesdkcore import ApiClient, Configuration
        from volcenginesdktranslate20250301 import TRANSLATE20250301Api
    except ImportError as exc:
        raise TranslationFailure("volcengine-python-sdk is required for title translation") from exc

    ak = os.environ.get("VOLCENGINE_ACCESS_KEY", "").strip()
    sk = os.environ.get("VOLCENGINE_SECRET_KEY", "").strip()
    if not ak or not sk:
        raise TranslationFailure("VOLCENGINE_ACCESS_KEY and VOLCENGINE_SECRET_KEY are required for title translation")

    configuration = Configuration()
    configuration.ak = ak
    configuration.sk = sk
    configuration.region = os.environ.get("VOLCENGINE_REGION", "cn-north-1").strip() or "cn-north-1"
    return TRANSLATE20250301Api(ApiClient(configuration))


def ensure_argos_title_translation(source_language: str | None) -> Any:
    normalized_source = normalize_language_code(source_language)
    if normalized_source != "en":
        if normalized_source:
            raise TranslationFailure(
                f"Offline title translation currently supports only en->zh, got {normalized_source}->zh"
            )
        raise TranslationFailure(
            "Offline title translation requires source language detection or an explicit --source-language en"
        )

    try:
        import argostranslate.package
        import argostranslate.translate
    except ImportError as exc:
        raise TranslationFailure("argostranslate is not installed in the current environment") from exc

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed if lang.code == "en"), None)
    to_lang = next((lang for lang in installed if lang.code == "zh"), None)
    if from_lang and to_lang:
        translation = from_lang.get_translation(to_lang)
        if translation:
            return translation

    argostranslate.package.update_package_index()
    package = next(
        (
            pkg
            for pkg in argostranslate.package.get_available_packages()
            if pkg.from_code == "en" and pkg.to_code == "zh"
        ),
        None,
    )
    if package is None:
        raise TranslationFailure("Could not find an Argos en->zh package for title translation")

    download_path = package.download()
    argostranslate.package.install_from_path(download_path)

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed if lang.code == "en"), None)
    to_lang = next((lang for lang in installed if lang.code == "zh"), None)
    if not from_lang or not to_lang:
        raise TranslationFailure("Argos en->zh package installation did not complete successfully")
    translation = from_lang.get_translation(to_lang)
    if not translation:
        raise TranslationFailure("Argos en->zh title translation is unavailable after installation")
    return translation


def translate_title_api(title: str, source_language: str | None) -> str:
    try:
        from volcenginesdktranslate20250301 import TranslateTextRequest
    except ImportError as exc:
        raise TranslationFailure("volcengine-python-sdk is required for title translation") from exc

    api = create_volc_translate_api()
    try:
        response = api.translate_text(
            TranslateTextRequest(
                source_language=source_language,
                target_language="zh",
                text_list=[title],
            )
        )
    except Exception as exc:
        raise TranslationFailure(str(exc)) from exc

    translations = getattr(response, "translation_list", None) or []
    if not translations:
        raise TranslationFailure("Volcengine title translation returned no text")
    translated = str(translations[0].translation or "").strip()
    return clean_title(translated)


def translate_title_offline(title: str, source_language: str | None) -> str:
    translator = ensure_argos_title_translation(source_language)
    translated = str(translator.translate(title) if title else "").strip()
    if not translated:
        raise TranslationFailure("Offline title translation returned no text")
    return clean_title(" ".join(translated.split()))


def translate_title(title: str, source_language: str | None, translation_mode: str) -> tuple[str, dict[str, Any]]:
    if translation_mode == "offline":
        translated = translate_title_offline(title, source_language)
        return translated, {
            "translation_mode_requested": translation_mode,
            "title_translation_mode_used": "offline",
            "title_translation_fallback_used": False,
            "title_translation_fallback_reason": "",
        }

    try:
        translated = translate_title_api(title, source_language)
        return translated, {
            "translation_mode_requested": translation_mode,
            "title_translation_mode_used": "api",
            "title_translation_fallback_used": False,
            "title_translation_fallback_reason": "",
        }
    except TranslationFailure as exc:
        fallback_reason = str(exc)
        print(f"! API title translation failed, falling back to offline translation: {fallback_reason}", flush=True)
        translated = translate_title_offline(title, source_language)
        return translated, {
            "translation_mode_requested": translation_mode,
            "title_translation_mode_used": "offline",
            "title_translation_fallback_used": True,
            "title_translation_fallback_reason": fallback_reason,
        }


def resolve_downloaded_source(workdir: Path) -> Path:
    candidates = sorted(workdir.glob("source.*"))
    if not candidates:
        raise SystemExit(f"yt-dlp did not produce a source file in {workdir}")
    return candidates[0]


def download_source_video(
    input_value: str,
    workdir: Path,
    cookies_from_browser: str | None,
    cookies_path: str | None,
    yt_dlp_impersonate: str | None,
) -> Path:
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format",
        "mp4",
        "-f",
        "bv*[height<=1080]+ba/b[height<=1080]/b",
        "-o",
        str(workdir / "source.%(ext)s"),
    ]
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    if cookies_path:
        cmd.extend(["--cookies", cookies_path])
    if yt_dlp_impersonate:
        cmd.extend(["--impersonate", yt_dlp_impersonate])
    cmd.append(input_value)

    result = run(cmd, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return resolve_downloaded_source(workdir)


def run_localizer(
    args: argparse.Namespace,
    python_exe: str,
    workdir: Path,
    input_value: str,
) -> None:
    cmd = [
        python_exe,
        str(localizer_script()),
        "--input",
        input_value,
        "--workdir",
        str(workdir),
        "--whisper-model",
        args.whisper_model,
        "--whisper-device",
        args.whisper_device,
        "--whisper-compute-type",
        args.whisper_compute_type,
        "--translation-mode",
        args.translation_mode,
        "--subtitle-layout",
        args.subtitle_layout,
        "--voice",
        args.voice,
        "--background-volume",
        str(args.background_volume),
    ]
    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
    if args.cookies:
        cmd.extend(["--cookies", args.cookies])
    if args.yt_dlp_impersonate:
        cmd.extend(["--yt-dlp-impersonate", args.yt_dlp_impersonate])
    if args.transcript_json:
        cmd.extend(["--transcript-json", args.transcript_json])
    if args.skip_transcription:
        cmd.append("--skip-transcription")
    if args.source_language:
        cmd.extend(["--source-language", args.source_language])
    if args.mode == "subtitles":
        cmd.append("--skip-tts")
    if args.sidecar_subtitles:
        cmd.append("--sidecar-subtitles")

    result = run(cmd, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def selected_video_path(workdir: Path, mode: str) -> Path:
    if mode == "dub":
        final_video = workdir / "final.mp4"
        if not final_video.exists():
            raise SystemExit(f"expected localized final video missing: {final_video}")
        return final_video

    final_video = workdir / "final.mp4"
    if final_video.exists():
        return final_video
    source_candidates = sorted(workdir.glob("source.*"))
    if source_candidates:
        return source_candidates[0]
    raise SystemExit(f"could not find a video to upload in {workdir}")


def build_biliup_command(args: argparse.Namespace, video_path: Path, title: str, source_url: str | None) -> list[str]:
    biliup_bin = args.biliup_bin or os.environ.get("BILIUP_BIN") or "biliup"
    cmd = [biliup_bin]
    cookie = args.bili_cookie or os.environ.get("BILIUP_COOKIE")
    if cookie:
        cmd.extend(["--user-cookie", cookie])
    cmd.extend(["upload", str(video_path), "--title", title])

    if args.desc:
        cmd.extend(["--desc", args.desc])
    elif source_url:
        cmd.extend(["--desc", f"原视频链接: {source_url}"])

    tags = args.tags or DEFAULT_TAGS
    if tags:
        cmd.extend(["--tag", tags])
    if args.tid:
        cmd.extend(["--tid", str(args.tid)])
    if args.copyright:
        cmd.extend(["--copyright", str(args.copyright)])
    if args.copyright == 2 and source_url:
        cmd.extend(["--source", source_url])
    if args.cover:
        cmd.extend(["--cover", args.cover])
    return cmd


def load_subtitle_translation_info(workdir: Path, subtitle_layout: str) -> dict[str, Any]:
    translated_segments_path = workdir / "translated_segments.json"
    if not translated_segments_path.exists():
        return {"subtitle_layout_used": subtitle_layout}

    translated_payload = json.loads(translated_segments_path.read_text(encoding="utf-8"))
    return {
        "translation_mode_used": translated_payload.get("translation_mode_used"),
        "translation_fallback_used": bool(translated_payload.get("translation_fallback_used")),
        "translation_fallback_reason": translated_payload.get("translation_fallback_reason", ""),
        "subtitle_translation_mode_used": translated_payload.get("translation_mode_used"),
        "subtitle_translation_fallback_used": bool(translated_payload.get("translation_fallback_used")),
        "subtitle_translation_fallback_reason": translated_payload.get("translation_fallback_reason", ""),
        "source_language_used": translated_payload.get("source_language_used"),
        "subtitle_layout_used": translated_payload.get("subtitle_layout_used", subtitle_layout),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Localize a video into Chinese and prepare or publish a Bilibili upload.")
    parser.add_argument("--input", required=True, help="Video URL or local video file")
    parser.add_argument("--localized-video", help="Already-localized video to publish; skips localization")
    parser.add_argument("--mode", choices=["subtitles", "dub"], default="dub")
    parser.add_argument("--workdir", required=True, help="Directory for intermediate and final files")
    parser.add_argument("--env-file", help="Optional .env file to load before running")
    parser.add_argument("--python-exe", help="Python executable used to run the localizer")
    parser.add_argument("--cookies-from-browser", help="Browser name for yt-dlp cookies, for example edge or chrome")
    parser.add_argument("--cookies", help="Path to a yt-dlp compatible cookies.txt file")
    parser.add_argument("--yt-dlp-impersonate", help="yt-dlp impersonation target such as edge:windows-10")
    parser.add_argument("--transcript-json", help="Existing transcript JSON with segments")
    parser.add_argument("--skip-transcription", action="store_true")
    parser.add_argument("--source-language", help="Source language code hint")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-device", default="auto")
    parser.add_argument("--whisper-compute-type", default="default")
    parser.add_argument("--voice", default="zh_female_qingxin")
    parser.add_argument("--background-volume", type=float, default=0.12)
    parser.add_argument("--sidecar-subtitles", action="store_true")
    parser.add_argument("--translation-mode", default="api", choices=["api", "offline", "auto"], help="Subtitle and title translation mode")
    parser.add_argument("--subtitle-layout", default="bilingual", choices=["zh", "bilingual"], help="Subtitle layout for localized output")
    parser.add_argument("--translated-title", help="Override automatic title translation")
    parser.add_argument("--tags", default=DEFAULT_TAGS)
    parser.add_argument("--desc")
    parser.add_argument("--source-url", help="Optional source URL or reference text kept in metadata and used for repost submissions")
    parser.add_argument("--tid", type=int, help="Bilibili category id")
    parser.add_argument("--copyright", type=int, default=1, choices=[1, 2], help="1 original, 2 repost")
    parser.add_argument("--cover", help="Cover image path")
    parser.add_argument("--biliup-bin")
    parser.add_argument("--bili-cookie")
    parser.add_argument("--skip-upload", action="store_true", help="Generate files and metadata but do not upload")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --skip-upload that also prints the upload command")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        load_env_file(Path(args.env_file))

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    python_exe = args.python_exe or default_python_exe()

    metadata = fetch_metadata(args.input, args.cookies_from_browser, args.cookies, args.yt_dlp_impersonate)
    write_json(workdir / "metadata.source.json", metadata)

    if args.localized_video:
        video_path = Path(args.localized_video).resolve()
        if not video_path.exists():
            raise SystemExit(f"localized video not found: {video_path}")
    else:
        localizer_input = args.input
        if args.cookies and is_url(args.input):
            localizer_input = str(
                download_source_video(
                    args.input,
                    workdir,
                    args.cookies_from_browser,
                    args.cookies,
                    args.yt_dlp_impersonate,
                )
            )
        run_localizer(args, python_exe, workdir, localizer_input)
        video_path = selected_video_path(workdir, args.mode)

    subtitle_translation_info = load_subtitle_translation_info(workdir, args.subtitle_layout)
    source_language_hint = normalize_language_code(
        args.source_language or metadata.get("language") or subtitle_translation_info.get("source_language_used")
    )

    original_title = clean_title(str(metadata.get("title") or fallback_title(args.input)))
    if args.translated_title:
        translated_title = clean_title(args.translated_title)
        title_translation_info = {
            "translation_mode_requested": args.translation_mode,
            "title_translation_mode_used": "manual",
            "title_translation_fallback_used": False,
            "title_translation_fallback_reason": "",
        }
    else:
        translated_title, title_translation_info = translate_title(
            original_title,
            source_language_hint,
            args.translation_mode,
        )
    bilibili_title = TITLE_PREFIX + translated_title

    source_url = args.source_url or (str(metadata.get("webpage_url") or args.input) if is_url(args.input) else None)
    upload_cmd = build_biliup_command(args, video_path, bilibili_title, source_url)

    publish_metadata = {
        "input": args.input,
        "mode": args.mode,
        "original_title": original_title,
        "translated_title": translated_title,
        "bilibili_title": bilibili_title,
        "source_url": source_url,
        "video_path": str(video_path),
        "subtitles_path": str(workdir / "subtitles.zh.srt"),
        "subtitle_layout": args.subtitle_layout,
        "upload_command": upload_cmd,
        **title_translation_info,
        **subtitle_translation_info,
    }
    write_json(workdir / "publish_metadata.json", publish_metadata)

    print(json.dumps(publish_metadata, ensure_ascii=False, indent=2), flush=True)

    if args.dry_run or args.skip_upload:
        print("dry_run=true; upload skipped", flush=True)
        return 0

    if shutil.which(upload_cmd[0]) is None and not Path(upload_cmd[0]).exists():
        raise SystemExit(f"biliup command not found: {upload_cmd[0]}")

    result = run(upload_cmd, check=False)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
