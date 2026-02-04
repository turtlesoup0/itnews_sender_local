#!/bin/bash
# launchd 스케줄러 관리
# 사용법:
#   ./scripts/setup_launchd.sh install    - 등록 및 시작
#   ./scripts/setup_launchd.sh uninstall  - 해제
#   ./scripts/setup_launchd.sh status     - 상태 확인
#   ./scripts/setup_launchd.sh logs       - 최근 로그 출력

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SRC="$PROJECT_DIR/com.itnews.sender.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.itnews.sender.plist"
LABEL="com.itnews.sender"
LOG_DIR="$PROJECT_DIR/logs"

case "$1" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$LOG_DIR"
    cp "$PLIST_SRC" "$PLIST_DST"
    launchctl load "$PLIST_DST"
    echo "등록 완료: $LABEL"
    echo "매일 06:00 KST에 실행됩니다."
    ;;
  uninstall)
    launchctl unload "$PLIST_DST" 2>/dev/null
    rm -f "$PLIST_DST"
    echo "해제 완료: $LABEL"
    ;;
  status)
    launchctl list | grep "$LABEL" || echo "미등록"
    ;;
  logs)
    echo "=== stdout ==="
    tail -20 "$LOG_DIR/launchd_stdout.log" 2>/dev/null || echo "(파일 없음)"
    echo ""
    echo "=== stderr ==="
    tail -20 "$LOG_DIR/launchd_stderr.log" 2>/dev/null || echo "(파일 없음)"
    echo ""
    echo "=== application log ==="
    tail -20 "$LOG_DIR/itnews_sender.log" 2>/dev/null || echo "(파일 없음)"
    ;;
  *)
    echo "사용법: $0 {install|uninstall|status|logs}"
    exit 1
    ;;
esac
