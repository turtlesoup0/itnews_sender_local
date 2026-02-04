#!/bin/bash
# launchd 실행용 래퍼 스크립트
# venv Python 대신 system Python을 사용하여 macOS TCC 권한 문제를 회피
# (venv/bin/python3 사용 시 pyvenv.cfg 읽기가 TCC에 의해 차단됨)

PROJECT_DIR="/Users/your-username/Projects/itnews_sender"
SYSTEM_PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
VENV_SITE_PACKAGES="${PROJECT_DIR}/venv/lib/python3.9/site-packages"

# venv의 site-packages를 PYTHONPATH에 추가
export PYTHONPATH="${VENV_SITE_PACKAGES}:${PROJECT_DIR}"
export TZ="Asia/Seoul"

cd "${PROJECT_DIR}"

# system Python으로 직접 실행 (pyvenv.cfg 읽기를 회피)
exec "${SYSTEM_PYTHON}" "${PROJECT_DIR}/run_daily.py" "$@"
