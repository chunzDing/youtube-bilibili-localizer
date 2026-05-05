from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REQUIRED_COOKIE_NAMES = ("SESSDATA", "bili_jct", "DedeUserID")
DEFAULT_COOKIE_DOMAINS = [
    ".bilibili.com",
    ".biligame.com",
    ".bigfun.cn",
    ".bigfunapp.cn",
    ".dreamcast.hk",
]


def resolve_skill_root(from_file: str | Path) -> Path:
    return Path(from_file).resolve().parents[1]


def default_biliup_login_path(skill_root: Path) -> Path:
    return skill_root / "cookies.json"


def default_bili_cookie_path(skill_root: Path) -> Path:
    return skill_root / ".auth" / "bilibili.cookies.json"


def resolve_bili_cookie_path(
    explicit_path: str | None,
    env_path: str | None,
    skill_root: Path,
) -> tuple[Path | None, str]:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve(), "argument"
    if env_path:
        return Path(env_path).expanduser().resolve(), "environment"
    default_path = default_biliup_login_path(skill_root)
    if default_path.exists():
        return default_path, "default_formal"
    return None, ""


def default_biliup_bin(skill_root: Path) -> str:
    win_biliup = skill_root / ".venv" / "Scripts" / "biliup.exe"
    posix_biliup = skill_root / ".venv" / "bin" / "biliup"
    if win_biliup.exists():
        return str(win_biliup)
    if posix_biliup.exists():
        return str(posix_biliup)
    return "biliup"


def build_cookie_header(payload: dict[str, Any]) -> str:
    cookies = payload.get("cookie_info", {}).get("cookies", [])
    parts = []
    for item in cookies:
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if name and value:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def build_biliup_cookie_payload(
    cookies: dict[str, str],
    *,
    domains: list[str] | None = None,
) -> dict[str, Any]:
    cookie_entries: list[dict[str, Any]] = []
    for name in REQUIRED_COOKIE_NAMES:
        value = str(cookies.get(name, "")).strip()
        if not value:
            continue
        cookie_entries.append(
            {
                "name": name,
                "value": value,
                "http_only": 1 if name == "SESSDATA" else 0,
                "expires": 0,
                "secure": 0,
            }
        )

    for name, value in cookies.items():
        if name in REQUIRED_COOKIE_NAMES:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        cookie_entries.append(
            {
                "name": name,
                "value": normalized,
                "http_only": 0,
                "expires": 0,
                "secure": 0,
            }
        )

    mid_raw = str(cookies.get("DedeUserID", "")).strip()
    try:
        mid = int(mid_raw)
    except ValueError:
        mid = 0

    return {
        "is_new": False,
        "mid": mid,
        "access_token": "",
        "refresh_token": "",
        "expires_in": 0,
        "token_info": {
            "mid": mid,
            "access_token": "",
            "refresh_token": "",
            "expires_in": 0,
            "region": "CN",
            "store_region": "CN",
        },
        "cookie_info": {
            "cookies": cookie_entries,
            "domains": domains or DEFAULT_COOKIE_DOMAINS,
        },
        "sso": [
            "https://passport.bilibili.com/api/v2/sso",
            "https://passport.biligame.com/api/v2/sso",
            "https://passport.bigfunapp.cn/api/v2/sso",
        ],
        "hint": "",
    }


def validate_biliup_cookie_payload(payload: dict[str, Any]) -> list[str]:
    cookies = payload.get("cookie_info", {}).get("cookies")
    if not isinstance(cookies, list):
        raise ValueError("Invalid biliup cookie payload: missing cookie_info.cookies")
    available = {
        str(item.get("name") or "").strip(): str(item.get("value") or "").strip()
        for item in cookies
        if isinstance(item, dict)
    }
    missing = [name for name in REQUIRED_COOKIE_NAMES if not available.get(name)]
    if missing:
        raise ValueError(f"Missing required Bilibili cookies: {', '.join(missing)}")
    return missing


def save_biliup_cookie_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_biliup_cookie_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_formal_biliup_login_payload(payload: dict[str, Any]) -> bool:
    token_info = payload.get("token_info")
    if not isinstance(token_info, dict):
        return False
    access_token = str(token_info.get("access_token") or payload.get("access_token") or "").strip()
    refresh_token = str(token_info.get("refresh_token") or payload.get("refresh_token") or "").strip()
    return bool(access_token and refresh_token)


def verify_cookie_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    cookie_header = build_cookie_header(payload)
    if not cookie_header:
        return False, "cookie header is empty"

    request = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={
            "Cookie": cookie_header,
            "Referer": "https://www.bilibili.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {body}"
    except Exception as exc:
        return False, str(exc)

    if payload.get("code") != 0:
        return False, str(payload)
    data = payload.get("data") or {}
    if not data.get("isLogin"):
        return False, "Bilibili returned isLogin=false"
    uname = str(data.get("uname") or "").strip()
    return True, uname or "login verified"


def start_biliup_login(
    skill_root: Path,
    *,
    target_path: Path | None = None,
    biliup_bin: str | None = None,
) -> Path:
    login_path = (target_path or default_biliup_login_path(skill_root)).expanduser().resolve()
    login_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        biliup_bin or default_biliup_bin(skill_root),
        "--user-cookie",
        str(login_path),
        "login",
    ]
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(command, cwd=str(skill_root), creationflags=creationflags)
    return login_path


def ensure_biliup_cookie_path(
    explicit_path: str | None,
    env_path: str | None,
    skill_root: Path,
    *,
    biliup_bin: str | None = None,
) -> tuple[Path, str]:
    cookie_path, source = resolve_bili_cookie_path(explicit_path, env_path, skill_root)
    login_path = default_biliup_login_path(skill_root).resolve()

    if cookie_path is None:
        launched = start_biliup_login(skill_root, target_path=login_path, biliup_bin=biliup_bin)
        raise RuntimeError(
            "No formal biliup login was found. "
            f"Opened a biliup login window; complete login and rerun. Target file: {launched}"
        )

    cookie_path = cookie_path.resolve()
    if not cookie_path.exists():
        if source in {"default_formal", ""}:
            launched = start_biliup_login(skill_root, target_path=login_path, biliup_bin=biliup_bin)
            raise RuntimeError(
                "The formal biliup login file is missing. "
                f"Opened a biliup login window; complete login and rerun. Target file: {launched}"
            )
        raise RuntimeError(f"Bilibili cookie file not found: {cookie_path}")

    try:
        payload = load_biliup_cookie_payload(cookie_path)
    except Exception as exc:
        if source == "default_formal":
            launched = start_biliup_login(skill_root, target_path=login_path, biliup_bin=biliup_bin)
            raise RuntimeError(
                "The formal biliup login file could not be read. "
                f"Opened a biliup login window; complete login and rerun. Target file: {launched}"
            ) from exc
        raise RuntimeError(f"Failed to read Bilibili cookie file: {cookie_path}") from exc

    validate_biliup_cookie_payload(payload)
    is_formal = is_formal_biliup_login_payload(payload)
    is_valid, message = verify_cookie_payload(payload)

    if is_formal and is_valid:
        return cookie_path, source

    if source == "default_formal":
        launched = start_biliup_login(skill_root, target_path=login_path, biliup_bin=biliup_bin)
        reason = "expired or invalid" if is_formal else "not a formal biliup login state"
        raise RuntimeError(
            f"The formal biliup login is {reason} ({message}). "
            f"Opened a biliup login window; complete login and rerun. Target file: {launched}"
        )

    if is_valid:
        return cookie_path, source

    raise RuntimeError(f"Bilibili cookie file is invalid: {message}")
