"""
스토리지 백엔드 팩토리
환경에 따라 적절한 스토리지 백엔드를 선택하여 반환
"""

import os
from .base import StorageBackend

_backend_instance: StorageBackend = None


def get_storage_backend() -> StorageBackend:
    """환경에 따라 적절한 스토리지 백엔드 반환 (싱글톤)"""
    global _backend_instance
    if _backend_instance is not None:
        return _backend_instance

    is_lambda = os.environ.get("AWS_EXECUTION_ENV") is not None

    if is_lambda:
        # AWS Lambda 환경: DynamoDB 사용
        from .dynamodb_backend import DynamoDBBackend

        _backend_instance = DynamoDBBackend()
    else:
        # Mac Mini 로컬 환경: SQLite 사용
        from .sqlite_backend import SQLiteBackend

        _backend_instance = SQLiteBackend()

    return _backend_instance
