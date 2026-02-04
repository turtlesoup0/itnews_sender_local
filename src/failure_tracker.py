"""
PDF 다운로드 실패 추적
DynamoDB를 사용하여 날짜별 실패 횟수를 기록하고 3회 이상 실패 시 건너뛰기
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .storage import get_storage_backend

logger = logging.getLogger(__name__)


class FailureTracker:
    """PDF 다운로드 실패 추적 클래스"""

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

    def should_skip_today(self) -> bool:
        """
        오늘 3회 이상 실패했는지 확인

        Returns:
            건너뛰어야 하면 True
        """
        today = self._get_today_date()
        item = self._get_backend().get_failure(today)

        if item is None:
            return False

        failure_count = item.get("failure_count", 0)

        if failure_count >= 3:
            logger.warning(
                f"오늘({today}) 3회 이상 실패하여 발송을 건너뜁니다 (현재: {failure_count}회)"
            )
            return True

        return False

    def increment_failure(self, error_message: str) -> int:
        """
        실패 카운트 증가 및 현재 카운트 반환

        Args:
            error_message: 오류 메시지

        Returns:
            증가 후 실패 카운트
        """
        today = self._get_today_date()
        now = datetime.now(timezone.utc)

        new_count = self._get_backend().increment_failure(today, error_message[:500])

        logger.info(f"실패 카운트 증가: {today} - {new_count}회")
        return new_count

    def reset_today(self) -> bool:
        """
        오늘 실패 카운트 리셋 (성공 시 호출)

        Returns:
            성공 여부
        """
        today = self._get_today_date()
        return self._get_backend().delete_failure(today)

    def get_failure_info(self, date: Optional[str] = None) -> Optional[dict]:
        """
        특정 날짜의 실패 정보 조회

        Args:
            date: 조회할 날짜 (YYYY-MM-DD), None이면 오늘

        Returns:
            실패 정보 딕셔너리 또는 None
        """
        target_date = date or self._get_today_date()
        return self._get_backend().get_failure(target_date)
