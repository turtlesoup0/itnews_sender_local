#!/bin/bash
# launchd 실행용 래퍼 스크립트
# venv Python 대신 system Python을 사용하여 macOS TCC 권한 문제를 회피
# (venv/bin/python3 사용 시 pyvenv.cfg 읽기가 TCC에 의해 차단됨)
#
# [S5] launchd stdout/stderr 로그를 월별 파일로 자동 분리하고
#       3개월 초과 파일을 자동 정리한다. (plist 의 StandardErrorPath 는 제거됨)

PROJECT_DIR="/Users/turtlesoup0-macmini/Projects/itnews_sender"
SYSTEM_PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
VENV_SITE_PACKAGES="${PROJECT_DIR}/venv/lib/python3.9/site-packages"
LOG_DIR="${PROJECT_DIR}/logs"

mkdir -p "${LOG_DIR}"

# --- S5: 월별 로그 분리 + 3개월 초과 prune --------------------------------
# 이 스크립트가 실행되는 시점의 연-월을 기준으로 단일 파일에 stdout+stderr append
# launchd StandardErrorPath 가 제거되므로, 이 리디렉션이 유일한 기록 경로다.
MONTH_TAG="$(date +%Y%m)"
MONTHLY_LOG="${LOG_DIR}/launchd_${MONTH_TAG}.log"

# 오래된 월간 파일 자동 정리 (90일 초과 = 3개월)
# 실패해도 발송은 계속 진행되어야 하므로 || true
find "${LOG_DIR}" -maxdepth 1 -type f -name 'launchd_20*.log' -mtime +90 -delete 2>/dev/null || true

# 이후 모든 출력을 월간 로그로 리디렉션
exec >>"${MONTHLY_LOG}" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') launchd_runner start (args: $*) ====="

# --- .env 로드 (서버 재기동 후에도 동작하도록) -----------------------------
if [ -f "${PROJECT_DIR}/.env" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "${PROJECT_DIR}/.env" | xargs)
fi

# venv의 site-packages를 PYTHONPATH에 추가
export PYTHONPATH="${VENV_SITE_PACKAGES}:${PROJECT_DIR}"
export TZ="Asia/Seoul"

cd "${PROJECT_DIR}" || exit 1

# system Python으로 직접 실행 (pyvenv.cfg 읽기를 회피)
exec "${SYSTEM_PYTHON}" "${PROJECT_DIR}/run_daily.py" "$@"
