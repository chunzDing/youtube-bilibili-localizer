"""
Adapted for this repository's local workflow.
Based on: https://github.com/jiayuqi7813/video-Zebra-china
"""

import json
import sys
from pathlib import Path

import argostranslate.package
import argostranslate.translate


def format_srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def clean_translation(text: str) -> str:
    return " ".join((text or "").strip().split())


def ensure_argos_en_to_zh():
    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed if lang.code == "en"), None)
    to_lang = next((lang for lang in installed if lang.code == "zh"), None)
    if from_lang and to_lang:
        return from_lang.get_translation(to_lang)

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
        raise RuntimeError("Missing Argos English to Chinese package")

    download_path = package.download()
    argostranslate.package.install_from_path(download_path)

    installed = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed if lang.code == "en"), None)
    to_lang = next((lang for lang in installed if lang.code == "zh"), None)
    if not from_lang or not to_lang:
        raise RuntimeError("Failed to install Argos English to Chinese package")
    return from_lang.get_translation(to_lang)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: translate_transcript_to_zh.py <transcript.json> <translated_segments.json> <subtitles.zh.srt>")
        return 1

    transcript_path = Path(sys.argv[1])
    translated_path = Path(sys.argv[2])
    srt_path = Path(sys.argv[3])

    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments = payload["segments"] if isinstance(payload, dict) else payload

    translator = ensure_argos_en_to_zh()
    pending = [seg for seg in segments if not (seg.get("translated_text") or "").strip()]
    total = len(pending)

    for index, seg in enumerate(pending, start=1):
        source_text = seg.get("text", "").strip()
        translated_text = translator.translate(source_text) if source_text else ""
        seg["translated_text"] = clean_translation(translated_text)
        if index % 25 == 0 or index == total:
            print(f"translated {index}/{total}", flush=True)

    translated_path.write_text(
        json.dumps({"segments": segments}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8-sig",
    )

    lines = []
    for idx, seg in enumerate(segments, start=1):
        subtitle_text = (seg.get("translated_text") or seg.get("text") or "").strip()
        if not subtitle_text:
            continue
        lines.extend(
            [
                str(idx),
                f"{format_srt_timestamp(float(seg['start']))} --> {format_srt_timestamp(float(seg['end']))}",
                subtitle_text,
                "",
            ]
        )

    srt_path.write_text("\n".join(lines), encoding="utf-8-sig")
    print(str(translated_path))
    print(str(srt_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
