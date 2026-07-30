#!/usr/bin/env python3
"""
GPU Utilization Card (WakaTime -> README)
-----------------------------------------
WakaTime 최근 7일 통계를 끌어와 'AI 워크스테이션 상태창'으로 번역해서
README.md 의 마커 사이를 갈아끼운다.

데이터 소스 (둘 중 하나만 있으면 됨):
  1) WAKATIME_API_KEY  : 비공개. Basic auth 로 /users/current/stats/last_7_days 호출
  2) WAKATIME_SHARE_URL: 공개 share embed JSON URL (키 없이 사용 가능)
  둘 다 없으면 데모 데이터로 렌더링한다 (로컬 미리보기용).

주간 목표 시간은 WEEKLY_TARGET_HOURS 로 조절.
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START = "<!-- CODING_TIME:START -->"
END = "<!-- CODING_TIME:END -->"

KST = timezone(timedelta(hours=9))
WEEKLY_TARGET_HOURS = float(os.getenv("WEEKLY_TARGET_HOURS", "40"))
BAR_WIDTH = 18
TOP_N = 4

DEMO = {
    "total_seconds": 152280,
    "languages": [
        {"name": "Python", "percent": 61.4, "text": "25 hrs 58 mins"},
        {"name": "CUDA", "percent": 14.2, "text": "6 hrs 1 min"},
        {"name": "YAML", "percent": 11.9, "text": "5 hrs 2 mins"},
        {"name": "Markdown", "percent": 7.3, "text": "3 hrs 5 mins"},
        {"name": "Bash", "percent": 5.2, "text": "2 hrs 12 mins"},
    ],
    "best_day": {"date": "2026-07-28", "text": "9 hrs 12 mins"},
}


def _get_json(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "readme-live-status")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_stats() -> tuple[dict, str]:
    """(stats, source) 반환. 실패 시 데모 데이터."""
    key = os.getenv("WAKATIME_API_KEY")
    share = os.getenv("WAKATIME_SHARE_URL")
    try:
        if key:
            token = base64.b64encode(key.encode()).decode()
            data = _get_json(
                "https://wakatime.com/api/v1/users/current/stats/last_7_days",
                {"Authorization": f"Basic {token}"},
            )
            return data.get("data", {}), "wakatime-api"
        if share:
            data = _get_json(share)
            return {"languages": data.get("data", [])}, "wakatime-share"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        print(f"[warn] WakaTime 호출 실패 -> 데모 데이터 사용: {exc}")
        return DEMO, "demo (fetch failed)"
    print("[warn] WakaTime 자격정보 없음 -> 데모 데이터 사용")
    return DEMO, "demo (no credentials)"


def bar(pct: float, width: int = BAR_WIDTH) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = round(width * pct / 100)
    return "█" * filled + "░" * (width - filled)


def parse_hours(stats: dict) -> float:
    if stats.get("total_seconds"):
        return stats["total_seconds"] / 3600
    # share embed 에는 총합이 없어서 언어별 시간을 합산
    total = 0.0
    for lang in stats.get("languages", []):
        total += lang.get("total_seconds", 0) / 3600
    return total


def humanize(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    return f"{h}h {m:02d}m"


def build_card(stats: dict, source: str) -> str:
    langs = stats.get("languages", [])[:TOP_N]
    total_h = parse_hours(stats)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    if not langs:
        return "_WakaTime 데이터가 아직 없습니다._"

    width = max(len(l.get("name", "?")) for l in langs)
    rows = []
    for lang in langs:
        pct = float(lang.get("percent", 0))
        text = lang.get("text") or humanize(lang.get("total_seconds", 0) / 3600)
        rows.append(f"{lang.get('name', '?'):<{width}}  {bar(pct)}  {pct:5.1f}%  {text}")

    rows.append("-" * max(len(r) for r in rows))
    rows.append(f"{'Total':<{width}}  {humanize(total_h)}  (last 7 days)")

    body = "\n".join(["```", *rows, "```"])
    if source.startswith("demo"):
        body += "\n<sub>demo data — WAKATIME_API_KEY 미설정</sub>"
    else:
        body += f"\n<sub>updated {now} · via WakaTime</sub>"
    return body


def inject(card: str) -> None:
    if not README.exists():
        README.write_text(
            f"# README\n\n{START}\n{END}\n", encoding="utf-8"
        )
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(
            f"README.md 에 마커가 없습니다. 다음 두 줄을 넣어주세요:\n{START}\n{END}"
        )
    new = re.sub(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        f"{START}\n{card}\n{END}",
        text,
        flags=re.DOTALL,
    )
    README.write_text(new, encoding="utf-8")


def main() -> None:
    stats, source = fetch_stats()
    card = build_card(stats, source)
    inject(card)
    print(card)


if __name__ == "__main__":
    main()