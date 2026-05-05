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

from bilibili_auth import ensure_biliup_cookie_path, resolve_skill_root
from translation_utils import (
    LoadedGlossary,
    clean_title_text,
    default_glossary_path,
    load_glossary,
    normalize_language_code,
)


TITLE_PREFIX = "【中文字幕】"
DEFAULT_TAGS = "中文字幕,翻译,搬运"
DEFAULT_TID_FALLBACK = 36
TID_ENV_VAR = "BILIBILI_DEFAULT_TID"
SUBTITLE_SAMPLE_LIMIT = 20
CATEGORY_PRIORITY = [171, 188, 160, 36]
CATEGORY_UPLOAD_TID_MAP = {
    188: 231,
    36: 122,
    160: 21,
    171: 171,
}
CATEGORY_UPLOAD_INFO = {
    231: {"name": "计算机技术", "parent_tid": 188, "parent_name": "科技"},
    122: {"name": "野生技能协会", "parent_tid": 36, "parent_name": "知识"},
    21: {"name": "日常", "parent_tid": 160, "parent_name": "生活"},
    171: {"name": "电子竞技", "parent_tid": 171, "parent_name": "电子竞技"},
}
CATEGORY_RULES = {
    188: {
        "name": "科技",
        "keywords": [
            "ai",
            "artificial intelligence",
            "人工智能",
            "llm",
            "gpt",
            "claude",
            "agent",
            "ai agent",
            "vibe coding",
            "coding",
            "code",
            "programming",
            "编程",
            "开发",
            "software",
            "app",
            "website",
            "saas",
            "tool",
            "workflow",
            "automation",
            "prompt",
            "cursor",
            "base44",
        ],
    },
    36: {
        "name": "知识",
        "keywords": [
            "tutorial",
            "guide",
            "course",
            "lesson",
            "explained",
            "how to",
            "tips",
            "beginner",
            "入门",
            "教程",
            "教学",
            "讲解",
            "科普",
            "总结",
            "复盘",
            "清单",
        ],
    },
    160: {
        "name": "生活",
        "keywords": [
            "vlog",
            "daily",
            "routine",
            "desk setup",
            "study with me",
            "room tour",
            "开箱",
            "日常",
            "生活",
            "通勤",
            "居家",
            "学习记录",
            "桌搭",
        ],
    },
    171: {
        "name": "电子竞技",
        "keywords": [
            "esports",
            "电竞",
            "league of legends",
            "lol",
            "valorant",
            "dota",
            "cs2",
            "counter-strike",
            "apex",
            "overwatch",
            "英雄联盟",
            "无畏契约",
            "刀塔",
            "反恐精英",
            "赛事",
            "战队",
            "比赛",
            "ranked",
            "scrim",
            "patch",
        ],
    },
}


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
    return resolve_skill_root(__file__)


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
            raise TranslationFailure(f"Offline title translation currently supports only en->zh, got {normalized_source}->zh")
        raise TranslationFailure("Offline title translation requires source language detection or an explicit --source-language en")

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


def translate_title_api(title: str, source_language: str | None, glossary: LoadedGlossary) -> str:
    try:
        from volcenginesdktranslate20250301 import TranslateTextRequest
    except ImportError as exc:
        raise TranslationFailure("volcengine-python-sdk is required for title translation") from exc

    api = create_volc_translate_api()
    prepared_title, placeholders = glossary.protect_text(title)
    try:
        response = api.translate_text(
            TranslateTextRequest(
                source_language=source_language,
                target_language="zh",
                text_list=[prepared_title],
            )
        )
    except Exception as exc:
        raise TranslationFailure(str(exc)) from exc

    translations = getattr(response, "translation_list", None) or []
    if not translations:
        raise TranslationFailure("Volcengine title translation returned no text")
    translated = str(translations[0].translation or "").strip()
    return clean_title_text(glossary.normalize_translation(translated, placeholders))


def translate_title_offline(title: str, source_language: str | None, glossary: LoadedGlossary) -> str:
    translator = ensure_argos_title_translation(source_language)
    prepared_title, placeholders = glossary.protect_text(title)
    translated = str(translator.translate(prepared_title) if prepared_title else "").strip()
    if not translated:
        raise TranslationFailure("Offline title translation returned no text")
    return clean_title_text(glossary.normalize_translation(translated, placeholders))


def translate_title(
    title: str,
    source_language: str | None,
    translation_mode: str,
    glossary: LoadedGlossary,
) -> tuple[str, dict[str, Any]]:
    if translation_mode == "offline":
        translated = translate_title_offline(title, source_language, glossary)
        return translated, {
            "translation_mode_requested": translation_mode,
            "title_translation_mode_used": "offline",
            "title_translation_fallback_used": False,
            "title_translation_fallback_reason": "",
        }

    try:
        translated = translate_title_api(title, source_language, glossary)
        return translated, {
            "translation_mode_requested": translation_mode,
            "title_translation_mode_used": "api",
            "title_translation_fallback_used": False,
            "title_translation_fallback_reason": "",
        }
    except TranslationFailure as exc:
        fallback_reason = str(exc)
        print(f"! API title translation failed; falling back to offline translation: {fallback_reason}", flush=True)
        translated = translate_title_offline(title, source_language, glossary)
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


def run_localizer(args: argparse.Namespace, python_exe: str, workdir: Path, input_value: str) -> None:
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
        "--translation-quality",
        args.translation_quality,
        "--subtitle-layout",
        args.subtitle_layout,
        "--voice",
        args.voice,
        "--background-volume",
        str(args.background_volume),
    ]
    if args.glossary_file:
        cmd.extend(["--glossary-file", args.glossary_file])
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


def normalize_category_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def keyword_in_text(text: str, keyword: str) -> bool:
    normalized_text = normalize_category_text(text)
    normalized_keyword = normalize_category_text(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9\s\-\+]*", normalized_keyword):
        pattern = r"(?<![a-z0-9])" + re.escape(normalized_keyword).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
        return bool(re.search(pattern, normalized_text))
    return normalized_keyword in normalized_text


def collect_category_matches(text: str, keywords: list[str]) -> list[str]:
    matches: list[str] = []
    for keyword in keywords:
        if keyword_in_text(text, keyword):
            matches.append(keyword)
    return matches


def load_subtitle_sample_text(workdir: Path, limit: int = SUBTITLE_SAMPLE_LIMIT) -> str:
    translated_segments_path = workdir / "translated_segments.json"
    if not translated_segments_path.exists():
        return ""

    payload = json.loads(translated_segments_path.read_text(encoding="utf-8"))
    segments = payload.get("segments") or []
    parts: list[str] = []
    for item in segments[:limit]:
        if not isinstance(item, dict):
            continue
        for field_name in ("text", "translated_text"):
            value = str(item.get(field_name) or "").strip()
            if value:
                parts.append(value)
    return "\n".join(parts)


def score_category_candidates(
    title: str,
    tags: str,
    desc: str,
    subtitle_sample: str,
) -> dict[int, dict[str, Any]]:
    source_text = {
        "title": title,
        "tags": tags,
        "desc": desc,
        "subtitles": subtitle_sample,
    }
    source_weights = {
        "title": 3,
        "tags": 2,
        "desc": 1,
        "subtitles": 1,
    }
    results: dict[int, dict[str, Any]] = {}
    for tid, config in CATEGORY_RULES.items():
        score = 0
        matches_by_source: dict[str, list[str]] = {}
        for source_name, text in source_text.items():
            matches = sorted(dict.fromkeys(collect_category_matches(text, config["keywords"])))
            if matches:
                matches_by_source[source_name] = matches
                score += len(matches) * source_weights[source_name]
        results[tid] = {
            "tid": tid,
            "name": config["name"],
            "score": score,
            "matches": matches_by_source,
        }
    return results


def format_tid_reason(score_entry: dict[str, Any]) -> str:
    parts: list[str] = []
    for source_name in ("title", "tags", "desc", "subtitles"):
        matches = score_entry["matches"].get(source_name) or []
        if matches:
            parts.append(f"{source_name}: {', '.join(matches)}")
    if not parts:
        return "No category keywords matched"
    return f"Matched {score_entry['name']} keywords; " + "; ".join(parts)


def parse_default_tid_env(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if not normalized.isdigit() or int(normalized) <= 0:
        raise SystemExit(f"{TID_ENV_VAR} must be a positive integer, got: {raw_value}")
    return int(normalized)


def normalize_upload_tid(tid: int) -> dict[str, Any]:
    upload_tid = CATEGORY_UPLOAD_TID_MAP.get(tid, tid)
    upload_info = CATEGORY_UPLOAD_INFO.get(upload_tid, {})
    parent_tid = upload_info.get("parent_tid", upload_tid)
    parent_name = upload_info.get("parent_name") or CATEGORY_RULES.get(parent_tid, {}).get("name", "")
    leaf_name = upload_info.get("name") or CATEGORY_RULES.get(upload_tid, {}).get("name", "")
    return {
        "requested_tid": tid,
        "tid": upload_tid,
        "name": leaf_name,
        "parent_tid": parent_tid,
        "parent_name": parent_name,
    }


def resolve_rule_tid(
    workdir: Path,
    title: str,
    tags: str,
    desc: str,
) -> dict[str, Any]:
    subtitle_sample = load_subtitle_sample_text(workdir)
    scores = score_category_candidates(title, tags, desc, subtitle_sample)
    priority_rank = {tid: index for index, tid in enumerate(CATEGORY_PRIORITY)}
    best = sorted(
        scores.values(),
        key=lambda item: (-item["score"], priority_rank.get(item["tid"], len(CATEGORY_PRIORITY))),
    )[0]
    if best["score"] > 0:
        normalized = normalize_upload_tid(best["tid"])
        return {
            "tid": normalized["tid"],
            "name": normalized["name"],
            "parent_tid": normalized["parent_tid"],
            "parent_name": normalized["parent_name"],
            "source": "rule",
            "reason": (
                f"{format_tid_reason(best)}; upload tid {normalized['tid']} "
                f"({normalized['parent_name']}/{normalized['name']})"
            ),
            "matched_keywords": best["matches"],
        }

    return {}


def resolve_upload_tid(
    args: argparse.Namespace,
    workdir: Path,
    title: str,
    tags: str,
    desc: str,
) -> dict[str, Any]:
    if args.tid:
        normalized = normalize_upload_tid(int(args.tid))
        if normalized["requested_tid"] != normalized["tid"]:
            reason = (
                f"Using explicit --tid {normalized['requested_tid']}; mapped to upload tid "
                f"{normalized['tid']} ({normalized['parent_name']}/{normalized['name']})"
            )
        else:
            reason = f"Using explicit --tid {normalized['tid']}"
        return {
            "tid": normalized["tid"],
            "name": normalized["name"],
            "parent_tid": normalized["parent_tid"],
            "parent_name": normalized["parent_name"],
            "source": "argument",
            "reason": reason,
            "matched_keywords": {},
        }

    rule_resolution = resolve_rule_tid(workdir, title, tags, desc)
    if rule_resolution:
        return rule_resolution

    env_tid = parse_default_tid_env(os.environ.get(TID_ENV_VAR))
    if env_tid is not None:
        normalized = normalize_upload_tid(env_tid)
        return {
            "tid": normalized["tid"],
            "name": normalized["name"],
            "parent_tid": normalized["parent_tid"],
            "parent_name": normalized["parent_name"],
            "source": "environment",
            "reason": (
                f"No category keywords matched; using {TID_ENV_VAR}={env_tid} "
                f"-> upload tid {normalized['tid']} ({normalized['parent_name']}/{normalized['name']})"
            ),
            "matched_keywords": {},
        }

    normalized = normalize_upload_tid(DEFAULT_TID_FALLBACK)
    return {
        "tid": normalized["tid"],
        "name": normalized["name"],
        "parent_tid": normalized["parent_tid"],
        "parent_name": normalized["parent_name"],
        "source": "fallback",
        "reason": (
            f"No category keywords matched; falling back to {DEFAULT_TID_FALLBACK} "
            f"({CATEGORY_RULES[DEFAULT_TID_FALLBACK]['name']}) -> upload tid "
            f"{normalized['tid']} ({normalized['parent_name']}/{normalized['name']})"
        ),
        "matched_keywords": {},
    }


def print_tid_resolution(resolution: dict[str, Any]) -> None:
    category_name = resolution.get("name") or "unknown"
    parent_name = resolution.get("parent_name") or category_name
    print(
        f"Bilibili category resolved: {parent_name}/{category_name} ({resolution['tid']}) "
        f"[source={resolution['source']}]",
        flush=True,
    )
    print(f"TID reason: {resolution['reason']}", flush=True)


def fallback_description(source_url: str | None) -> str:
    if source_url:
        return f"原视频链接: {source_url}"
    return "本视频已完成中文字幕本地化，欢迎观看。"


def resolve_upload_description(
    args: argparse.Namespace,
    *,
    title: str,
    tags: str,
    source_url: str | None,
    workdir: Path,
) -> dict[str, str]:
    if args.desc:
        return {
            "desc": args.desc,
            "source": "argument",
            "reason": "Using explicit --desc",
        }
    return {
        "desc": fallback_description(source_url),
        "source": "fallback",
        "reason": "No explicit --desc provided; using default description fallback",
    }


def build_biliup_command(
    args: argparse.Namespace,
    video_path: Path,
    title: str,
    desc: str,
    source_url: str | None,
    cookie_path: Path | None,
    resolved_tid: int,
) -> list[str]:
    biliup_bin = args.biliup_bin or os.environ.get("BILIUP_BIN") or "biliup"
    cmd = [biliup_bin]
    if cookie_path:
        cmd.extend(["--user-cookie", str(cookie_path)])
    cmd.extend(["upload", str(video_path), "--title", title])

    if desc:
        cmd.extend(["--desc", desc])

    tags = args.tags or DEFAULT_TAGS
    if tags:
        cmd.extend(["--tag", tags])
    cmd.extend(["--tid", str(resolved_tid)])
    if args.copyright:
        cmd.extend(["--copyright", str(args.copyright)])
    cmd.extend(["--is-only-self", str(args.is_only_self)])
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
        "translation_quality_used": translated_payload.get("translation_quality_used", "standard"),
        "glossary_file_used": translated_payload.get("glossary_file_used", ""),
        "segment_refinement_used": bool(translated_payload.get("segment_refinement_used")),
    }


def classify_upload_failure(result: subprocess.CompletedProcess[str]) -> str:
    combined = f"{result.stdout}\n{result.stderr}".lower()
    if "账号未登录" in combined or "not login" in combined or "code: -101" in combined:
        return "Bilibili account is not logged in. Complete biliup login and try again."
    if "no such file" in combined or "cannot find the file" in combined:
        return "The configured biliup cookie path does not exist."
    if "copyright" in combined or "tid" in combined or "参数" in combined:
        return "Bilibili rejected the submission parameters. Check tid, copyright, title, and description."
    return "biliup upload failed."


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
    parser.add_argument("--translation-quality", default="high", choices=["standard", "high"], help="Translation quality mode")
    parser.add_argument("--glossary-file", help="Optional glossary JSON file used to normalize terminology")
    parser.add_argument("--subtitle-layout", default="bilingual", choices=["zh", "bilingual"], help="Subtitle layout for localized output")
    parser.add_argument("--translated-title", help="Override automatic title translation")
    parser.add_argument("--tags", default=DEFAULT_TAGS)
    parser.add_argument("--desc")
    parser.add_argument("--source-url", help="Optional source URL or reference text kept in metadata and used for repost submissions")
    parser.add_argument("--tid", type=int, help="Bilibili category id")
    parser.add_argument("--copyright", type=int, default=1, choices=[1, 2], help="1 original, 2 repost")
    parser.add_argument(
        "--is-only-self",
        type=int,
        default=0,
        choices=[0, 1],
        help="1 saves as only-self/private for manual review, 0 submits publicly",
    )
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

    root = skill_root()
    glossary_path = Path(args.glossary_file).expanduser().resolve() if args.glossary_file else default_glossary_path(root)
    glossary = load_glossary(glossary_path if glossary_path.exists() else None)

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

    original_title = clean_title_text(str(metadata.get("title") or fallback_title(args.input)))
    if args.translated_title:
        translated_title = clean_title_text(args.translated_title)
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
            glossary,
        )
    bilibili_title = TITLE_PREFIX + translated_title

    source_url = args.source_url or (str(metadata.get("webpage_url") or args.input) if is_url(args.input) else None)
    try:
        cookie_path, cookie_source = ensure_biliup_cookie_path(
            args.bili_cookie,
            os.environ.get("BILIUP_COOKIE"),
            root,
            biliup_bin=args.biliup_bin or os.environ.get("BILIUP_BIN"),
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    upload_tags = args.tags or DEFAULT_TAGS
    description_resolution = resolve_upload_description(
        args,
        title=bilibili_title,
        tags=upload_tags,
        source_url=source_url,
        workdir=workdir,
    )
    upload_desc = description_resolution["desc"]
    tid_resolution = resolve_upload_tid(args, workdir, bilibili_title, upload_tags, upload_desc)
    print_tid_resolution(tid_resolution)
    upload_cmd = build_biliup_command(
        args,
        video_path,
        bilibili_title,
        upload_desc,
        source_url,
        cookie_path,
        tid_resolution["tid"],
    )

    publish_metadata = {
        "input": args.input,
        "mode": args.mode,
        "original_title": original_title,
        "translated_title": translated_title,
        "bilibili_title": bilibili_title,
        "source_url": source_url,
        "video_path": str(video_path),
        "subtitles_path": str(workdir / "subtitles.zh.srt"),
        "description_used": upload_desc,
        "description_source": description_resolution["source"],
        "description_reason": description_resolution["reason"],
        "subtitle_layout": args.subtitle_layout,
        "translation_quality_used": subtitle_translation_info.get("translation_quality_used", args.translation_quality),
        "glossary_file_used": subtitle_translation_info.get("glossary_file_used", glossary.source_path),
        "bili_cookie_path_used": str(cookie_path) if cookie_path else "",
        "bili_cookie_source": cookie_source,
        "visibility_used": "private" if args.is_only_self else "public",
        "tid_used": tid_resolution["tid"],
        "tid_source": tid_resolution["source"],
        "tid_reason": tid_resolution["reason"],
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
    if result.returncode != 0:
        raise SystemExit(classify_upload_failure(result))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
