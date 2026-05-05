#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, TypeVar


T = TypeVar("T")
_CUDA_DLL_HANDLES: list[Any] = []


@dataclass
class Segment:
    start: float
    end: float
    text: str
    translated_text: str = ""


class TranslationFailure(RuntimeError):
    pass


def run(cmd: list[str], *, capture: bool = False) -> str | None:
    print("+", " ".join(cmd))
    if capture:
        completed = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return completed.stdout.strip()
    subprocess.run(cmd, check=True)
    return None


def require_command(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise SystemExit(f"Missing required command: {name}")
    return resolved


def is_youtube_input(value: str) -> bool:
    lowered = value.lower()
    return "youtube.com/" in lowered or "youtu.be/" in lowered


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def configure_windows_cuda_dll_paths() -> None:
    if os.name != "nt":
        return

    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    candidate_dirs = [
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cudnn" / "bin",
        site_packages / "ctranslate2",
    ]
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    for candidate in candidate_dirs:
        if not candidate.is_dir():
            continue
        candidate_str = str(candidate)
        try:
            _CUDA_DLL_HANDLES.append(os.add_dll_directory(candidate_str))
        except (AttributeError, FileNotFoundError):
            pass
        if candidate_str not in path_parts:
            path_parts.insert(0, candidate_str)
    os.environ["PATH"] = os.pathsep.join(path_parts)


def normalize_language_code(language: str | None) -> str | None:
    if not language:
        return None
    return language.strip().lower().replace("_", "-").split("-", 1)[0] or None


def format_srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def load_segments_from_json(path: Path) -> list[Segment]:
    payload = read_json(path)
    raw_segments: Iterable[dict]
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        raw_segments = payload["segments"]
    elif isinstance(payload, list):
        raw_segments = payload
    else:
        raise SystemExit("Unsupported transcript JSON format")

    segments: list[Segment] = []
    for item in raw_segments:
        start = float(item["start"])
        end = float(item["end"])
        text = str(item.get("text") or item.get("source_text") or "").strip()
        translated = str(
            item.get("translated_text") or item.get("translation") or ""
        ).strip()
        if not text:
            continue
        segments.append(Segment(start=start, end=end, text=text, translated_text=translated))
    if not segments:
        raise SystemExit("Transcript JSON did not contain usable segments")
    return segments


def ensure_source_video(
    input_value: str,
    workdir: Path,
    *,
    cookies_from_browser: str | None,
    cookies_path: str | None,
    yt_dlp_impersonate: str | None,
) -> Path:
    if is_youtube_input(input_value):
        require_command("yt-dlp")
        target = workdir / "source.%(ext)s"
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--merge-output-format",
            "mp4",
        ]
        if cookies_from_browser:
            cmd.extend(["--cookies-from-browser", cookies_from_browser])
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
        if yt_dlp_impersonate:
            cmd.extend(["--impersonate", yt_dlp_impersonate])
        cmd.extend(["-o", str(target), input_value])
        run(cmd)
        matches = sorted(workdir.glob("source.*"))
        if not matches:
            raise SystemExit("yt-dlp did not produce a source video")
        return matches[0]

    source = Path(input_value).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Input video does not exist: {source}")
    target = workdir / f"source{source.suffix or '.mp4'}"
    if source != target:
        shutil.copy2(source, target)
    return target


def extract_audio(video_path: Path, output_path: Path) -> None:
    require_command("ffmpeg")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def transcribe_with_faster_whisper(
    audio_path: Path,
    *,
    model_name: str,
    device: str,
    compute_type: str,
    language: str | None,
) -> tuple[list[Segment], str | None]:
    configure_windows_cuda_dll_paths()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "faster-whisper is not installed. Install it or pass --transcript-json."
        ) from exc

    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )

    results: list[Segment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        results.append(Segment(start=float(segment.start), end=float(segment.end), text=text))
    if not results:
        raise SystemExit("Transcription produced no segments")
    detected_language = normalize_language_code(getattr(_info, "language", None))
    return results, detected_language


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def env_required_for_translation(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise TranslationFailure(f"Missing required environment variable: {name}")
    return value


def create_volc_translate_api():
    try:
        from volcenginesdkcore import ApiClient, Configuration
        from volcenginesdktranslate20250301 import TRANSLATE20250301Api
    except ImportError as exc:
        raise TranslationFailure(
            "volcengine-python-sdk is not installed in the current environment"
        ) from exc

    configuration = Configuration()
    configuration.ak = env_required_for_translation("VOLCENGINE_ACCESS_KEY")
    configuration.sk = env_required_for_translation("VOLCENGINE_SECRET_KEY")
    configuration.region = os.environ.get("VOLCENGINE_REGION", "cn-north-1").strip() or "cn-north-1"
    return TRANSLATE20250301Api(ApiClient(configuration))


def chunked(items: list[T], size: int) -> Iterable[list[T]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def ensure_argos_translation(source_language: str | None, target_language: str) -> Any:
    normalized_source = normalize_language_code(source_language)
    normalized_target = normalize_language_code(target_language)
    if normalized_target != "zh":
        raise TranslationFailure("Offline translation currently supports only zh as the target language")
    if normalized_source != "en":
        if normalized_source:
            raise TranslationFailure(
                f"Offline translation currently supports only en->zh, got {normalized_source}->{normalized_target}"
            )
        raise TranslationFailure(
            "Offline translation requires source language detection or an explicit --source-language en"
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
        raise TranslationFailure("Could not find an Argos en->zh package")

    download_path = package.download()
    argostranslate.package.install_from_path(download_path)

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed if lang.code == "en"), None)
    to_lang = next((lang for lang in installed if lang.code == "zh"), None)
    if not from_lang or not to_lang:
        raise TranslationFailure("Argos en->zh package installation did not complete successfully")
    translation = from_lang.get_translation(to_lang)
    if not translation:
        raise TranslationFailure("Argos en->zh translation is unavailable after installation")
    return translation


def translate_segments_api(
    segments: list[Segment],
    source_language: str | None,
    target_language: str,
    batch_size: int,
) -> None:
    try:
        from volcenginesdktranslate20250301 import TranslateTextRequest
    except ImportError as exc:
        raise TranslationFailure(
            "volcengine-python-sdk is required for translation"
        ) from exc

    untranslated = [segment for segment in segments if not segment.translated_text]
    if not untranslated:
        return
    if batch_size > 16:
        raise TranslationFailure("Volcengine TranslateText accepts at most 16 texts per request")

    translate_api = create_volc_translate_api()
    index_by_id = {index: segment for index, segment in enumerate(untranslated)}
    try:
        for batch_indexes in chunked(list(index_by_id.keys()), batch_size):
            response = translate_api.translate_text(
                TranslateTextRequest(
                    source_language=source_language,
                    target_language=target_language,
                    text_list=[index_by_id[index].text for index in batch_indexes],
                )
            )
            translations = response.translation_list or []
            if len(translations) != len(batch_indexes):
                raise TranslationFailure(
                    f"Volcengine translation returned {len(translations)} items for {len(batch_indexes)} inputs"
                )
            for position, batch_index in enumerate(batch_indexes):
                translated_text = str(translations[position].translation or "").strip()
                if not translated_text:
                    raise TranslationFailure(f"Empty translation returned for segment {batch_index}")
                index_by_id[batch_index].translated_text = translated_text
    except TranslationFailure:
        raise
    except Exception as exc:
        raise TranslationFailure(str(exc)) from exc


def translate_segments_offline(
    segments: list[Segment],
    source_language: str | None,
    target_language: str,
) -> None:
    untranslated = [segment for segment in segments if not segment.translated_text]
    if not untranslated:
        return

    translator = ensure_argos_translation(source_language, target_language)
    for segment in untranslated:
        text = segment.text.strip()
        translated_text = str(translator.translate(text) if text else "").strip()
        if not translated_text:
            raise TranslationFailure("Offline translation returned an empty subtitle line")
        segment.translated_text = " ".join(translated_text.split())


def translate_segments(
    segments: list[Segment],
    source_language: str | None,
    target_language: str,
    batch_size: int,
    translation_mode: str,
) -> dict[str, Any]:
    requested_mode = translation_mode

    if requested_mode == "offline":
        translate_segments_offline(segments, source_language, target_language)
        return {
            "translation_mode_requested": requested_mode,
            "translation_mode_used": "offline",
            "translation_fallback_used": False,
            "translation_fallback_reason": "",
        }

    try:
        translate_segments_api(segments, source_language, target_language, batch_size)
        return {
            "translation_mode_requested": requested_mode,
            "translation_mode_used": "api",
            "translation_fallback_used": False,
            "translation_fallback_reason": "",
        }
    except TranslationFailure as exc:
        fallback_reason = str(exc)
        print(f"! API translation failed, falling back to offline translation: {fallback_reason}")
        translate_segments_offline(segments, source_language, target_language)
        return {
            "translation_mode_requested": requested_mode,
            "translation_mode_used": "offline",
            "translation_fallback_used": True,
            "translation_fallback_reason": fallback_reason,
        }


def build_subtitle_text(segment: Segment, subtitle_layout: str) -> str:
    translated = " ".join((segment.translated_text or "").split()).strip()
    source = " ".join((segment.text or "").split()).strip()
    if subtitle_layout == "bilingual" and translated and source:
        if translated == source:
            return translated
        return f"{translated}\n{source}"
    return translated or source


def write_srt(path: Path, segments: list[Segment], subtitle_layout: str) -> None:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        subtitle_text = build_subtitle_text(segment, subtitle_layout)
        lines.extend(
            [
                str(index),
                f"{format_srt_timestamp(segment.start)} --> {format_srt_timestamp(segment.end)}",
                subtitle_text,
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def probe_duration(path: Path) -> float:
    require_command("ffprobe")
    output = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture=True,
    )
    if not output:
        raise SystemExit(f"Could not determine duration for {path}")
    return float(output)


def atempo_chain(speedup: float) -> str:
    factors: list[str] = []
    remaining = speedup
    while remaining > 2.0:
        factors.append("atempo=2.0")
        remaining /= 2.0
    factors.append(f"atempo={remaining:.5f}")
    return ",".join(factors)


def maybe_fit_segment_audio(
    audio_path: Path,
    target_duration: float,
    max_speedup: float,
) -> Path:
    actual_duration = probe_duration(audio_path)
    if actual_duration <= 0 or target_duration <= 0:
        return audio_path
    speedup = actual_duration / target_duration
    if speedup <= 1.02:
        return audio_path
    if speedup > max_speedup:
        print(
            f"! keeping long segment audio {audio_path.name}: "
            f"{actual_duration:.2f}s for {target_duration:.2f}s slot"
        )
        return audio_path

    adjusted = audio_path.with_name(f"{audio_path.stem}.fit.wav")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-filter:a",
            atempo_chain(speedup),
            str(adjusted),
        ]
    )
    return adjusted


def synthesize_volc_tts(
    text: str,
    *,
    speaker: str,
    response_format: str,
    sample_rate: int,
) -> bytes:
    api_key = env_required("VOLCENGINE_TTS_API_KEY")
    resource_id = os.environ.get("VOLCENGINE_TTS_RESOURCE_ID", "volc.service_type.10029").strip() or "volc.service_type.10029"
    body = json.dumps(
        {
            "req_params": {
                "text": text,
                "speaker": speaker,
                "audio_params": {
                    "format": response_format,
                    "sample_rate": sample_rate,
                },
                "additions": json.dumps(
                    {
                        "disable_markdown_filter": True,
                        "enable_language_detector": True,
                        "enable_latex_tn": True,
                        "disable_default_bit_rate": True,
                        "max_length_to_filter_parenthesis": 0,
                        "cache_config": {"text_type": 1, "use_cache": True},
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            }
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        data=body,
        headers={
            "x-api-key": api_key,
            "X-Api-Resource-Id": resource_id,
            "Connection": "keep-alive",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Volc TTS request failed ({exc.code}): {body}") from exc

    audio_parts: list[bytes] = []
    final_code: int | None = None
    final_message = ""
    for raw_line in response_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        if parsed.get("data"):
            audio_parts.append(base64.b64decode(parsed["data"]))
        if "code" in parsed:
            final_code = int(parsed["code"])
            final_message = str(parsed.get("message", ""))

    if not audio_parts:
        raise SystemExit("Volc TTS response did not contain audio chunks")
    if final_code not in (0, 20000000):
        raise SystemExit(f"Volc TTS failed: code={final_code}, message={final_message}")
    return b"".join(audio_parts)


def synthesize_tts_segments(
    segments: list[Segment],
    audio_dir: Path,
    *,
    speaker: str,
    response_format: str,
    sample_rate: int,
    max_speedup: float,
) -> list[Path]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for index, segment in enumerate(segments):
        text = (segment.translated_text or "").strip()
        if not text:
            continue
        output_path = audio_dir / f"tts_{index:04d}.{response_format}"
        audio_bytes = synthesize_volc_tts(
            text,
            speaker=speaker,
            response_format=response_format,
            sample_rate=sample_rate,
        )
        output_path.write_bytes(audio_bytes)
        fitted = maybe_fit_segment_audio(
            output_path,
            max(segment.end - segment.start, 0.1),
            max_speedup=max_speedup,
        )
        rendered.append(fitted)
    return rendered


def build_dub_track(segments: list[Segment], rendered_paths: list[Path], output_path: Path) -> None:
    if len(rendered_paths) != len(segments):
        raise SystemExit("Rendered TTS segment count did not match segment count")
    filter_lines: list[str] = []
    mix_inputs: list[str] = []
    cmd = ["ffmpeg", "-y"]
    for path in rendered_paths:
        cmd.extend(["-i", str(path)])
    for index, segment in enumerate(segments):
        delay_ms = max(0, int(math.floor(segment.start * 1000)))
        label = f"a{index}"
        filter_lines.append(f"[{index}:a]adelay={delay_ms}|{delay_ms}[{label}]")
        mix_inputs.append(f"[{label}]")
    filter_lines.append(
        f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest:normalize=0[mix]"
    )
    filter_path = output_path.with_suffix(".filter.txt")
    filter_path.write_text(";\n".join(filter_lines) + "\n", encoding="utf-8")
    cmd.extend(
        [
            "-filter_complex_script",
            str(filter_path),
            "-map",
            "[mix]",
            str(output_path),
        ]
    )
    run(cmd)


def mix_with_original_audio(
    original_audio: Path,
    dub_track: Path,
    output_path: Path,
    background_volume: float,
) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(original_audio),
            "-i",
            str(dub_track),
            "-filter_complex",
            (
                f"[0:a]volume={background_volume:.3f}[bg];"
                "[1:a]volume=1.0[dub];"
                "[bg][dub]amix=inputs=2:duration=longest:normalize=0[mix]"
            ),
            "-map",
            "[mix]",
            str(output_path),
        ]
    )


def escape_subtitle_path(path: Path) -> str:
    escaped = str(path.resolve())
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace(",", "\\,")
    escaped = escaped.replace("'", "\\'")
    return escaped


def export_final_video(
    source_video: Path,
    final_audio: Path,
    subtitles_path: Path,
    output_path: Path,
    burn_subtitles: bool,
) -> None:
    if burn_subtitles:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source_video),
                "-i",
                str(final_audio),
                "-vf",
                f"subtitles='{escape_subtitle_path(subtitles_path)}'",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-shortest",
                str(output_path),
            ]
        )
        return

    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video),
            "-i",
            str(final_audio),
            "-i",
            str(subtitles_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-c:s",
            "mov_text",
            "-shortest",
            str(output_path),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create Chinese subtitles and Mandarin dubbing for a video.")
    parser.add_argument("--input", required=True, help="YouTube URL or local video path")
    parser.add_argument("--workdir", required=True, help="Directory for intermediate and final files")
    parser.add_argument("--transcript-json", help="Existing transcript JSON with segments")
    parser.add_argument("--cookies-from-browser", help="Pass browser cookies to yt-dlp, for example edge or chrome")
    parser.add_argument("--cookies", help="Path to a yt-dlp compatible cookies.txt file")
    parser.add_argument("--yt-dlp-impersonate", help="yt-dlp impersonation target such as edge:windows-10")
    parser.add_argument("--skip-transcription", action="store_true", help="Require --transcript-json instead of transcribing")
    parser.add_argument("--skip-tts", action="store_true", help="Stop after subtitles and do not synthesize dubbing")
    parser.add_argument("--source-language", help="Hint language code for ASR")
    parser.add_argument("--whisper-model", default="small", help="faster-whisper model name")
    parser.add_argument("--whisper-device", default="auto", help="faster-whisper device")
    parser.add_argument("--whisper-compute-type", default="default", help="faster-whisper compute type")
    parser.add_argument("--translation-target-language", default="zh", help="Volcengine translation target language code")
    parser.add_argument("--translation-batch-size", type=int, default=16, help="Volcengine TranslateText batch size, max 16")
    parser.add_argument("--translation-mode", default="api", choices=["api", "offline", "auto"], help="Subtitle translation mode")
    parser.add_argument("--subtitle-layout", default="bilingual", choices=["zh", "bilingual"], help="Subtitle layout: Chinese only or Chinese plus original source text")
    parser.add_argument("--voice", default="zh_female_qingxin", help="Volc TTS speaker name")
    parser.add_argument("--tts-format", default="wav", choices=["mp3", "wav", "aac"], help="Volc TTS output format")
    parser.add_argument("--tts-sample-rate", type=int, default=24000, choices=[8000, 16000, 22050, 24000, 32000, 44100, 48000], help="Volc TTS sample rate")
    parser.add_argument("--background-volume", type=float, default=0.12)
    parser.add_argument("--max-tts-speedup", type=float, default=1.35)
    parser.add_argument("--sidecar-subtitles", action="store_true", help="Embed subtitles as a soft track instead of burning them in")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workdir = Path(args.workdir).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    if not 1 <= args.translation_batch_size <= 16:
        raise SystemExit("--translation-batch-size must be between 1 and 16")

    require_command("ffmpeg")
    require_command("ffprobe")

    source_video = ensure_source_video(
        args.input,
        workdir,
        cookies_from_browser=args.cookies_from_browser,
        cookies_path=args.cookies,
        yt_dlp_impersonate=args.yt_dlp_impersonate,
    )
    source_audio = workdir / "audio.wav"
    extract_audio(source_video, source_audio)

    transcript_path = workdir / "transcript.json"
    if args.transcript_json:
        segments = load_segments_from_json(Path(args.transcript_json).expanduser().resolve())
        write_json(transcript_path, {"segments": [asdict(segment) for segment in segments]})
        detected_language = normalize_language_code(args.source_language)
    elif args.skip_transcription:
        raise SystemExit("--skip-transcription requires --transcript-json")
    else:
        segments, detected_language = transcribe_with_faster_whisper(
            source_audio,
            model_name=args.whisper_model,
            device=args.whisper_device,
            compute_type=args.whisper_compute_type,
            language=args.source_language,
        )
        write_json(transcript_path, {"segments": [asdict(segment) for segment in segments]})

    effective_source_language = normalize_language_code(args.source_language) or detected_language

    translation_info = translate_segments(
        segments,
        effective_source_language,
        args.translation_target_language,
        args.translation_batch_size,
        args.translation_mode,
    )
    translated_path = workdir / "translated_segments.json"
    write_json(
        translated_path,
        {
            "segments": [asdict(segment) for segment in segments],
            "source_language_used": effective_source_language,
            "subtitle_layout_used": args.subtitle_layout,
            **translation_info,
        },
    )

    subtitles_path = workdir / "subtitles.zh.srt"
    write_srt(subtitles_path, segments, args.subtitle_layout)

    if args.skip_tts:
        final_video = workdir / "final.mp4"
        export_final_video(
            source_video,
            source_audio,
            subtitles_path,
            final_video,
            burn_subtitles=not args.sidecar_subtitles,
        )
        print(f"subtitles_only={subtitles_path}")
        print(f"final_video={final_video}")
        return 0

    rendered_paths = synthesize_tts_segments(
        segments,
        workdir / "tts_segments",
        speaker=args.voice,
        response_format=args.tts_format,
        sample_rate=args.tts_sample_rate,
        max_speedup=args.max_tts_speedup,
    )
    if not rendered_paths:
        raise SystemExit("No TTS audio was generated")

    dub_track = workdir / "dub_track.wav"
    build_dub_track(segments, rendered_paths, dub_track)

    final_audio = workdir / "final_audio.wav"
    mix_with_original_audio(
        source_audio,
        dub_track,
        final_audio,
        background_volume=args.background_volume,
    )

    final_video = workdir / "final.mp4"
    export_final_video(
        source_video,
        final_audio,
        subtitles_path,
        final_video,
        burn_subtitles=not args.sidecar_subtitles,
    )

    print(f"source_video={source_video}")
    print(f"subtitles={subtitles_path}")
    print(f"dub_track={dub_track}")
    print(f"final_audio={final_audio}")
    print(f"final_video={final_video}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
