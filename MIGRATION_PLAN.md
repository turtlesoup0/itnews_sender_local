# itnews_sender 맥미니 마이그레이션 계획서 v2

## 개요

AWS Lambda 기반 etnews/itfind 뉴스레터 발송 시스템의 **주 실행 환경을 Mac Mini로 전환**한다.
AWS 인프라는 **백업 수단으로 유지**하되 EventBridge 스케줄만 비활성화한다.
코드가 양쪽 환경에서 모두 동작하도록 **스토리지 추상화 레이어**를 도입한다.

**베이스 디렉토리**: `/path/to/project`

---

## Phase 0: 리팩토링 (마이그레이션 전 코드 정비)

마이그레이션 전에 기존 코드의 구조적 문제를 먼저 해결한다.
이 단계는 AWS 환경에서의 동작에 영향을 주지 않으면서 코드 품질을 개선한다.

### 발견된 리팩토링 항목

---

#### R-1. 버그 수정: `notification.py` SMTP 속성명 불일치

**파일**: `src/utils/notification.py:46-47`

**현상**: `config.SMTP_SERVER`와 `config.SMTP_PORT`를 참조하지만, `ConfigClass`에는 `GMAIL_SMTP_SERVER`와 `GMAIL_SMTP_PORT`로 정의되어 있어 런타임에 `AttributeError` 발생.

**수정**:
```python
# 변경 전 (notification.py:46-47)
with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:

# 변경 후
with smtplib.SMTP(config.GMAIL_SMTP_SERVER, config.GMAIL_SMTP_PORT) as server:
```

---

#### R-2. `sanitize_error()` 함수 중복 제거

**현상**: 동일한 `sanitize_error()` 함수가 두 곳에 존재
- `lambda_handler.py:47-71`
- `src/workflow/pdf_workflow.py:18-31`

**수정**:
- `src/utils/sanitize.py`에 단일 구현을 두거나, 기존 `pdf_workflow.py`의 것만 남기기
- `lambda_handler.py`에서 import하여 사용:
  ```python
  from src.workflow.pdf_workflow import sanitize_error
  ```
- `lambda_handler.py`의 로컬 `sanitize_error()` 함수 삭제

---

#### R-3. `lambda_handler.py`에서 미사용 `send_emails` 워크플로우 함수

**현상**: `src/workflow/email_workflow.py`에 `send_emails()` 함수가 존재하고 `src/workflow/__init__.py`에서 export하지만, `lambda_handler.py`는 이를 사용하지 않고 `send_pdf_bulk_email()`을 직접 호출하여 이메일 전송 로직을 인라인으로 구현 (214-249행).

**수정 방향**:
- `lambda_handler.py`의 이메일 전송 로직(214-249행)을 `send_emails()` 워크플로우 함수 호출로 교체
- 이미 `email_workflow.py`가 동일한 로직을 구현하고 있으므로, 핸들러를 얇게 유지
- 변경 전 검증 필요: `send_emails()`의 반환값 `(email_success, success_emails, itfind_email_success, itfind_success_emails)` 4-tuple이 핸들러의 후속 로직과 호환되는지 확인

---

#### R-4. `lambda_handler.py` 중복 import 정리

**현상**: `send_admin_notification`이 두 번 import됨
- 24행: `from src.utils.notification import send_admin_notification`
- 75행: `from src.utils.notification import send_admin_notification as _send_admin_notification`

두 번째 import의 `_send_admin_notification`은 `lambda_handler.py` 내에서 사용되지 않음 (원래 있던 로컬 함수가 `src/utils/notification.py`로 이동한 흔적).

**수정**: 75행 삭제, 74행의 주석도 삭제

---

#### R-5. `DynamoDBClient`의 인터페이스 누수 (leaky abstraction)

**현상**: `DynamoDBClient`는 `recipients` 테이블 전용으로 설계됨 (메서드가 `email` 기반: `get_item(email)`, `update_item(email, ...)`, `delete_item(email)`). 그러나 `ExecutionTracker`와 `FailureTracker`는 다른 테이블(다른 PK 구조)에서 사용하면서 `_get_table()`로 내부 DynamoDB Table 객체에 직접 접근하여 우회.

- `execution_tracker.py:64` → `table = self.db_client._get_table()` (PK: `execution_key`)
- `failure_tracker.py:49` → `table = self.db_client._get_table()` (PK: `date`)

**수정 방향** (Phase 1의 스토리지 추상화에서 함께 해결):
- `DynamoDBClient`를 범용 스토리지 인터페이스로 리디자인
- 또는 각 Tracker가 자체 DB 접근 로직을 가지도록 분리 (이 방법 권장)
- **상세 내용은 Phase 1 작업 1에서 설계**

---

#### R-6. `recipient_manager.py` 모듈 레벨 싱글톤의 즉시 초기화

**현상**: `recipient_manager.py:226`에서 `_recipient_manager = RecipientManager()`가 모듈 import 시점에 실행됨. 이는 `DynamoDBClient()`를 생성하며, 이 시점에서 테이블 존재 여부와 무관하게 boto3 리소스가 lazy-load 준비됨.

현재는 큰 문제 없으나, 스토리지 백엔드 선택(DynamoDB vs SQLite)을 환경에 따라 동적으로 하려면 이 초기화 타이밍이 문제가 됨.

**수정 방향** (Phase 1에서 함께 해결):
- 싱글톤 대신 팩토리 패턴 또는 lazy initialization 적용
- `get_active_recipients()` 편의함수 호출 시점에 초기화

---

#### R-7. ITFIND RSS 파싱 로직 중복

**현상**: RSS 피드(`itfind.or.kr/ccenter/rss.do`)를 파싱하는 코드가 두 곳에 별도 구현:
- `lambda_itfind_downloader.py:34-124` — `get_latest_weekly_trend_from_rss()` (standalone 함수)
- `src/itfind_scraper.py:81-201` — `ItfindScraper.get_latest_weekly_trend_from_rss()` (클래스 메서드)

두 구현은 같은 RSS를 파싱하지만 반환 형식, 토픽 수집 방식, 에러 처리가 다름.

**수정 방향**:
- `lambda_itfind_downloader.py`의 RSS 파싱을 `src/itfind_scraper.py`의 메서드로 통합
- `lambda_itfind_downloader.py`에서는 `ItfindScraper().get_latest_weekly_trend_from_rss()` 호출
- `ItfindScraper`의 RSS 메서드는 Playwright 브라우저 불필요 (순수 requests 기반) → 인스턴스 생성 없이도 호출 가능하도록 `@staticmethod` 또는 모듈 레벨 함수로 추출

---

#### R-8. `Config.validate()` 모듈 import 시 실행

**현상**: `src/config.py:205-209`에서 모듈이 import되면 자동으로 `Config.validate()` 호출. `.env` 파일이 없거나 credential이 누락되면 경고가 출력됨. 테스트나 스크립트에서 Config를 사용하지 않는 모듈을 import해도 경고 발생 가능.

```python
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(f"경고: {e}")
```

**수정**: `validate()`를 자동 호출하지 않고, 실제 사용 시점(`run_daily.py`나 `lambda_handler.py`의 시작부)에서 명시적으로 호출

---

#### R-9. 하드코딩된 테이블명과 리전

**현상**: 여러 파일에서 DynamoDB 테이블명과 AWS 리전이 기본값으로 하드코딩:
- `execution_tracker.py:17` → `table_name="etnews-execution-log"`, `region_name="ap-northeast-2"`
- `failure_tracker.py:17` → `table_name="etnews-delivery-failures"`, `region_name="ap-northeast-2"`
- `delivery_tracker.py:18` → `table_name="etnews-recipients"`, `region_name="ap-northeast-2"`
- `dynamodb_client.py:17` → `table_name="etnews-recipients"`, `region_name="ap-northeast-2"`

**수정**: `Config` 클래스에 테이블명과 리전을 중앙 관리, 각 모듈은 `Config`에서 읽기

---

### 리팩토링 실행 순서

```
R-1 (버그 수정)      ← 즉시 (기존 기능 영향)
R-4 (중복 import)    ← 즉시 (단순 정리)
R-2 (sanitize 중복)  ← 즉시 (단순 정리)
R-8 (validate 타이밍) ← 즉시 (단순 정리)
R-3 (email workflow)  ← 독립 (동작 변경 없이 리팩토링)
R-9 (하드코딩 정리)   ← R-5보다 먼저 (Config 중앙화)
R-5 (DynamoDB 추상화) ← Phase 1과 함께
R-6 (싱글톤 초기화)   ← Phase 1과 함께
R-7 (ITFIND 통합)    ← Phase 1의 Lambda invoke 제거와 함께
```

---

## Phase 1: 듀얼 환경 지원 마이그레이션

AWS Lambda와 Mac Mini 양쪽에서 동작하는 구조로 전환한다.
핵심 전략: **스토리지 추상화 레이어** 도입.

### 아키텍처 변경 요약

```
[현재]
lambda_handler.py
  → DynamoDBClient (직접 사용)
  → boto3.client('lambda').invoke (ITFIND)
  → EventBridge 스케줄

[변경 후]
run_daily.py (Mac Mini) ──┐
lambda_handler.py (AWS)  ──┤
                           ↓
                   src/config.py (환경 감지)
                           ↓
              ┌────────────┴────────────┐
        StorageBackend              StorageBackend
        (SQLite - 로컬)             (DynamoDB - AWS)
```

### AWS 백업 유지 전략

| 항목 | 조치 |
|---|---|
| Lambda 함수 3개 | **유지** — 코드 변경 후 재배포하여 최신 상태 유지 |
| EventBridge 스케줄 | **비활성화** (`aws events disable-rule`) — 수동 invoke로 백업 실행 가능 |
| DynamoDB 테이블 3개 | **유지** — Lambda 실행 시 그대로 사용 |
| SSM Parameter Store | **유지** — Lambda 환경에서 credential 소스 |
| ECR 이미지 | **유지** — 재배포용 |
| IAM 역할/정책 | **유지** — 변경 불필요 |

**백업 실행 방법** (Mac Mini 장애 시):
```bash
# 1. EventBridge 다시 활성화
aws events enable-rule --name news-daily-trigger --region ap-northeast-2

# 2. 또는 수동 Lambda 호출
aws lambda invoke --function-name etnews-pdf-sender \
  --payload '{"mode":"opr","skip_idempotency":true}' \
  --region ap-northeast-2 /tmp/result.json
```

---

### 작업 1: 스토리지 추상화 레이어 설계 및 구현

**목적**: DynamoDB와 SQLite를 동일 인터페이스로 사용할 수 있는 추상 레이어 도입

**생성할 파일들**:

#### 1-1. `src/storage/__init__.py`

```python
from .base import StorageBackend
from .factory import get_storage_backend
```

#### 1-2. `src/storage/base.py` — 추상 인터페이스

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

class StorageBackend(ABC):
    """스토리지 백엔드 추상 인터페이스"""

    # --- Recipients ---
    @abstractmethod
    def get_recipient(self, email: str) -> Optional[Dict]: ...

    @abstractmethod
    def put_recipient(self, item: Dict) -> bool: ...

    @abstractmethod
    def query_recipients_by_status(self, status: str) -> List[Dict]: ...

    @abstractmethod
    def get_all_recipients(self) -> List[Dict]: ...

    @abstractmethod
    def update_recipient(self, email: str, updates: Dict) -> bool: ...

    @abstractmethod
    def delete_recipient(self, email: str) -> bool: ...

    # --- Execution Log ---
    @abstractmethod
    def get_execution(self, execution_key: str) -> Optional[Dict]: ...

    @abstractmethod
    def put_execution(self, item: Dict) -> bool:
        """
        실행 기록 삽입 (멱등성 보장).
        이미 존재하면 False 반환 (DynamoDB ConditionExpression / SQLite INSERT OR IGNORE)
        """
        ...

    # --- Failure Tracking ---
    @abstractmethod
    def get_failure(self, date: str) -> Optional[Dict]: ...

    @abstractmethod
    def increment_failure(self, date: str, error: str) -> int:
        """실패 카운트 원자적 증가. 새 카운트 반환."""
        ...

    @abstractmethod
    def delete_failure(self, date: str) -> bool: ...
```

**설계 핵심**:
- 기존 `DynamoDBClient`의 "하나의 클래스가 3개 테이블을 범용 처리"하는 패턴을 버리고, **도메인별 메서드**로 명확하게 분리
- 각 Tracker(`ExecutionTracker`, `FailureTracker`, `DeliveryTracker`)가 `_get_table()`로 내부를 우회하던 문제 해결
- DynamoDB 구현과 SQLite 구현이 동일 인터페이스를 따름

#### 1-3. `src/storage/sqlite_backend.py` — SQLite 구현

**SQLite 스키마**:

```sql
-- 1. 수신인 테이블
CREATE TABLE IF NOT EXISTS recipients (
    email TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    unsubscribed_at TEXT,
    last_delivery_date TEXT
);
CREATE INDEX IF NOT EXISTS idx_recipients_status ON recipients(status);

-- 2. 실패 추적 테이블
CREATE TABLE IF NOT EXISTS delivery_failures (
    date TEXT PRIMARY KEY,
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT,
    ttl INTEGER
);

-- 3. 실행 이력 테이블
CREATE TABLE IF NOT EXISTS execution_log (
    execution_key TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    mode TEXT NOT NULL,
    request_id TEXT,
    execution_time TEXT,
    ttl INTEGER
);
```

**구현 요구사항**:
- DB 파일 위치: `Config`에서 `DB_PATH` 읽기 (기본값: `data/itnews_sender.db`)
- `__init__`에서 테이블 자동 생성 (`CREATE TABLE IF NOT EXISTS`)
- `data/` 디렉토리 자동 생성 (`os.makedirs`)
- TTL 정리: 각 조회 메서드 호출 시 `DELETE FROM ... WHERE ttl IS NOT NULL AND ttl < ?` 실행
- `put_execution()`: `INSERT OR IGNORE` + `cursor.rowcount` 확인으로 멱등성 보장
- `increment_failure()`: `INSERT ... ON CONFLICT(date) DO UPDATE SET failure_count = failure_count + 1`
- `check_same_thread=False` (playwright async 환경)
- 연결 관리: lazy initialization, context manager 지원

#### 1-4. `src/storage/dynamodb_backend.py` — DynamoDB 구현 (기존 코드 래핑)

**기존 `src/recipients/dynamodb_client.py`의 코드를 이 파일로 이동/래핑**하여 `StorageBackend` 인터페이스를 구현.

```python
import boto3
from .base import StorageBackend

class DynamoDBBackend(StorageBackend):
    def __init__(self, region_name="ap-northeast-2"):
        self.region_name = region_name
        self._dynamodb = None
        self._tables = {}  # 테이블별 캐시

    def _get_table(self, table_name: str):
        if table_name not in self._tables:
            if self._dynamodb is None:
                self._dynamodb = boto3.resource("dynamodb", region_name=self.region_name)
            self._tables[table_name] = self._dynamodb.Table(table_name)
        return self._tables[table_name]

    # --- Recipients (테이블: etnews-recipients) ---
    def get_recipient(self, email):
        table = self._get_table("etnews-recipients")
        response = table.get_item(Key={"email": email})
        return response.get("Item")

    # ... 나머지 메서드 구현
```

**핵심**: `boto3` import는 이 파일에만 존재. 나머지 코드는 `StorageBackend` 인터페이스만 의존.

#### 1-5. `src/storage/factory.py` — 백엔드 선택 팩토리

```python
import os
from .base import StorageBackend

def get_storage_backend() -> StorageBackend:
    """환경에 따라 적절한 스토리지 백엔드 반환"""
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    if is_lambda:
        from .dynamodb_backend import DynamoDBBackend
        return DynamoDBBackend()
    else:
        from .sqlite_backend import SQLiteBackend
        return SQLiteBackend()
```

**핵심**: `DynamoDBBackend` import는 Lambda 환경에서만 실행 → 맥미니에서 boto3 없어도 `ImportError` 발생하지 않음.

---

### 작업 2: 기존 모듈을 스토리지 추상화 레이어로 전환

**수정할 파일 5개**:

#### 2-1. `src/recipients/dynamodb_client.py` → 호환 래퍼로 전환

기존 `DynamoDBClient`를 직접 사용하는 코드가 많으므로 **급격한 변경 대신 래퍼로 전환**:

```python
"""
DynamoDB 클라이언트 (호환 래퍼)
기존 인터페이스를 유지하면서 내부적으로 StorageBackend 사용
"""
from ..storage import get_storage_backend

class DynamoDBClient:
    """기존 인터페이스 호환 래퍼 — 내부적으로 StorageBackend에 위임"""

    def __init__(self, table_name="etnews-recipients", region_name="ap-northeast-2"):
        self.table_name = table_name
        self._backend = None  # lazy init

    def _get_backend(self):
        if self._backend is None:
            self._backend = get_storage_backend()
        return self._backend

    def put_item(self, item):
        return self._get_backend().put_recipient(item)

    def get_item(self, email):
        return self._get_backend().get_recipient(email)

    # ... 나머지 메서드도 위임
```

**이 접근의 장점**:
- `recipient_manager.py`, `delivery_tracker.py` 등이 `DynamoDBClient`를 사용하는 코드를 **변경하지 않아도 됨**
- 점진적 마이그레이션 가능

#### 2-2. `src/execution_tracker.py`

- `self.db_client._get_table()` 직접 접근 → `StorageBackend`의 `get_execution()`, `put_execution()` 호출로 변경
- `DynamoDBClient` import 제거 → `get_storage_backend` 사용

```python
from .storage import get_storage_backend

class ExecutionTracker:
    def __init__(self):
        self._backend = None

    def _get_backend(self):
        if self._backend is None:
            self._backend = get_storage_backend()
        return self._backend

    def should_skip_execution(self, mode: str) -> bool:
        execution_key = self._get_execution_key(mode)
        item = self._get_backend().get_execution(execution_key)
        return item is not None

    def mark_execution(self, mode: str, request_id: str) -> bool:
        item = {
            "execution_key": execution_key,
            "date": today,
            "mode": mode,
            "request_id": request_id,
            "execution_time": now,
            "ttl": ttl
        }
        return self._get_backend().put_execution(item)
```

#### 2-3. `src/failure_tracker.py`

- `self.db_client._get_table()` 직접 접근 → `StorageBackend`의 `get_failure()`, `increment_failure()`, `delete_failure()` 호출
- 기존 `__init__`의 `table_name`, `region_name` 파라미터 제거 (StorageBackend가 관리)

#### 2-4. `src/delivery_tracker.py`

- `self.db_client.update_item()` → `self._get_backend().update_recipient()` 호출
- `DynamoDBClient` import 제거

#### 2-5. `src/recipients/recipient_manager.py`

- `_recipient_manager` 모듈 레벨 싱글톤 → lazy 초기화 변경 (R-6 해결)

```python
# 변경 전
_recipient_manager = RecipientManager()

def get_active_recipients():
    return _recipient_manager.get_active_recipients()

# 변경 후
_recipient_manager = None

def _get_manager():
    global _recipient_manager
    if _recipient_manager is None:
        _recipient_manager = RecipientManager()
    return _recipient_manager

def get_active_recipients():
    return _get_manager().get_active_recipients()
```

---

### 작업 3: ITFIND 다운로드 — Lambda invoke를 조건부 분기로 변경

**수정할 파일**: `src/workflow/pdf_workflow.py`

**현재 문제**: `download_itfind_pdf()` (104-160행)이 항상 `boto3.client('lambda').invoke()` 호출. 또한 `boto3`가 파일 상단(7행)에서 무조건 import됨.

**변경 전략**: Lambda 환경이면 Lambda invoke, 로컬이면 직접 함수 호출

```python
# 변경 전 (pdf_workflow.py 상단)
import boto3

# 변경 후
import os
# boto3는 Lambda 환경에서만 import (하단에서 조건부)
```

```python
def download_itfind_pdf():
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    if is_lambda:
        # AWS Lambda 환경: 기존 Lambda invoke 방식
        import boto3
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName='itfind-pdf-downloader',
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        result_payload = json.loads(response['Payload'].read())
        # ... 기존 Lambda 응답 처리 로직 유지
    else:
        # 로컬 환경: 직접 함수 호출
        import asyncio
        from lambda_itfind_downloader import download_itfind_pdf as _download_async
        result = asyncio.run(_download_async())
        if result is None:
            return None, None
        # result는 이미 dict (title, issue_number, pdf_base64 등)
        # ... base64 디코딩 및 파일 저장
```

**ITFIND 로직 통합 (R-7)**:
- `lambda_itfind_downloader.py`의 `get_latest_weekly_trend_from_rss()` 함수를 `src/itfind_scraper.py`의 `ItfindScraper` 클래스에서 호출하도록 변경
- `lambda_itfind_downloader.py`에서 RSS 파싱 코드 제거 → `from src.itfind_scraper import ItfindScraper` 사용

---

### 작업 4: `Config` 클래스에 스토리지 설정 추가 (R-9 해결)

**수정할 파일**: `src/config.py`

**추가할 설정**:

```python
class ConfigClass:
    # ... 기존 설정 유지 ...

    # 스토리지 설정
    DB_PATH = os.getenv('DB_PATH', 'data/itnews_sender.db')

    # DynamoDB 테이블명 (AWS 환경용)
    DYNAMODB_RECIPIENTS_TABLE = os.getenv('DYNAMODB_RECIPIENTS_TABLE', 'etnews-recipients')
    DYNAMODB_FAILURES_TABLE = os.getenv('DYNAMODB_FAILURES_TABLE', 'etnews-delivery-failures')
    DYNAMODB_EXECUTION_TABLE = os.getenv('DYNAMODB_EXECUTION_TABLE', 'etnews-execution-log')
    AWS_REGION = os.getenv('AWS_REGION', 'ap-northeast-2')
```

**`validate()` 자동 호출 제거** (R-8):

```python
# 삭제할 부분 (config.py:204-209)
# if __name__ != "__main__":
#     try:
#         Config.validate()
#     except ValueError as e:
#         print(f"경고: {e}")
```

`run_daily.py`와 `lambda_handler.py`의 시작부에서 명시적으로 `Config.validate()` 호출.

---

### 작업 5: 로컬 실행 엔트리포인트 생성

**생성할 파일**: `run_daily.py` (프로젝트 루트)

```python
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
import logging
from datetime import datetime

# 프로젝트 루트를 PYTHONPATH에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description='IT뉴스 PDF 발송')
    parser.add_argument('--mode', choices=['test', 'opr'], default='test')
    parser.add_argument('--skip-idempotency', action='store_true')
    args = parser.parse_args()

    # 로깅 설정
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    # ... RotatingFileHandler 설정 ...

    # Config 유효성 검증
    from src.config import Config
    Config.validate()

    # 핸들러 실행
    from lambda_handler import handler
    event = {'mode': args.mode, 'skip_idempotency': args.skip_idempotency}
    result = handler(event, None)

    # 결과 출력 및 종료 코드
    status_code = result.get('statusCode', 500)
    print(f"[{datetime.now().isoformat()}] 완료: statusCode={status_code}")
    sys.exit(0 if status_code == 200 else 1)

if __name__ == '__main__':
    main()
```

---

### 작업 6: macOS launchd 스케줄러 설정

**생성할 파일 2개**:

#### 6-1. `com.itnews.sender.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.itnews.sender</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/project/venv/bin/python3</string>
        <string>/path/to/project/run_daily.py</string>
        <string>--mode</string>
        <string>opr</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/project/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/project/logs/launchd_stderr.log</string>
    <key>WorkingDirectory</key>
    <string>/path/to/project</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TZ</key>
        <string>Asia/Seoul</string>
    </dict>
</dict>
</plist>
```

#### 6-2. `scripts/setup_launchd.sh`

```bash
#!/bin/bash
# launchd 스케줄러 관리
# 사용법:
#   ./scripts/setup_launchd.sh install    - 등록 및 시작
#   ./scripts/setup_launchd.sh uninstall  - 해제
#   ./scripts/setup_launchd.sh status     - 상태 확인
#   ./scripts/setup_launchd.sh logs       - 최근 로그 출력

PLIST_SRC="$(dirname "$0")/../com.itnews.sender.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.itnews.sender.plist"
LABEL="com.itnews.sender"

case "$1" in
  install)
    cp "$PLIST_SRC" "$PLIST_DST"
    launchctl load "$PLIST_DST"
    echo "등록 완료: $LABEL"
    ;;
  uninstall)
    launchctl unload "$PLIST_DST" 2>/dev/null
    rm -f "$PLIST_DST"
    echo "해제 완료: $LABEL"
    ;;
  status)
    launchctl list | grep "$LABEL" || echo "미등록"
    ;;
  logs)
    echo "=== stdout ==="
    tail -20 logs/launchd_stdout.log 2>/dev/null
    echo "=== stderr ==="
    tail -20 logs/launchd_stderr.log 2>/dev/null
    ;;
  *)
    echo "사용법: $0 {install|uninstall|status|logs}"
    ;;
esac
```

---

### 작업 7: 로그 로테이션 및 파일 로깅

**수정할 파일**: `src/structured_logging.py`

**변경 내용**:
- `logging.handlers.RotatingFileHandler` 추가 (로컬 환경에서만)
- 로그 파일: `logs/itnews_sender.log`
- maxBytes: 10MB, backupCount: 5
- Lambda 환경에서는 기존 CloudWatch 로깅 유지 (stdout)
- 로컬 환경에서는 콘솔 + 파일 동시 출력

```python
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """환경에 따른 로깅 설정"""
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 콘솔 핸들러 (양쪽 환경 모두)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(console)

    # 파일 핸들러 (로컬 환경에서만)
    if not is_lambda:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, 'itnews_sender.log'),
            maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        root_logger.addHandler(file_handler)
```

---

### 작업 8: 수신거부 핸들러 전환

**현재**: Lambda Function URL로 동작. AWS 백업으로 유지하므로 Lambda 함수 자체는 삭제하지 않음.

**로컬 환경 대응**:
- `.env`의 `UNSUBSCRIBE_FUNCTION_URL`을 **AWS Lambda Function URL 그대로 유지**
- 수신거부 요청은 여전히 AWS Lambda가 처리 (Mac Mini와 독립)
- DynamoDB의 recipients 테이블에서 수신거부 처리 → 다음 Mac Mini 실행 시 SQLite에는 반영되지 않는 문제

**동기화 해결**: `scripts/sync_recipients.py` 스크립트 생성
- DynamoDB의 recipients 데이터를 SQLite로 동기화
- 주기적 실행 (weekly) 또는 run_daily.py 시작 시 자동 실행
- 방향: DynamoDB → SQLite (단방향)
- boto3가 있을 때만 동작, 없으면 skip

**대안** (AWS Lambda 수신거부를 없앨 경우):
- `UNSUBSCRIBE_FUNCTION_URL`을 `mailto:` 링크로 변경
- 관리자가 이메일 받고 `python scripts/manage_recipients.py unsubscribe <email>` 수동 실행

---

### 작업 9: requirements.txt 분리 및 .gitignore 업데이트

**`requirements.txt` 변경** — boto3를 제거하지 않고 optional로 분리:

```
# requirements.txt (공통 — Mac Mini / AWS Lambda 공용)
playwright
beautifulsoup4
requests
pypdf
python-dotenv
python-dateutil
```

```
# requirements-aws.txt (AWS Lambda 추가 의존성)
-r requirements.txt
boto3
```

Dockerfile에서 `requirements-aws.txt` 사용:
```dockerfile
COPY requirements.txt requirements-aws.txt ./
RUN pip3 install --no-cache-dir -r requirements-aws.txt
```

**`.gitignore` 추가**:
```
# 로컬 데이터
data/
logs/
!data/.gitkeep
!logs/.gitkeep
```

**생성할 파일**:
- `data/.gitkeep`
- `logs/.gitkeep`

---

### 작업 10: DynamoDB 데이터 마이그레이션 및 동기화 스크립트

**생성할 파일**: `scripts/migrate_dynamodb_to_sqlite.py`

```python
#!/usr/bin/env python3
"""
DynamoDB → SQLite 데이터 마이그레이션
초기 1회 실행 또는 동기화용

사용법:
  python scripts/migrate_dynamodb_to_sqlite.py           # 전체 마이그레이션
  python scripts/migrate_dynamodb_to_sqlite.py --sync     # 수신인만 동기화
"""
```

**구현 요구사항**:
- boto3 import를 try/except로 감싸서 설치되지 않은 환경에서도 에러 없이 종료
- 3개 테이블 순차 마이그레이션: recipients → delivery_failures → execution_log
- `--sync` 모드: recipients 테이블만 동기화 (수신거부 반영용)
- 충돌 처리: `INSERT OR REPLACE` (SQLite)
- dry-run 모드: `--dry-run` 옵션으로 실제 삽입 없이 데이터만 출력

---

## 전체 실행 순서 (의존 관계)

```
=== Phase 0: 리팩토링 (AWS 환경 변경 없음) ===

R-1 (notification.py 버그)      ← 즉시
R-4 (중복 import 정리)          ← 즉시
R-2 (sanitize_error 통합)       ← 즉시
R-8 (Config.validate 타이밍)    ← 즉시
R-3 (email_workflow 활용)       ← 독립
    ↓
(커밋 & AWS 재배포하여 기존 환경 정상 동작 확인)

=== Phase 1: 듀얼 환경 마이그레이션 ===

작업 1 (스토리지 추상화)         ← 핵심, 가장 먼저
    ↓
작업 4 (Config 설정 추가, R-9)   ← 작업 1과 병행 가능
    ↓
작업 2 (기존 모듈 전환, R-5/R-6) ← 작업 1 완료 후
작업 3 (ITFIND 분기, R-7)       ← 작업 1 완료 후, 독립
작업 7 (로깅)                   ← 독립
    ↓
작업 9 (requirements 분리)       ← 작업 1, 2, 3 완료 후
작업 10 (데이터 마이그레이션)     ← 작업 1 완료 후
    ↓
작업 5 (run_daily.py)            ← 작업 2, 3 완료 후
    ↓
작업 8 (수신거부)                ← 작업 2, 5 완료 후
작업 6 (launchd)                 ← 작업 5 완료 후 (최종)
```

---

## 파일 변경 요약

### 신규 생성 파일

| 파일 | 목적 |
|---|---|
| `src/storage/__init__.py` | 스토리지 모듈 패키지 |
| `src/storage/base.py` | 스토리지 추상 인터페이스 (ABC) |
| `src/storage/sqlite_backend.py` | SQLite 구현 |
| `src/storage/dynamodb_backend.py` | DynamoDB 구현 (기존 코드 래핑) |
| `src/storage/factory.py` | 환경별 백엔드 팩토리 |
| `run_daily.py` | Mac Mini 로컬 엔트리포인트 |
| `com.itnews.sender.plist` | launchd 스케줄 정의 |
| `scripts/setup_launchd.sh` | launchd 관리 스크립트 |
| `scripts/migrate_dynamodb_to_sqlite.py` | 데이터 마이그레이션/동기화 |
| `requirements-aws.txt` | AWS Lambda용 추가 의존성 |
| `data/.gitkeep` | SQLite DB 디렉토리 |
| `logs/.gitkeep` | 로그 디렉토리 |

### 수정할 파일

| 파일 | 변경 내용 | Phase |
|---|---|---|
| `src/utils/notification.py` | SMTP 속성명 버그 수정 (R-1) | 0 |
| `lambda_handler.py` | 중복 import 제거(R-4), sanitize 함수 제거(R-2), email_workflow 활용(R-3) | 0 |
| `src/config.py` | DB_PATH/테이블명 추가(작업4), validate() 자동호출 제거(R-8) | 0+1 |
| `src/recipients/dynamodb_client.py` | StorageBackend 위임 래퍼로 전환 (작업2) | 1 |
| `src/execution_tracker.py` | StorageBackend 사용 (작업2) | 1 |
| `src/failure_tracker.py` | StorageBackend 사용 (작업2) | 1 |
| `src/delivery_tracker.py` | StorageBackend 사용 (작업2) | 1 |
| `src/recipients/recipient_manager.py` | lazy 싱글톤 (R-6, 작업2) | 1 |
| `src/workflow/pdf_workflow.py` | Lambda invoke 조건부 분기 (작업3), boto3 상단 import 제거 | 1 |
| `lambda_itfind_downloader.py` | RSS 파싱을 itfind_scraper로 통합 (R-7) | 1 |
| `src/structured_logging.py` | 파일 로깅 추가 (작업7) | 1 |
| `requirements.txt` | boto3 제거 (requirements-aws.txt로 분리) | 1 |
| `.gitignore` | `data/`, `logs/` 추가 | 1 |
| `Dockerfile` | requirements-aws.txt 참조로 변경 | 1 |

### 변경 불필요

| 파일 | 이유 |
|---|---|
| `src/scraper.py` | AWS 의존성 없음 |
| `src/pdf_processor.py` | AWS 의존성 없음 |
| `src/recipients/models.py` | 순수 데이터 모델 |
| `src/unsubscribe_token.py` | 순수 HMAC 로직 |
| `src/parameter_store.py` | Lambda 환경에서만 사용됨 (유지) |
| `src/api/unsubscribe_handler.py` | Lambda Function URL로 유지 |
| `src/workflow/email_workflow.py` | R-3에서 활용될 뿐 자체 변경 불필요 |
| `Dockerfile.itfind` | Lambda 백업용 유지 |

---

## 테스트 계획

### Phase 0 테스트 (리팩토링 후)

```bash
# AWS Lambda에 재배포 후 기존 동작 확인
./scripts/test_lambda.sh test skip-idempotency
# admin@example.com 수신 확인
```

### Phase 1 테스트

#### 1. 스토리지 레이어 단위 테스트 (작업 1 완료 후)
```bash
python -c "
from src.storage.sqlite_backend import SQLiteBackend
db = SQLiteBackend()
db.put_recipient({'email':'test@test.com','name':'테스트','status':'active','created_at':'2026-01-31'})
print(db.get_recipient('test@test.com'))
print(db.query_recipients_by_status('active'))
db.delete_recipient('test@test.com')
print('SQLite 테스트 통과')
"
```

#### 2. 수신인 관리 테스트 (작업 2 완료 후)
```bash
python scripts/manage_recipients.py init
python scripts/manage_recipients.py list
python scripts/manage_recipients.py list-active
```

#### 3. ITFIND 독립 테스트 (작업 3 완료 후)
```bash
python lambda_itfind_downloader.py
```

#### 4. 전체 플로우 테스트 (작업 5 완료 후)
```bash
# 반드시 test 모드 (관리자에게만 발송)
python run_daily.py --mode test --skip-idempotency

# 확인사항:
# - admin@example.com 에 news PDF 수신
# - 수요일이면 ITFIND PDF 별도 수신
# - SQLite DB 파일 생성 확인: data/itnews_sender.db
# - 로그 파일 생성 확인: logs/itnews_sender.log
```

#### 5. 멱등성 테스트
```bash
python run_daily.py --mode test
python run_daily.py --mode test  # "이미 실행됨" 확인
```

#### 6. AWS Lambda 호환성 테스트 (재배포 후)
```bash
./scripts/test_lambda.sh test skip-idempotency
# Lambda 환경에서도 정상 동작하는지 확인 (DynamoDB 사용)
```

#### 7. OPR 모드 전환 (최종)
```bash
# 1. EventBridge 비활성화
aws events disable-rule --name news-daily-trigger --region ap-northeast-2

# 2. launchd 등록
./scripts/setup_launchd.sh install

# 3. 다음 날 06:00 자동 실행 확인
./scripts/setup_launchd.sh logs
```

---

## 비상 복구 절차

### Mac Mini 장애 시

```bash
# 1. AWS EventBridge 재활성화
aws events enable-rule --name news-daily-trigger --region ap-northeast-2

# 2. 또는 수동 Lambda 호출 (당일 미발송인 경우)
aws lambda invoke --function-name etnews-pdf-sender \
  --payload '$(echo -n "{\"mode\":\"opr\",\"skip_idempotency\":true}" | base64)' \
  --region ap-northeast-2 --cli-read-timeout 300 \
  /tmp/result.json
cat /tmp/result.json
```

### Mac Mini 복구 후

```bash
# 1. EventBridge 다시 비활성화
aws events disable-rule --name news-daily-trigger --region ap-northeast-2

# 2. 수신인 동기화 (수신거부 반영)
python scripts/migrate_dynamodb_to_sqlite.py --sync

# 3. launchd 상태 확인
./scripts/setup_launchd.sh status
```

---

## 주의사항

1. **`.env` 파일 필수** — `.env.example`을 복사하여 실제 credential 입력
2. **Playwright 브라우저 설치**: `playwright install chromium`
3. **Python venv 사용**: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
4. **Mac Mini 슬립 방지**: 시스템 설정 > 에너지 절약 > "디스플레이가 꺼져 있을 때 자동 잠자기 방지" 체크
5. **`src/parameter_store.py` 삭제 금지** — Lambda 환경에서 credential 소스로 사용
6. **boto3는 Mac Mini에 설치하지 않아도 됨** — `factory.py`에서 조건부 import로 처리
7. **양쪽 환경의 멱등성 키가 서로 독립** — Mac Mini(SQLite)와 Lambda(DynamoDB)는 별도 execution_log를 가지므로 같은 날 양쪽에서 모두 실행하면 중복 발송 가능. 운영 시 한쪽만 활성화할 것.

---

## 사전 준비 체크리스트 (작업 시작 전)

```
[ ] Mac Mini에 Python 3.11+ 설치 확인
    python3 --version

[ ] 프로젝트 디렉토리 확인
    ls /path/to/project

[ ] Git 저장소 상태 확인 (clean working tree)
    cd /path/to/project
    git status

[ ] .env 파일 존재 및 credential 설정 확인
    cat .env | grep -E "ETNEWS_USER_ID|GMAIL_USER" | head -2

[ ] Python venv 생성 (아직 없으면)
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt

[ ] Playwright Chromium 설치
    playwright install chromium

[ ] AWS CLI 설치 및 설정 확인 (데이터 마이그레이션용, 선택사항)
    aws sts get-caller-identity

[ ] Mac Mini 시스템 타임존 확인
    date +%Z  # KST 또는 Asia/Seoul 이어야 함
```

---

## 상세 구현 체크리스트 (에이전트용)

각 작업 항목에 대한 상세 체크리스트. 완료 시 `[x]` 표시.

### Phase 0: 리팩토링

#### R-1. notification.py 버그 수정
```
[ ] src/utils/notification.py 열기
[ ] 46행: config.SMTP_SERVER → config.GMAIL_SMTP_SERVER 변경
[ ] 46행: config.SMTP_PORT → config.GMAIL_SMTP_PORT 변경
[ ] 저장 후 import 에러 없는지 확인:
    python -c "from src.utils.notification import send_admin_notification"
```

#### R-2. sanitize_error 중복 제거
```
[ ] lambda_handler.py에서 sanitize_error 함수 위치 확인 (47-71행)
[ ] 상단에 import 추가: from src.workflow.pdf_workflow import sanitize_error
[ ] lambda_handler.py의 로컬 sanitize_error 함수 전체 삭제 (47-71행)
[ ] 테스트: python -c "from lambda_handler import handler"
```

#### R-4. 중복 import 정리
```
[ ] lambda_handler.py 열기
[ ] 74-75행 삭제 (주석 + _send_admin_notification import)
[ ] 테스트: python -c "from lambda_handler import handler"
```

#### R-8. Config.validate 자동 호출 제거
```
[ ] src/config.py 열기
[ ] 204-209행 삭제 또는 주석 처리:
    if __name__ != "__main__":
        try:
            Config.validate()
        except ValueError as e:
            print(f"경고: {e}")
[ ] 테스트: python -c "from src.config import Config"  # 경고 없이 통과해야 함
```

#### R-3. email_workflow 활용 (선택적 — 로직 변경 큼)
```
[ ] src/workflow/email_workflow.py의 send_emails() 반환값 구조 확인
[ ] lambda_handler.py의 214-249행 검토
[ ] send_emails() 호출로 교체할 경우:
    [ ] from src.workflow import send_emails 추가
    [ ] 214-249행 대체:
        email_success, success_emails, itfind_email_success, itfind_success_emails = \
            send_emails(processed_pdf_path, is_test_mode, itfind_pdf_path, itfind_trend_info)
    [ ] 후속 로직(발송 이력 기록)에 success_emails 사용 가능 확인
[ ] 테스트 모드로 전체 플로우 테스트
```

#### Phase 0 완료 후
```
[ ] 모든 리팩토링 커밋
[ ] AWS Lambda에 재배포 (선택사항 - 백업 환경 동기화)
[ ] ./scripts/test_lambda.sh test skip-idempotency 로 기존 동작 확인
```

---

### Phase 1: 듀얼 환경 마이그레이션

#### 작업 1: 스토리지 추상화 레이어

```
[ ] src/storage/ 디렉토리 생성
    mkdir -p src/storage

[ ] src/storage/__init__.py 생성
    # 내용:
    from .base import StorageBackend
    from .factory import get_storage_backend
    __all__ = ["StorageBackend", "get_storage_backend"]

[ ] src/storage/base.py 생성 (추상 인터페이스)
    # ABC 클래스로 9개 추상 메서드 정의
    # get_recipient, put_recipient, query_recipients_by_status,
    # get_all_recipients, update_recipient, delete_recipient,
    # get_execution, put_execution,
    # get_failure, increment_failure, delete_failure

[ ] src/storage/sqlite_backend.py 생성
    [ ] SQLiteBackend 클래스 구현
    [ ] __init__: DB 파일 경로, 테이블 생성
    [ ] _get_connection: lazy connection
    [ ] 11개 메서드 구현 (base.py 인터페이스)
    [ ] TTL 정리 로직 구현

[ ] src/storage/dynamodb_backend.py 생성
    [ ] DynamoDBBackend 클래스 구현
    [ ] boto3 조건부 import (try/except)
    [ ] 11개 메서드 구현 (기존 DynamoDBClient 로직 래핑)

[ ] src/storage/factory.py 생성
    [ ] get_storage_backend() 함수 구현
    [ ] AWS_EXECUTION_ENV 환경변수로 분기

[ ] 단위 테스트
    python -c "
    from src.storage.sqlite_backend import SQLiteBackend
    db = SQLiteBackend()
    # CRUD 테스트...
    print('OK')
    "
```

#### 작업 2: 기존 모듈 전환

```
[ ] src/recipients/dynamodb_client.py 수정
    [ ] boto3 import 제거
    [ ] from ..storage import get_storage_backend 추가
    [ ] DynamoDBClient 클래스를 StorageBackend 래퍼로 변경
    [ ] 기존 메서드 시그니처 유지 (호환성)

[ ] src/execution_tracker.py 수정
    [ ] DynamoDBClient import 제거
    [ ] from .storage import get_storage_backend 추가
    [ ] _get_backend() lazy 메서드 추가
    [ ] should_skip_execution: get_execution() 사용
    [ ] mark_execution: put_execution() 사용
    [ ] _get_table() 직접 호출 모두 제거

[ ] src/failure_tracker.py 수정
    [ ] DynamoDBClient import 제거
    [ ] from .storage import get_storage_backend 추가
    [ ] _get_backend() lazy 메서드 추가
    [ ] should_skip_today: get_failure() 사용
    [ ] increment_failure: increment_failure() 사용
    [ ] reset_today: delete_failure() 사용
    [ ] _get_table() 직접 호출 모두 제거

[ ] src/delivery_tracker.py 수정
    [ ] DynamoDBClient import 제거
    [ ] from .storage import get_storage_backend 추가
    [ ] mark_as_delivered: update_recipient() 사용

[ ] src/recipients/recipient_manager.py 수정
    [ ] _recipient_manager = RecipientManager() 즉시 초기화 제거
    [ ] _recipient_manager = None 으로 변경
    [ ] _get_manager() lazy 함수 추가
    [ ] get_active_recipients(), unsubscribe_recipient() 에서 _get_manager() 사용

[ ] 수신인 관리 테스트
    python scripts/manage_recipients.py list
```

#### 작업 3: ITFIND Lambda invoke 분기

```
[ ] src/workflow/pdf_workflow.py 열기

[ ] 상단 import 수정
    [ ] import boto3 제거
    [ ] import os 추가 (없으면)

[ ] download_itfind_pdf() 함수 수정
    [ ] 함수 시작부에 환경 감지 추가:
        is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None
    [ ] if is_lambda: 블록에 기존 boto3 Lambda invoke 로직 이동
        [ ] import boto3 를 블록 내부로 이동 (조건부 import)
    [ ] else: 블록에 로컬 직접 호출 로직 추가
        [ ] import asyncio
        [ ] from lambda_itfind_downloader import download_itfind_pdf as _download_async
        [ ] result = asyncio.run(_download_async())
        [ ] base64 디코딩 및 파일 저장

[ ] 테스트 (로컬 환경)
    python -c "
    from src.workflow.pdf_workflow import download_itfind_pdf
    result = download_itfind_pdf()
    print(result)
    "
```

#### 작업 4: Config 설정 추가

```
[ ] src/config.py 열기

[ ] ConfigClass에 속성 추가 (클래스 변수):
    DB_PATH = os.getenv('DB_PATH', 'data/itnews_sender.db')
    DYNAMODB_RECIPIENTS_TABLE = os.getenv('DYNAMODB_RECIPIENTS_TABLE', 'etnews-recipients')
    DYNAMODB_FAILURES_TABLE = os.getenv('DYNAMODB_FAILURES_TABLE', 'etnews-delivery-failures')
    DYNAMODB_EXECUTION_TABLE = os.getenv('DYNAMODB_EXECUTION_TABLE', 'etnews-execution-log')
    AWS_REGION = os.getenv('AWS_REGION', 'ap-northeast-2')

[ ] 테스트
    python -c "from src.config import Config; print(Config.DB_PATH)"
```

#### 작업 5: run_daily.py 생성

```
[ ] 프로젝트 루트에 run_daily.py 생성
    [ ] #!/usr/bin/env python3 shebang
    [ ] argparse로 --mode, --skip-idempotency 옵션
    [ ] Config.validate() 호출
    [ ] lambda_handler.handler() 호출
    [ ] exit code 처리

[ ] 실행 권한 부여
    chmod +x run_daily.py

[ ] 테스트
    python run_daily.py --mode test --skip-idempotency
```

#### 작업 6: launchd 스케줄러

```
[ ] com.itnews.sender.plist 생성 (프로젝트 루트)
    [ ] python3 경로를 venv 절대경로로 설정
    [ ] run_daily.py 절대경로
    [ ] logs 디렉토리 경로
    [ ] TZ=Asia/Seoul 환경변수

[ ] scripts/setup_launchd.sh 생성
    [ ] install/uninstall/status/logs 서브커맨드
    [ ] 실행 권한: chmod +x scripts/setup_launchd.sh

[ ] 테스트 (설치하지 않고 문법만)
    plutil -lint com.itnews.sender.plist
```

#### 작업 7: 파일 로깅

```
[ ] src/structured_logging.py 수정
    [ ] from logging.handlers import RotatingFileHandler 추가
    [ ] setup_logging() 함수 추가 또는 기존 로직 수정
    [ ] 로컬 환경에서만 파일 핸들러 추가

[ ] logs/ 디렉토리 생성
    mkdir -p logs
    touch logs/.gitkeep
```

#### 작업 8: 수신거부 전략 결정

```
[ ] 전략 선택:
    [ ] A. AWS Lambda Function URL 유지 (수신거부는 AWS에서 처리)
        → 추가 작업 불필요, 단 DynamoDB→SQLite 동기화 필요
    [ ] B. mailto: 링크로 변경 (수동 처리)
        → src/email_sender.py 수정
    [ ] C. 로컬 Flask 서버 (ngrok/Cloudflare Tunnel)
        → unsubscribe_server.py 생성

[ ] 선택에 따른 구현
```

#### 작업 9: requirements 분리

```
[ ] requirements.txt에서 boto3 행 제거

[ ] requirements-aws.txt 생성:
    -r requirements.txt
    boto3

[ ] Dockerfile 수정
    [ ] COPY requirements-aws.txt 추가
    [ ] pip install -r requirements-aws.txt 로 변경

[ ] .gitignore 수정
    [ ] data/ 추가
    [ ] logs/ 추가
    [ ] !data/.gitkeep 추가
    [ ] !logs/.gitkeep 추가

[ ] 디렉토리 생성
    mkdir -p data logs
    touch data/.gitkeep logs/.gitkeep
```

#### 작업 10: 데이터 마이그레이션

```
[ ] scripts/migrate_dynamodb_to_sqlite.py 생성
    [ ] boto3 try/except import
    [ ] argparse: --sync, --dry-run 옵션
    [ ] recipients 테이블 마이그레이션
    [ ] delivery_failures 테이블 마이그레이션
    [ ] execution_log 테이블 마이그레이션

[ ] 테스트 (dry-run)
    python scripts/migrate_dynamodb_to_sqlite.py --dry-run

[ ] 실행 (boto3 있는 환경에서)
    python scripts/migrate_dynamodb_to_sqlite.py
```

---

## 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                      itnews_sender 듀얼 환경                     │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐          ┌──────────────────────┐
│     Mac Mini         │          │     AWS Lambda       │
│  (Primary - 활성)    │          │   (Backup - 대기)    │
├──────────────────────┤          ├──────────────────────┤
│                      │          │                      │
│  ┌────────────────┐  │          │  ┌────────────────┐  │
│  │ run_daily.py   │  │          │  │lambda_handler  │  │
│  │ (launchd 06:00)│  │          │  │ (EventBridge)  │  │
│  └───────┬────────┘  │          │  └───────┬────────┘  │
│          │           │          │          │           │
│          ▼           │          │          ▼           │
│  ┌────────────────┐  │          │  ┌────────────────┐  │
│  │ StorageBackend │  │          │  │ StorageBackend │  │
│  │    Factory     │  │          │  │    Factory     │  │
│  └───────┬────────┘  │          │  └───────┬────────┘  │
│          │           │          │          │           │
│          ▼           │          │          ▼           │
│  ┌────────────────┐  │          │  ┌────────────────┐  │
│  │ SQLiteBackend  │  │          │  │DynamoDBBackend │  │
│  │                │  │          │  │                │  │
│  │ data/itnews_   │  │          │  │ DynamoDB 3개   │  │
│  │ sender.db      │  │          │  │ 테이블         │  │
│  └────────────────┘  │          │  └────────────────┘  │
│                      │          │                      │
└──────────────────────┘          └──────────────────────┘
         │                                  │
         │      ┌─────────────────┐         │
         │      │  공통 로직       │         │
         │      │                 │         │
         ├─────►│ • scraper.py    │◄────────┤
                │ • pdf_processor │
                │ • email_sender  │
                │ • itfind_scraper│
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │   Gmail SMTP    │
                │   (발송)        │
                └─────────────────┘


데이터 동기화:
  DynamoDB ───────────────► SQLite
           sync_recipients.py
          (수신거부 반영, 주기적)
```

---

## 트러블슈팅 가이드

### 문제: SQLite "database is locked"

**원인**: 여러 프로세스가 동시에 DB 접근 (playwright async + main thread)

**해결**:
```python
# sqlite_backend.py에서
conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
```

---

### 문제: Playwright 브라우저 실행 실패

**원인**: Mac Mini에 GUI 없음 또는 Chromium 미설치

**해결**:
```bash
# Chromium 재설치
playwright install chromium

# 또는 headless 모드 확인 (scraper.py에서)
# headless=True 가 기본값인지 확인
```

---

### 문제: launchd 작업이 실행되지 않음

**원인**: Mac Mini 슬립, plist 문법 오류, 경로 오류

**해결**:
```bash
# 1. plist 문법 검증
plutil -lint ~/Library/LaunchAgents/com.itnews.sender.plist

# 2. 수동 로드 및 즉시 실행
launchctl load ~/Library/LaunchAgents/com.itnews.sender.plist
launchctl start com.itnews.sender

# 3. 에러 확인
cat logs/launchd_stderr.log

# 4. 시스템 로그 확인
log show --predicate 'subsystem == "com.apple.launchd"' --last 10m
```

---

### 문제: 로컬에서 "boto3 not found" 에러

**원인**: factory.py의 조건부 import가 제대로 동작하지 않음

**해결**:
```python
# factory.py 확인
def get_storage_backend():
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None
    if is_lambda:
        from .dynamodb_backend import DynamoDBBackend  # 여기서만 import
        return DynamoDBBackend()
    else:
        from .sqlite_backend import SQLiteBackend
        return SQLiteBackend()
```

확인:
```bash
# 로컬에서 boto3 없이 실행 가능해야 함
pip uninstall boto3 -y
python -c "from src.storage import get_storage_backend; print(get_storage_backend())"
```

---

### 문제: 수신거부 후 다음 발송에도 메일 수신

**원인**: AWS Lambda 수신거부(DynamoDB)가 Mac Mini SQLite에 반영 안 됨

**해결**:
```bash
# 동기화 스크립트 실행
python scripts/migrate_dynamodb_to_sqlite.py --sync
```

---

## 부록: 주요 코드 변경 예시

### A. sqlite_backend.py 핵심 구현

```python
import sqlite3
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from .base import StorageBackend

class SQLiteBackend(StorageBackend):
    def __init__(self, db_path: str = None):
        if db_path is None:
            from ..config import Config
            db_path = Config.DB_PATH
        self.db_path = db_path
        self._conn = None
        self._ensure_tables()

    def _get_connection(self):
        if self._conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_tables(self):
        conn = self._get_connection()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS recipients (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                unsubscribed_at TEXT,
                last_delivery_date TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_recipients_status ON recipients(status);

            CREATE TABLE IF NOT EXISTS delivery_failures (
                date TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                updated_at TEXT,
                ttl INTEGER
            );

            CREATE TABLE IF NOT EXISTS execution_log (
                execution_key TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                mode TEXT NOT NULL,
                request_id TEXT,
                execution_time TEXT,
                ttl INTEGER
            );
        ''')
        conn.commit()

    def _cleanup_ttl(self, table: str):
        """만료된 TTL 레코드 정리"""
        now = int(datetime.now(timezone.utc).timestamp())
        conn = self._get_connection()
        conn.execute(f"DELETE FROM {table} WHERE ttl IS NOT NULL AND ttl < ?", (now,))
        conn.commit()

    # --- Recipients ---
    def get_recipient(self, email: str) -> Optional[Dict]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM recipients WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def put_recipient(self, item: Dict) -> bool:
        conn = self._get_connection()
        conn.execute('''
            INSERT OR REPLACE INTO recipients (email, name, status, created_at, unsubscribed_at, last_delivery_date)
            VALUES (:email, :name, :status, :created_at, :unsubscribed_at, :last_delivery_date)
        ''', item)
        conn.commit()
        return True

    def query_recipients_by_status(self, status: str) -> List[Dict]:
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM recipients WHERE status = ?", (status,)).fetchall()
        return [dict(r) for r in rows]

    def get_all_recipients(self) -> List[Dict]:
        conn = self._get_connection()
        rows = conn.execute("SELECT * FROM recipients").fetchall()
        return [dict(r) for r in rows]

    def update_recipient(self, email: str, updates: Dict) -> bool:
        if not updates:
            return True
        set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
        params = {**updates, "email": email}
        conn = self._get_connection()
        conn.execute(f"UPDATE recipients SET {set_clause} WHERE email = :email", params)
        conn.commit()
        return True

    def delete_recipient(self, email: str) -> bool:
        conn = self._get_connection()
        conn.execute("DELETE FROM recipients WHERE email = ?", (email,))
        conn.commit()
        return True

    # --- Execution Log ---
    def get_execution(self, execution_key: str) -> Optional[Dict]:
        self._cleanup_ttl("execution_log")
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM execution_log WHERE execution_key = ?", (execution_key,)).fetchone()
        return dict(row) if row else None

    def put_execution(self, item: Dict) -> bool:
        """INSERT OR IGNORE로 멱등성 보장. 이미 존재하면 False 반환."""
        conn = self._get_connection()
        cursor = conn.execute('''
            INSERT OR IGNORE INTO execution_log (execution_key, date, mode, request_id, execution_time, ttl)
            VALUES (:execution_key, :date, :mode, :request_id, :execution_time, :ttl)
        ''', item)
        conn.commit()
        return cursor.rowcount > 0  # 삽입되었으면 True, 이미 존재하면 False

    # --- Failure Tracking ---
    def get_failure(self, date: str) -> Optional[Dict]:
        self._cleanup_ttl("delivery_failures")
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM delivery_failures WHERE date = ?", (date,)).fetchone()
        return dict(row) if row else None

    def increment_failure(self, date: str, error: str) -> int:
        self._cleanup_ttl("delivery_failures")
        now = datetime.now(timezone.utc).isoformat()
        ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
        conn = self._get_connection()
        conn.execute('''
            INSERT INTO delivery_failures (date, failure_count, last_error, updated_at, ttl)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                failure_count = failure_count + 1,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
        ''', (date, error[:500], now, ttl))
        conn.commit()
        row = conn.execute("SELECT failure_count FROM delivery_failures WHERE date = ?", (date,)).fetchone()
        return row[0] if row else 1

    def delete_failure(self, date: str) -> bool:
        conn = self._get_connection()
        conn.execute("DELETE FROM delivery_failures WHERE date = ?", (date,))
        conn.commit()
        return True
```

---

### B. factory.py 구현

```python
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import StorageBackend

def get_storage_backend() -> "StorageBackend":
    """
    환경에 따라 적절한 스토리지 백엔드 반환.

    - AWS Lambda 환경: DynamoDBBackend (boto3 사용)
    - 로컬 환경: SQLiteBackend

    boto3는 Lambda 환경에서만 import되므로,
    Mac Mini에서 boto3가 설치되지 않아도 에러 없음.
    """
    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    if is_lambda:
        from .dynamodb_backend import DynamoDBBackend
        return DynamoDBBackend()
    else:
        from .sqlite_backend import SQLiteBackend
        return SQLiteBackend()
```

---

### C. pdf_workflow.py download_itfind_pdf 분기 예시

```python
def download_itfind_pdf() -> Tuple[Optional[str], Optional[object]]:
    """
    ITFIND 주간기술동향 PDF 다운로드

    Lambda 환경: Lambda invoke로 itfind-pdf-downloader 호출
    로컬 환경: lambda_itfind_downloader.download_itfind_pdf() 직접 호출
    """
    import os
    logger.info("2-1단계: ITFIND 주간기술동향 다운로드 시도")

    is_lambda = os.environ.get('AWS_EXECUTION_ENV') is not None

    try:
        if is_lambda:
            # === AWS Lambda 환경: 기존 방식 유지 ===
            import boto3
            import json

            lambda_client = boto3.client('lambda')
            logger.info("ITFIND Lambda 함수 호출 중... (Lambda invoke)")

            response = lambda_client.invoke(
                FunctionName='itfind-pdf-downloader',
                InvocationType='RequestResponse',
                Payload=json.dumps({})
            )
            result_payload = json.loads(response['Payload'].read())
            logger.info(f"ITFIND Lambda 응답: statusCode={result_payload.get('statusCode')}")

            if result_payload.get('statusCode') == 200 and result_payload['body']['success']:
                data = result_payload['body']['data']
            else:
                logger.warning("ITFIND PDF를 찾지 못했습니다")
                return None, None

        else:
            # === 로컬 환경: 직접 함수 호출 ===
            import asyncio
            from lambda_itfind_downloader import download_itfind_pdf as _download_async

            logger.info("ITFIND 다운로드 함수 직접 호출 중... (로컬 모드)")
            data = asyncio.run(_download_async())

            if data is None:
                logger.warning("ITFIND PDF를 찾지 못했습니다")
                return None, None

        # === 공통: base64 디코딩 및 파일 저장 ===
        pdf_base64 = data['pdf_base64']
        pdf_data = base64.b64decode(pdf_base64)

        from .config import Config
        itfind_pdf_path = os.path.join(Config.TEMP_DIR, data['filename'])
        with open(itfind_pdf_path, 'wb') as f:
            f.write(pdf_data)

        logger.info(f"✅ ITFIND PDF 다운로드 성공: {itfind_pdf_path}")

        # WeeklyTrend namedtuple 생성
        WeeklyTrend = namedtuple('WeeklyTrend', ['title', 'issue_number', 'publish_date', 'pdf_url', 'topics', 'detail_id'])
        itfind_trend_info = WeeklyTrend(
            title=data['title'],
            issue_number=data['issue_number'],
            publish_date=data['publish_date'],
            pdf_url='',
            topics=data.get('topics', []),
            detail_id=''
        )

        return itfind_pdf_path, itfind_trend_info

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 중 오류: {e}")
        return None, None
```

---

**문서 끝**
