#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from bilibili_auth import (
    build_biliup_cookie_payload,
    default_bili_cookie_path,
    resolve_skill_root,
    save_biliup_cookie_payload,
    validate_biliup_cookie_payload,
    verify_cookie_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a fresh browser window, log in to Bilibili, and export a biliup-compatible cookies file."
    )
    parser.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    parser.add_argument("--cookie-output", help="Output path for the biliup cookies.json file")
    parser.add_argument("--timeout", type=int, default=900, help="Maximum seconds to wait for interactive login")
    return parser.parse_args()


def cookie_output_path(args: argparse.Namespace) -> Path:
    if args.cookie_output:
        return Path(args.cookie_output).expanduser().resolve()
    return default_bili_cookie_path(resolve_skill_root(__file__))


def browser_channel(browser: str) -> str:
    return {"edge": "msedge", "chrome": "chrome"}[browser]


def collect_bilibili_cookies(raw_cookies: list[dict[str, object]]) -> dict[str, str]:
    collected: dict[str, str] = {}
    for item in raw_cookies:
        domain = str(item.get("domain") or "")
        if "bilibili.com" not in domain:
            continue
        name = str(item.get("name") or "").strip()
        value = str(item.get("value") or "").strip()
        if name and value:
            collected[name] = value
    return collected


def main() -> int:
    args = parse_args()
    target_path = cookie_output_path(args)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("playwright is required for the interactive Bilibili login helper") from exc

    print(f"Opening a fresh {args.browser} window for Bilibili login...", flush=True)
    print("Log in completely, then return here and press Enter.", flush=True)

    deadline = time.time() + max(args.timeout, 30)
    with sync_playwright() as playwright:
        browser_type = playwright.chromium
        with tempfile.TemporaryDirectory(prefix="youtube-bilibili-localizer-login-") as user_data_dir:
            context = browser_type.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel=browser_channel(args.browser),
                headless=False,
                viewport={"width": 1440, "height": 960},
            )
            try:
                page = context.new_page()
                page.goto("https://passport.bilibili.com/login", wait_until="domcontentloaded")
                input()
                if time.time() > deadline:
                    raise SystemExit("Timed out waiting for Bilibili login confirmation")
                time.sleep(2)
                raw_cookies = context.cookies(
                    ["https://www.bilibili.com", "https://member.bilibili.com", "https://passport.bilibili.com"]
                )
            finally:
                context.close()

    collected = collect_bilibili_cookies(raw_cookies)
    payload = build_biliup_cookie_payload(collected)
    validate_biliup_cookie_payload(payload)
    ok, message = verify_cookie_payload(payload)
    if not ok:
        raise SystemExit(f"Cookie export failed verification: {message}")

    save_biliup_cookie_payload(target_path, payload)
    print(f"Saved biliup cookie file: {target_path}", flush=True)
    print(f"Login verified: {message}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
