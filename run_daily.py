#!/usr/bin/env python3
"""
Mac Mini 로컬 실행 엔트리포인트
launchd 또는 수동으로 실행

사용법:
  python run_daily.py                           # test 모드 (관리자에게만)
  python run_daily.py --mode opr                # 운영 모드 (전체 수신인)
  python run_daily.py --mode test --skip-idempotency  # 멱등성 무시 재실행
"""
import sys
import os
import argparse
import json
from datetime import datetime

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description='IT뉴스 PDF 발송')
    parser.add_argument('--mode', choices=['test', 'opr'], default='test',
                        help='실행 모드: test(관리자만) 또는 opr(전체)')
    parser.add_argument('--skip-idempotency', action='store_true',
                        help='멱등성 체크 건너뛰기 (같은 날 재실행)')
    args = parser.parse_args()

    # 로깅 설정 (파일 + 콘솔)
    from src.structured_logging import setup_logging
    setup_logging()

    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== run_daily.py 시작 (mode={args.mode}, skip_idempotency={args.skip_idempotency}) ===")

    # Config 유효성 검증
    from src.config import Config
    try:
        Config.validate()
    except ValueError as e:
        logger.error(f"설정 검증 실패: {e}")
        sys.exit(1)

    # 핸들러 실행
    from lambda_handler import handler

    event = {
        'mode': args.mode,
        'skip_idempotency': args.skip_idempotency,
    }

    result = handler(event, None)

    # 결과 출력 및 종료 코드
    status_code = result.get('statusCode', 500)
    body = result.get('body', '{}')
    if isinstance(body, str):
        body = json.loads(body)

    logger.info(f"=== run_daily.py 완료: statusCode={status_code} ===")

    if status_code == 200:
        print(f"[{datetime.now().isoformat()}] 성공: {body.get('message', '')}")
        sys.exit(0)
    else:
        print(f"[{datetime.now().isoformat()}] 실패 (statusCode={status_code}): {body.get('message', '')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
