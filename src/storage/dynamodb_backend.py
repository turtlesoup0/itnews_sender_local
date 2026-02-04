"""
DynamoDB 스토리지 백엔드 구현
AWS Lambda 환경에서 DynamoDB를 사용하여 Mac Mini 환경을 대체
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

from .base import StorageBackend

logger = logging.getLogger(__name__)


def _get_ttl(days: int = 7) -> int:
    """TTL을 위한 시간 계산 (초 단위)"""
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


class DynamoDBBackend(StorageBackend):
    """DynamoDB 스토리지 백엔드 (기존 dynamodb_client.py의 코드 래핑)"""

    def __init__(self):
        """DynamoDBBackend 초기화 (Config에서 설정 로드)"""
        from ..config import Config

        self.region_name = Config.AWS_REGION
        self._recipients_table = Config.DYNAMODB_RECIPIENTS_TABLE
        self._failures_table = Config.DYNAMODB_FAILURES_TABLE
        self._execution_table = Config.DYNAMODB_EXECUTION_TABLE
        self._dynamodb = None
        self._tables = {}  # 테이블별 캐시

    def _get_dynamodb(self):
        """Lazy loading: boto3 DynamoDB 리소스"""
        if self._dynamodb is None:
            self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
        return self._dynamodb

    def _get_table(self, table_name: str):
        """Lazy loading: 테이블 리소스"""
        if table_name not in self._tables:
            dynamodb = self._get_dynamodb()
            self._tables[table_name] = dynamodb.Table(table_name)
        return self._tables[table_name]

    # --- Recipients ---
    def get_recipient(self, email: str) -> Optional[Dict]:
        """수신인 정보 조회"""
        try:
            table = self._get_table(self._recipients_table)
            response = table.get_item(Key={"email": email})

            if "Item" in response:
                logger.info(f"DynamoDB 아이템 조회 완료: {email}")
                return response["Item"]
            else:
                logger.info(f"DynamoDB 아이템 없음: {email}")
                return None

        except ClientError as e:
            logger.error(f"DynamoDB get_item 실패: {e}")
            return None

    def put_recipient(self, item: Dict) -> bool:
        """수신인 정보 저장 (이미 존재하면 덮어쓰기)"""
        try:
            table = self._get_table(self._recipients_table)
            table.put_item(Item=item)
            logger.info(f"DynamoDB에 아이템 저장 완료: {item.get('email')}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB put_item 실패: {e}")
            return False

    def query_recipients_by_status(self, status: str) -> List[Dict]:
        """상태별 수신인 조회"""
        try:
            table = self._get_table(self._recipients_table)
            response = table.query(
                IndexName="status-index",
                KeyConditionExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": status},
            )

            items = response.get("Items", [])
            logger.info(f"DynamoDB 상태별 조회 완료: {status} ({len(items)}건)")
            return items

        except ClientError as e:
            logger.error(f"DynamoDB query 실패: {e}")
            return []

    def get_all_recipients(self) -> List[Dict]:
        """모든 수신인 조회"""
        try:
            table = self._get_table(self._recipients_table)
            response = table.scan()

            items = response.get("Items", [])

            # 페이지네이션 처리
            while "LastEvaluatedKey" in response:
                response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
                items.extend(response.get("Items", []))

            logger.info(f"DynamoDB 전체 스캔 완료: {len(items)}건")
            return items

        except ClientError as e:
            logger.error(f"DynamoDB scan 실패: {e}")
            return []

    def update_recipient(self, email: str, updates: Dict) -> bool:
        """수신인 정보 업데이트"""
        try:
            table = self._get_table(self._recipients_table)

            # UpdateExpression 생성
            update_expression = "SET " + ", ".join(
                [f"#{k} = :{k}" for k in updates.keys()]
            )
            expression_attribute_names = {f"#{k}": k for k in updates.keys()}
            expression_attribute_values = {f":{k}": v for k, v in updates.items()}

            table.update_item(
                Key={"email": email},
                UpdateExpression=update_expression,
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values,
            )

            logger.info(f"DynamoDB 아이템 업데이트 완료: {email}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB update_item 실패: {e}")
            return False

    def delete_recipient(self, email: str) -> bool:
        """수신인 정보 삭제"""
        try:
            table = self._get_table(self._recipients_table)
            table.delete_item(Key={"email": email})
            logger.info(f"DynamoDB 아이템 삭제 완료: {email}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB delete_item 실패: {e}")
            return False

    # --- Execution Log ---
    def get_execution(self, execution_key: str) -> Optional[Dict]:
        """실행 기록 조회"""
        try:
            table = self._get_table(self._execution_table)
            response = table.get_item(Key={"execution_key": execution_key})

            if "Item" in response:
                return response["Item"]
            else:
                return None

        except ClientError as e:
            logger.error(f"DynamoDB 실행 기록 조회 실패: {e}")
            return None

    def put_execution(self, item: Dict) -> bool:
        """
        실행 기록 삽입 (멱등성 보장)
        이미 존재하면 False 반환 (ConditionExpression: attribute_not_exists)
        """
        try:
            table = self._get_table(self._execution_table)

            table.put_item(
                Item={
                    "execution_key": item.get("execution_key"),
                    "date": item.get("date"),
                    "mode": item.get("mode"),
                    "request_id": item.get("request_id"),
                    "execution_time": item.get("execution_time"),
                    "ttl": _get_ttl(),
                },
                ConditionExpression="attribute_not_exists(execution_key)",
            )

            logger.info(f"실행 기록: {item.get('execution_key')}")
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(
                    f"이미 기록된 실행: {item.get('execution_key')} (중복 방지)"
                )
                return False
            logger.error(f"실행 기록 삽입 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"실행 기록 삽입 실패 (예외): {e}")
            return False

    # --- Failure Tracking ---
    def get_failure(self, date: str) -> Optional[Dict]:
        """실패 기록 조회"""
        try:
            table = self._get_table(self._failures_table)
            response = table.get_item(Key={"date": date})

            if "Item" in response:
                return response["Item"]
            else:
                return None

        except ClientError as e:
            logger.error(f"DynamoDB 실패 기록 조회 실패: {e}")
            return None

    def increment_failure(self, date: str, error: str) -> int:
        """실패 카운트 원자적 증가. 새 카운트 반환."""
        try:
            table = self._get_table(self._failures_table)
            now = datetime.now(timezone.utc).isoformat()

            response = table.update_item(
                Key={"date": date},
                UpdateExpression=(
                    "SET failure_count = if_not_exists(failure_count, :zero) + :inc, "
                    "last_error = :error, updated_at = :now, "
                    "ttl = :ttl"
                ),
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":inc": 1,
                    ":error": error[:500],
                    ":now": now,
                    ":ttl": _get_ttl(),
                },
                ReturnValues="UPDATED_NEW",
            )

            new_count = int(response["Attributes"]["failure_count"])
            logger.info(f"실패 카운트 증가: {date} - {new_count}회")
            return new_count

        except ClientError as e:
            logger.error(f"DynamoDB 실패 카운트 증가 실패: {e}")
            return 1

    def delete_failure(self, date: str) -> bool:
        """실패 기록 삭제 (성공 후 리셋용)"""
        try:
            table = self._get_table(self._failures_table)
            table.delete_item(Key={"date": date})
            logger.info(f"DynamoDB 실패 기록 삭제: {date}")
            return True

        except ClientError as e:
            logger.error(f"DynamoDB 실패 기록 삭제 실패: {e}")
            return False
