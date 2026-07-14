"""
AWS Lambda 핸들러
EventBridge에서 트리거되어 IT뉴스 PDF 다운로드 및 전송
"""

import logging
import os
import json
import time
from datetime import datetime, timezone, timedelta

from src.structured_logging import get_structured_logger
from src.delivery_tracker import DeliveryTracker
from src.failure_tracker import FailureTracker

# 워크플로우 모듈
from src.workflow import check_idempotency, check_failure_limit, send_emails, upload_to_icloud
from src.workflow.icloud_workflow import upload_itfind_to_icloud
from src.workflow.pdf_workflow import (
    download_and_process_pdf,
    download_itfind_pdf,
)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


def is_itfind_day() -> bool:
    """
    오늘이 ITFIND 주간기술동향 다운로드 요일(목요일)인지 확인 (KST 기준)

    주간기술동향은 격주 수요일 발행되지만, 발행 당일 07:00에는 RSS/StreamDocs
    자료 게시가 완료되지 않는 경우가 있어(2215·2216호 누락 사례) 발행 다음 날인
    목요일에 다운로드를 시도한다.

    Returns:
        bool: 목요일이면 True
    """
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    return now_kst.weekday() == 3  # 0=월요일, 3=목요일


def handler(event, context):
    """
    Lambda 함수 핸들러

    Args:
        event: Lambda 이벤트 (EventBridge 스케줄)
        context: Lambda 컨텍스트

    Returns:
        dict: 실행 결과
    """
    start_time = time.time()

    logger.info("===== IT뉴스 PDF 전송 작업 시작 =====")

    # 안전한 이벤트 로깅 (민감정보 제외)
    safe_event = {k: v for k, v in event.items() if k in ["mode", "request_id"]}
    logger.info(f"Event (safe): {json.dumps(safe_event)}")

    # 실행 모드 결정 (기본값: test)
    mode = event.get("mode", "test")
    is_test_mode = mode != "opr"

    # 멱등성 체크 비활성화 옵션 (테스트용)
    skip_idempotency = event.get("skip_idempotency", False)

    if is_test_mode:
        logger.info("🧪 TEST 모드로 실행 (수신인: ***@***.***)")
    else:
        logger.info("🚀 OPR 모드로 실행 (수신인: DynamoDB 활성 수신인 전체)")

    structured_logger.info(
        event="lambda_start",
        message=f"IT뉴스 PDF 전송 작업 시작 (모드: {mode})",
        function_name=context.function_name if context else "local",
        request_id=context.aws_request_id if context else "local",
        execution_mode=mode,
    )

    pdf_path = None
    processed_pdf_path = None

    try:
        # 0. 멱등성 보장
        request_id = context.aws_request_id if context else "local"
        can_proceed, error_response = check_idempotency(
            mode, request_id, skip_idempotency
        )

        if not can_proceed:
            duration_ms = (time.time() - start_time) * 1000
            structured_logger.info(
                event="duplicate_execution_prevented",
                message=f"오늘 이미 {mode} 모드로 실행됨",
                execution_mode=mode,
                duration_ms=duration_ms,
            )
            return {
                "statusCode": error_response["statusCode"],
                "body": json.dumps(error_response["body"]),
            }

        # DeliveryTracker 초기화 (수신인별 발송 이력 추적용)
        tracker = DeliveryTracker()

        # 1. 실패 제한 체크
        can_proceed, error_response = check_failure_limit()

        if not can_proceed:
            duration_ms = (time.time() - start_time) * 1000
            return {
                "statusCode": error_response["statusCode"],
                "body": json.dumps(error_response["body"]),
            }

        # 실패 추적기 초기화
        failure_tracker = FailureTracker()

        # 2. 전자신문 PDF 다운로드 및 처리
        try:
            pdf_path, processed_pdf_path, page_info = download_and_process_pdf(
                failure_tracker
            )

        except ValueError as ve:
            # 신문 미발행일 처리
            if "신문이 발행되지 않은 날" in str(ve):
                duration_ms = (time.time() - start_time) * 1000
                logger.info("신문이 발행되지 않은 날입니다")

                structured_logger.info(
                    event="newspaper_not_published",
                    message="신문 미발행일로 인해 메일 미전송",
                    duration_ms=duration_ms,
                )

                return {
                    "statusCode": 200,
                    "body": json.dumps(
                        {"message": "신문이 발행되지 않은 날입니다", "skipped": True}
                    ),
                }
            else:
                raise

        except Exception as e:
            # PDF 다운로드 실패 (워크플로우에서 이미 알림 처리됨)
            raise

        # 2-1. 목요일이면 ITFIND 주간기술동향 다운로드 (발행 다음 날, 자료 게시 완료 후)
        itfind_pdf_path = None
        itfind_trend_info = None

        # 현재 시각 로깅 (디버깅용)
        kst = timezone(timedelta(hours=9))
        now_kst = datetime.now(kst)
        now_utc = datetime.now(timezone.utc)
        logger.info(
            f"현재 시각 - UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}, KST: {now_kst.strftime('%Y-%m-%d %H:%M:%S %Z')}, weekday: {now_kst.weekday()}"
        )

        if is_itfind_day():
            logger.info("📅 오늘은 목요일 - ITFIND 주간기술동향 다운로드 시도")
            try:
                itfind_pdf_path, itfind_trend_info = download_itfind_pdf()
            except Exception as itfind_error:
                # ITFIND 실패해도 전자신문 발송은 계속
                logger.error(f"ITFIND 다운로드 실패 (무시하고 계속): {itfind_error}")
                structured_logger.warning(
                    event="itfind_download_failed",
                    message="ITFIND 주간기술동향 다운로드 실패",
                    error=str(itfind_error),
                )
                itfind_pdf_path = None
                itfind_trend_info = None
        else:
            logger.info("📅 오늘은 목요일이 아님 - ITFIND 다운로드 건너뛰기")

        # 4. 이메일 전송 (모드에 따라 수신인 결정)
        logger.info("4단계: 이메일 전송 시작")

        email_success, success_emails, itfind_email_success, itfind_success_emails = \
            send_emails(processed_pdf_path, is_test_mode, itfind_pdf_path, itfind_trend_info)

        if not email_success:
            logger.error("전자신문 이메일 전송 실패")
            raise Exception("전자신문 이메일 전송 실패")

        logger.info(f"전자신문 이메일 전송 성공: {len(success_emails)}명")

        # 4-1. iCloud Drive에 전자신문 PDF 업로드 (로컬 전용, 함수 내부에서 예외 처리)
        upload_to_icloud(processed_pdf_path)

        # 4-2. ITFIND iCloud Drive 업로드 (로컬 전용, 목요일만)
        if itfind_pdf_path and itfind_trend_info:
            upload_itfind_to_icloud(
                itfind_pdf_path,
                itfind_trend_info.issue_number,
                itfind_trend_info.publish_date
            )

        # 5. 발송 이력 기록 (OPR 모드에만 기록)
        if not is_test_mode:
            logger.info("5단계: 발송 이력 기록 (OPR 모드)")
            tracker.mark_as_delivered(success_emails)
            logger.info("발송 이력 기록 완료")
        else:
            logger.info("5단계: 발송 이력 기록 건너뛰기 (TEST 모드)")

        duration_ms = (time.time() - start_time) * 1000

        logger.info("===== IT뉴스 PDF 전송 작업 완료 =====")

        structured_logger.info(
            event="lambda_success",
            message="IT뉴스 PDF 전송 작업 완료",
            duration_ms=duration_ms,
            pdf_path=pdf_path,
            processed_pdf_path=processed_pdf_path,
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "IT뉴스 PDF 전송 성공",
                    "pdf_path": pdf_path,
                    "processed_pdf_path": processed_pdf_path,
                    "duration_ms": duration_ms,
                }
            ),
        }

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        logger.error(f"작업 실행 중 오류 발생: {e}", exc_info=True)

        structured_logger.error(
            event="lambda_error",
            message=f"IT뉴스 PDF 전송 작업 실패: {str(e)}",
            duration_ms=duration_ms,
            error=str(e),
            error_type=type(e).__name__,
        )

        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": "IT뉴스 PDF 전송 실패",
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            ),
        }

    finally:
        # 임시 파일 정리
        cleanup_temp_files(
            pdf_path,
            processed_pdf_path,
            itfind_pdf_path if "itfind_pdf_path" in locals() else None,
        )


def cleanup_temp_files(*file_paths):
    """임시 파일 정리"""
    logger.info("임시 파일 정리 시작")

    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"파일 삭제: {file_path}")
            except Exception as e:
                logger.warning(f"파일 삭제 실패 ({file_path}): {e}")

    logger.info("임시 파일 정리 완료")
