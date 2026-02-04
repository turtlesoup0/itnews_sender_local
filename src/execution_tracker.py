"""
Lambda 실행 이력 추적
날짜 + 모드별로 중복 실행 방지 (멱등성 보장)
"""

import logging
from datetime import datetime, timezone, timedelta

from .storage import get_storage_backend

logger = logging.getLogger(__name__)


class ExecutionTracker:
    """Lambda 실행 이력 추적 클래스"""

    def __init__(self):
        """초기화"""
        self._backend = None

    def _get_backend(self):
        """StorageBackend lazy 초기화"""
        if self._backend is None:
            self._backend = get_storage_backend()
        return self._backend

    def _get_today_date(self) -> str:
        """
        오늘 날짜 반환 (KST 기준)

        Returns:
            YYYY-MM-DD 형식의 날짜 문자열
        """
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst)
        return today.strftime("%Y-%m-%d")

    def _get_execution_key(self, mode: str) -> str:
        """
        실행 키 생성 (날짜#모드)

        Args:
            mode: 실행 모드 ("test" 또는 "opr")

        Returns:
            실행 키 (예: "2026-01-27#test")
        """
        today = self._get_today_date()
        return f"{today}#{mode}"

    def should_skip_execution(self, mode: str) -> bool:
        """
        오늘 이미 실행되었는지 확인

        Args:
            mode: 실행 모드 ("test" 또는 "opr")

        Returns:
            건너뛰어야 하면 True
        """
        execution_key = self._get_execution_key(mode)
        item = self._get_backend().get_execution(execution_key)

        if item is not None:
            request_id = item.get("request_id", "unknown")
            execution_time = item.get("execution_time", "unknown")

            logger.warning(
                f"오늘 이미 {mode} 모드로 실행되었습니다 "
                f"(키: {execution_key}, RequestId: {request_id}, 시각: {execution_time})"
            )
            return True

        return False

    def mark_execution(self, mode: str, request_id: str) -> bool:
        """
        오늘 실행 기록

        Args:
            mode: 실행 모드 ("test" 또는 "opr")
            request_id: Lambda RequestId (context.request_id)

        Returns:
            성공 여부
        """
        execution_key = self._get_execution_key(mode)
        today = self._get_today_date()
        now = datetime.now(timezone.utc).isoformat()

        try:
            item = {
                "execution_key": execution_key,
                "date": today,
                "mode": mode,
                "request_id": request_id,
                "execution_time": now,
            }

            result = self._get_backend().put_execution(item)

            if result:
                logger.info(
                    f"실행 이력 기록: {execution_key} (RequestId: {request_id})"
                )
            else:
                logger.warning(f"이미 실행 이력 존재: {execution_key} (중복 방지)")

            return result

        except Exception as e:
            logger.error(f"실행 이력 기록 오류: {e}")
            return False

    def get_execution_info(self, mode: str, date: str = None) -> dict:
        """
        특정 날짜의 실행 정보 조회

        Args:
            mode: 실행 모드 ("test" 또는 "opr")
            date: 조회할 날짜 (YYYY-MM-DD), None이면 오늘

        Returns:
            실행 정보 딕셔너리 또는 None
        """
        if date is None:
            date = self._get_today_date()

        execution_key = f"{date}#{mode}"
        item = self._get_backend().get_execution(execution_key)

        if item is None:
            return None

        return item
