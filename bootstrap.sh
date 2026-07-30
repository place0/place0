#!/usr/bin/env bash
# 사용법: ./bootstrap.sh <github-username>
# README 의 <USERNAME> 자리를 채우고, 통계 블록을 한 번 렌더링한다.
# 설치할 의존성은 없다 (파이썬 표준 라이브러리만 사용).
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "사용법: ./bootstrap.sh <github-username>"
  exit 1
fi

USER_NAME="$1"

echo "▶ README 에 사용자명 주입: $USER_NAME"
if sed --version >/dev/null 2>&1; then
  sed -i "s/<USERNAME>/$USER_NAME/g" README.md
else
  sed -i '' "s/<USERNAME>/$USER_NAME/g" README.md
fi

echo "▶ GitHub 활동 통계 (토큰 있으면 실제 값, 없으면 생략)"
GH_USERNAME="$USER_NAME" python3 scripts/github_stats.py || true

echo "▶ 코딩 시간 (WakaTime)"
python3 scripts/coding_time.py >/dev/null || true

echo ""
echo "✅ 준비 완료. README.md 를 확인한 뒤 push 하면 된다."
echo "   git add -A && git commit -m 'feat: readme stats' && git push"
