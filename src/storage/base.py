from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class StorageBackend(ABC):
    """스토리지 백엔드 추상 인터페이스"""

    # --- Recipients ---
    @abstractmethod
    def get_recipient(self, email: str) -> Optional[Dict]:
        """수신인 정보 조회"""
        ...

    @abstractmethod
    def put_recipient(self, item: Dict) -> bool:
        """수신인 정보 저장 (이미 존재하면 덮어쓰기)"""
        ...

    @abstractmethod
    def query_recipients_by_status(self, status: str) -> List[Dict]:
        """상태별 수신인 조회"""
        ...

    @abstractmethod
    def get_all_recipients(self) -> List[Dict]:
        """모든 수신인 조회"""
        ...

    @abstractmethod
    def update_recipient(self, email: str, updates: Dict) -> bool:
        """수신인 정보 업데이트"""
        ...

    @abstractmethod
    def delete_recipient(self, email: str) -> bool:
        """수신인 정보 삭제"""
        ...

    # --- Execution Log ---
    @abstractmethod
    def get_execution(self, execution_key: str) -> Optional[Dict]:
        """실행 기록 조회"""
        ...

    @abstractmethod
    def put_execution(self, item: Dict) -> bool:
        """
        실행 기록 삽입 (멱등성 보장).
        이미 존재하면 False 반환 (SQLite: INSERT OR IGNORE / DynamoDB: ConditionExpression)
        """
        ...

    # --- Failure Tracking ---
    @abstractmethod
    def get_failure(self, date: str) -> Optional[Dict]:
        """실패 기록 조회"""
        ...

    @abstractmethod
    def increment_failure(self, date: str, error: str) -> int:
        """실패 카운트 원자적 증가. 새 카운트 반환."""
        ...

    @abstractmethod
    def delete_failure(self, date: str) -> bool:
        """실패 기록 삭제 (성공 후 리셋용)"""
        ...
