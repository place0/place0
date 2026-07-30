#!/usr/bin/env python3
"""
GitHub Stats -> README
----------------------
GitHub API 에서 실제 활동 데이터를 가져와 README 의 마커 사이를 갈아끼운다.
지어낸 값은 하나도 없다. 가져오지 못한 항목은 표시하지 않는다.

수집 항목
  - 최근 1년 컨트리뷰션 수 / 활동한 날 수 / 현재 연속 일수  (GraphQL)
  - 최근 30일 활동 스파크라인                                (GraphQL)
  - 공개 리포 수, 언어별 실제 코드 비율                      (REST)

환경변수
  GH_USERNAME : 대상 계정 (기본값: 워크플로에서 주입)
  GH_TOKEN    : 토큰. Actions 의 GITHUB_TOKEN 으로도 대부분 동작하지만
                컨트리뷰션 조회가 비면 read:user 권한의 classic PAT 를 쓸 것.
표준 라이브러리만 사용한다 (설치할 의존성 없음).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"

KST = timezone(timedelta(hours=9))
USER = os.getenv("GH_USERNAME", "")
TOKEN = os.getenv("GH_TOKEN", "")
BAR_WIDTH = 18
TOP_LANGS = 5
SPARK = "▁▂▃▄▅▆▇█"

# 세지 않을 언어 (설정 파일류가 비율을 왜곡한다)
SKIP_LANGS = {"HTML", "CSS", "Jupyter Notebook", "Makefile", "Dockerfile"}


def _request(url: str, data: bytes | None = None, auth: bool = True) -> dict:
    req = urllib.request.Request(url, data=data)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "readme-stats")
    if auth and TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def _get_public(url: str) -> dict:
    """공개 데이터 조회. 토큰이 문제면 비인증으로 한 번 더 시도한다."""
    try:
        return _request(url)
    except urllib.error.HTTPError as exc:
        print(f"[warn] 인증 요청 실패({exc.code}) -> 비인증으로 재시도: {url}")
        return _request(url, auth=False)


def fetch_contributions() -> dict | None:
    """최근 1년 컨트리뷰션 캘린더. 실패하면 None (해당 섹션을 아예 생략한다)."""
    if not (USER and TOKEN):
        print("[warn] GH_USERNAME / GH_TOKEN 없음 -> 컨트리뷰션 생략")
        return None
    query = """
    query($login:String!) {
      user(login:$login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }"""
    body = json.dumps({"query": query, "variables": {"login": USER}}).encode()
    try:
        res = _request("https://api.github.com/graphql", body)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[warn] GraphQL 실패 -> 컨트리뷰션 생략: {exc}")
        return None

    if res.get("errors") or not res.get("data", {}).get("user"):
        print(f"[warn] GraphQL 응답 비어있음 -> 컨트리뷰션 생략: {res.get('errors')}")
        return None

    cal = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    today = datetime.now(KST).date().isoformat()
    streak = 0
    for day in reversed(days):
        if day["date"] > today:
            continue
        if day["contributionCount"] > 0:
            streak += 1
        elif day["date"] != today:  # 오늘은 아직 안 했을 수 있으니 봐준다
            break

    return {
        "total": cal["totalContributions"],
        "active_days": sum(1 for d in days if d["contributionCount"] > 0),
        "total_days": len(days),
        "streak": streak,
        "recent": [d["contributionCount"] for d in days if d["date"] <= today][-30:],
    }


def fetch_languages() -> tuple[list[tuple[str, float]], int]:
    """본인 소유 공개 리포의 실제 언어 바이트를 합산한다."""
    if not USER:
        print("[warn] GH_USERNAME 없음 -> 언어 비율 생략")
        return [], 0
    try:
        repos = _get_public(
            f"https://api.github.com/users/{USER}/repos"
            "?per_page=100&type=owner&sort=updated"
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[warn] 리포 목록 실패: {exc}")
        return [], 0

    repos = [r for r in repos if not r.get("fork") and not r.get("archived")]
    totals: dict[str, int] = {}
    for repo in repos[:40]:  # rate limit 보호
        try:
            langs = _get_public(repo["languages_url"])
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        for name, size in langs.items():
            if name not in SKIP_LANGS:
                totals[name] = totals.get(name, 0) + size

    grand = sum(totals.values())
    if not grand:
        return [], len(repos)
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:TOP_LANGS]
    return [(n, s / grand * 100) for n, s in ranked], len(repos)


def sparkline(values: list[int]) -> str:
    if not values:
        return ""
    peak = max(values)
    if peak == 0:
        return SPARK[0] * len(values)
    return "".join(SPARK[min(7, round(v / peak * 7))] for v in values)


def center_block(lines: list[str]) -> str:
    """모든 줄을 같은 길이로 패딩한 뒤 가운데 정렬 pre 로 감싼다.
    길이를 맞춰야 줄마다 따로 중앙 정렬돼도 열이 어긋나지 않는다."""
    width = max(len(line) for line in lines)
    padded = [line.ljust(width) for line in lines]
    return '<div align="center">\n<pre>\n' + "\n".join(padded) + "</pre>\n</div>"


def bar(pct: float) -> str:
    filled = round(BAR_WIDTH * pct / 100)
    return "▰" * filled + "▱" * (BAR_WIDTH - filled)


def build_block() -> str:
    contrib = fetch_contributions()
    langs, repo_count = fetch_languages()
    parts: list[str] = []

    if contrib:
        parts.append(center_block([f"last 30 days  {sparkline(contrib['recent'])}"]))

    if langs:
        width = max(len(n) for n, _ in langs)
        parts.append(
            center_block(
                [f"{name:<{width}}  {bar(pct)}  {pct:5.1f}%" for name, pct in langs]
            )
        )

    if not parts:
        print("[error] 컨트리뷰션/언어 모두 실패 — 위의 warn 로그를 확인하세요")
        return ('<p align="center"><em>통계를 가져오지 못했습니다. '
                'Actions 로그를 확인하세요.</em></p>')

    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    parts.append(f'<p align="center"><sub>updated {stamp}</sub></p>')
    return "\n\n".join(parts)


def inject(block: str) -> None:
    if not README.exists():
        raise SystemExit("README.md 가 없습니다.")
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"README.md 에 마커가 없습니다:\n{START}\n{END}")
    README.write_text(
        re.sub(
            rf"{re.escape(START)}.*?{re.escape(END)}",
            f"{START}\n{block}\n{END}",
            text,
            flags=re.DOTALL,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    out = build_block()
    inject(out)
    print(out)
