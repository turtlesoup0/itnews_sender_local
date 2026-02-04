"""
DynamoDB 클라이언트 (호환 래퍼)
기존 인터페이스를 유지하면서 내부적으로 StorageBackend 사용
"""

import logging
from typing import Dict, List, Optional

from ..storage import get_storage_backend

logger = logging.getLogger(__name__)


class DynamoDBClient:
    """기존 인터페이스 호환 래퍼 — 내부적으로 StorageBackend에 위임"""

    def __init__(
        self, table_name: str = "etnews-recipients", region_name: str = "ap-northeast-2"
    ):
        """
        초기화 (기존 인터페이스 호환 유지)

        Args:
            table_name: 테이블명 (현재는 무시됨, StorageBackend가 관리)
            region_name: 리전 (현재는 무시됨, StorageBackend가 관리)
        """
        self.table_name = table_name
        self.region_name = region_name
        self._backend = None
        logger.info("DynamoDBClient 초기화 (StorageBackend 래퍼)")

    def _get_backend(self):
        """StorageBackend lazy 초기화"""
        if self._backend is None:
            self._backend = get_storage_backend()
        return self._backend

    def put_item(self, item: Dict) -> bool:
        """수신인 정보 저장"""
        return self._get_backend().put_recipient(item)

    def get_item(self, email: str) -> Optional[Dict]:
        """수신인 정보 조회"""
        return self._get_backend().get_recipient(email)

    def query_by_status(self, status: str) -> List[Dict]:
        """상태별 수신인 조회"""
        return self._get_backend().query_recipients_by_status(status)

    def scan_all(self) -> List[Dict]:
        """모든 수신인 조회"""
        return self._get_backend().get_all_recipients()

    def update_item(self, email: str, updates: Dict) -> bool:
        """수신인 정보 업데이트"""
        return self._get_backend().update_recipient(email, updates)

    def delete_item(self, email: str) -> bool:
        """수신인 정보 삭제"""
        return self._get_backend().delete_recipient(email)
