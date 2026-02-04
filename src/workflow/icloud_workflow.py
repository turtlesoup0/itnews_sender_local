"""
iCloud Drive 자동 업로드 워크플로우
로컬 실행 시 처리된 전자신문 PDF를 iCloud Drive에 자동 복사
"""

import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

ICLOUD_BASE_PATH = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/전자신문"
)


def upload_to_icloud(processed_pdf_path: str) -> Optional[str]:
    """
    처리된 PDF를 iCloud Drive에 복사한다.

    Lambda 환경에서는 즉시 스킵하고, 로컬 환경에서만 동작한다.
    실패해도 예외를 발생시키지 않고 None을 반환한다.

    Args:
        processed_pdf_path: 처리된 PDF 파일 경로

    Returns:
        복사된 iCloud Drive 경로, 실패 시 None
    """
    # Lambda 환경이면 스킵
    if os.environ.get("AWS_EXECUTION_ENV"):
        logger.info("Lambda 환경 — iCloud 업로드 스킵")
        return None

    try:
        if not os.path.exists(processed_pdf_path):
            logger.warning(f"PDF 파일이 존재하지 않음: {processed_pdf_path}")
            return None

        # KST 기준 날짜로 서브디렉토리 결정
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        yy = now_kst.strftime("%y")        # "26"
        yymm = now_kst.strftime("%y%m")    # "2602"

        dest_dir = os.path.join(ICLOUD_BASE_PATH, yy, yymm)
        os.makedirs(dest_dir, exist_ok=True)

        filename = os.path.basename(processed_pdf_path)
        dest_path = os.path.join(dest_dir, filename)

        shutil.copy2(processed_pdf_path, dest_path)
        logger.info(f"iCloud Drive에 PDF 복사 완료: {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(f"iCloud Drive 업로드 실패 (무시하고 계속): {e}")
        return None


def upload_itfind_to_icloud(pdf_path: str, issue_number: str, publish_date: str) -> Optional[str]:
    """
    주간기술동향 PDF를 iCloud Drive에 업로드

    Lambda 환경에서는 즉시 스킵하고, 로컬 환경에서만 동작한다.
    실패해도 예외를 발생시키지 않고 None을 반환한다.

    Args:
        pdf_path: 주간기술동향 PDF 파일 경로
        issue_number: 호수 (예: "2203")
        publish_date: 발행일 (YYYY-MM-DD)

    Returns:
        업로드된 iCloud Drive 경로, 실패 시 None
    """
    # Lambda 환경이면 스킵
    if os.environ.get("AWS_EXECUTION_ENV"):
        logger.info("Lambda 환경 — ITFIND iCloud 업로드 스킵")
        return None

    try:
        if not os.path.exists(pdf_path):
            logger.warning(f"ITFIND PDF 파일이 존재하지 않음: {pdf_path}")
            return None

        # KST 기준 연도 추출
        kst = timezone(timedelta(hours=9))
        pub_dt = datetime.strptime(publish_date, "%Y-%m-%d").replace(tzinfo=kst)
        yyyy = pub_dt.strftime("%Y")

        # iCloud 경로 생성
        itfind_base_path = os.path.expanduser(
            "~/Library/Mobile Documents/com~apple~CloudDocs/주간 기술 동향"
        )
        dest_dir = os.path.join(itfind_base_path, yyyy)
        os.makedirs(dest_dir, exist_ok=True)

        # 파일명 생성: 주기동YYMMDD-xxxx호 형식
        yymmdd = pub_dt.strftime("%y%m%d")
        filename = f"주기동{yymmdd}-{issue_number}호.pdf"
        dest_path = os.path.join(dest_dir, filename)

        # 파일 복사
        shutil.copy2(pdf_path, dest_path)
        logger.info(f"iCloud Drive에 ITFIND PDF 복사 완료: {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(f"ITFIND iCloud 업로드 실패 (무시하고 계속): {e}")
        return None
