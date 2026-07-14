#!/usr/bin/env python3
"""
ITFIND 주간기술동향(주기동) 수동/보충 발송 스크립트

전자신문 재발송 없이, 현재 ITFIND 최신 주간기술동향 PDF만 내려받아
주간기술동향 메일을 단독으로 발송한다.

발송일(수→목) 이동 이전에 놓친 회차를 보충 발송하거나,
자료 게시 지연으로 07:00 정기 실행에서 누락된 회차를 당일 재발송할 때 사용.

사용법:
  python scripts/send_itfind_manual.py                 # test 모드 (관리자에게만)
  python scripts/send_itfind_manual.py --mode opr      # 운영 모드 (활성 수신인 전체)
"""
import argparse
import logging
import os
import sys

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="ITFIND 주간기술동향 수동 발송")
    parser.add_argument(
        "--mode",
        choices=["test", "opr"],
        default="test",
        help="실행 모드: test(관리자만) 또는 opr(활성 수신인 전체)",
    )
    args = parser.parse_args()

    from src.structured_logging import setup_logging

    setup_logging()
    logger = logging.getLogger(__name__)

    test_mode = args.mode != "opr"
    logger.info(f"=== ITFIND 수동 발송 시작 (mode={args.mode}) ===")

    # Config 유효성 검증
    from src.config import Config

    Config.validate()

    # 1) ITFIND 최신 주간기술동향 다운로드 (신선도/StreamDocs 처리 포함)
    from src.workflow.pdf_workflow import download_itfind_pdf

    itfind_pdf_path, itfind_info = download_itfind_pdf()

    if not itfind_pdf_path or not itfind_info:
        logger.error("ITFIND PDF를 가져오지 못했습니다 (신선도 미달 또는 자료 미게시). 발송 중단.")
        return 1

    logger.info(
        f"ITFIND 준비 완료: {itfind_info.issue_number}호 - {itfind_info.title} "
        f"(발행일 {itfind_info.publish_date})"
    )

    # 2) 주간기술동향 메일 단독 발송 (전자신문 재발송 없음)
    from src.email_sender import send_pdf_bulk_email

    email_subject = f"{itfind_info.title} [주간기술동향 {itfind_info.issue_number}호]"

    success, sent_emails = send_pdf_bulk_email(
        itfind_pdf_path,  # ITFIND PDF를 메인으로 전달
        subject=email_subject,
        test_mode=test_mode,
        itfind_pdf_path=itfind_pdf_path,  # 목차 이미지 추출용 동일 경로
        itfind_info=itfind_info,
    )

    if success:
        logger.info(f"✅ ITFIND 발송 성공 (수신인 {len(sent_emails)}명): {sent_emails}")
        return 0

    logger.error(f"❌ ITFIND 발송 실패 (성공 {len(sent_emails)}명)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
