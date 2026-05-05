"""
Adapted for this repository's local workflow.
Based on: https://github.com/jiayuqi7813/video-Zebra-china
"""

import json
import os
import sys
import urllib.error
import urllib.request


DEFAULT_SPEAKERS = [
    "zh_female_qingxin",
    "zh_female_roumeinvyou",
    "zh_female_wanwanxiaohe",
    "zh_male_qingshuang",
    "zh_male_haoyang",
    "zh_male_beijingxiaoye",
]

DEFAULT_RESOURCES = [
    "volc.service_type.10029",
    "volc.tts_async.default",
]


def split_csv(value: str | None, defaults: list[str]) -> list[str]:
    if not value:
        return defaults[:]
    parts = [item.strip() for item in value.split(",")]
    return [item for item in parts if item]


def test_tts(resource_id: str, speaker: str, api_key: str) -> tuple[str, str]:
    body = json.dumps(
        {
            "req_params": {
                "text": "你好，这是测试。",
                "speaker": speaker,
                "audio_params": {
                    "format": "wav",
                    "sample_rate": 24000,
                },
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
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ("ERR", f"http={exc.code} raw={raw}")
        header = payload.get("header", {})
        return ("ERR", f"code={header.get('code')} message={header.get('message')}")
    except Exception as exc:  # noqa: BLE001
        return ("ERR", repr(exc))

    code = payload.get("code")
    message = payload.get("message", "")
    if code in (0, 20000000):
        return ("OK", f"code={code} message={message}")
    return ("ERR", f"code={code} message={message}")


def main() -> int:
    api_key = os.environ.get("VOLCENGINE_TTS_API_KEY", "").strip()
    if not api_key:
        print("Missing VOLCENGINE_TTS_API_KEY", file=sys.stderr)
        return 1

    speakers = split_csv(os.environ.get("VOLC_PROBE_SPEAKERS"), DEFAULT_SPEAKERS)
    resources = split_csv(os.environ.get("VOLC_PROBE_RESOURCES"), DEFAULT_RESOURCES)

    found = False
    for resource_id in resources:
        for speaker in speakers:
            status, detail = test_tts(resource_id, speaker, api_key)
            print(
                json.dumps(
                    {
                        "resource_id": resource_id,
                        "speaker": speaker,
                        "status": status,
                        "detail": detail,
                    },
                    ensure_ascii=False,
                )
            )
            if status == "OK":
                found = True

    return 0 if found else 2


if __name__ == "__main__":
    raise SystemExit(main())
