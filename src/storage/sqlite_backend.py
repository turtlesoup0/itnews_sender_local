"""
SQLite 스토리지 백엔드 구현
Mac Mini 로컬 환경에서 SQLite를 사용하여 DynamoDB를 대체
"""

import logging
import sqlite3
import os
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

from .base import StorageBackend

logger = logging.getLogger(__name__)


class SQLiteBackend(StorageBackend):
    """SQLite 스토리지 백엔드"""

    def __init__(self):
        """SQLiteBackend 초기화 및 DB 연결 설정"""
        self._connection = None
        self._tables_created = False

        from ..config import Config

        self.db_path = Config.DB_PATH

    def _get_connection(self):
        """Lazy connection: DB 커넥션 생성 (이미 생성된 경우 재사용)"""
        if self._connection is None:
            # 데이터베이스 디렉토리 자동 생성
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            # 비동기 환경(playwright)을 위한 설정
            self._connection = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30.0
            )

            # WAL 모드 사용 (동시성 개선)
            self._connection.execute("PRAGMA journal_mode=WAL")

            logger.info(f"SQLite DB 연결: {self.db_path}")

            # 테이블 자동 생성 (최초 연결 시)
            if not self._tables_created:
                self._create_tables_impl()

        return self._connection

    def _create_tables(self):
        """테이블 자동 생성 (외부 호출용)"""
        self._get_connection()  # _get_connection 안에서 테이블 생성됨

    def _create_tables_impl(self):
        """테이블 자동 생성 (내부 구현)"""
        cursor = self._connection.cursor()

        # 1. 수신인 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recipients (
                email TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                unsubscribed_at TEXT,
                last_delivery_date TEXT
            )
        """)

        # 인덱스 생성
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recipients_status
            ON recipients(status)
        """)

        # 2. 실패 추적 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS delivery_failures (
                date TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                updated_at TEXT,
                ttl INTEGER
            )
        """)

        # 3. 실행 이력 테이블
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS execution_log (
                execution_key TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                mode TEXT NOT NULL,
                request_id TEXT,
                execution_time TEXT,
                ttl INTEGER
            )
        """)

        self._connection.commit()
        self._tables_created = True
        logger.info("SQLite 테이블 생성 완료")

    def _cleanup_expired_items(self, cursor, ttl_table: str):
        """TTL 만료된 아이템 정리 (실행 이력 테이블)"""
        now = int((datetime.now(timezone.utc)).timestamp())
        cursor.execute(f"""
            DELETE FROM {ttl_table}
            WHERE ttl IS NOT NULL AND ttl < {now}
        """)

    # --- Recipients ---
    def get_recipient(self, email: str) -> Optional[Dict]:
        """수신인 정보 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM recipients WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))

        return None

    def put_recipient(self, item: Dict) -> bool:
        """수신인 정보 저장 (이미 존재하면 업데이트)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT OR REPLACE INTO recipients
            (email, name, status, created_at, unsubscribed_at, last_delivery_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                item.get("email"),
                item.get("name", ""),
                item.get("status", "active"),
                item.get("created_at", now),
                item.get("unsubscribed_at"),
                item.get("last_delivery_date"),
            ),
        )

        conn.commit()
        logger.info(f"수신인 저장: {item.get('email')}")
        return True

    def query_recipients_by_status(self, status: str) -> List[Dict]:
        """상태별 수신인 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM recipients WHERE status = ?
            ORDER BY created_at DESC
        """,
            (status,),
        )

        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        logger.info(f"상태별 수신인 조회: {status} ({len(results)}건)")
        return results

    def get_all_recipients(self) -> List[Dict]:
        """모든 수신인 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM recipients ORDER BY created_at DESC")

        columns = [description[0] for description in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        logger.info(f"모든 수신인 조회: {len(results)}건")
        return results

    def update_recipient(self, email: str, updates: Dict) -> bool:
        """수신인 정보 업데이트"""
        conn = self._get_connection()
        cursor = conn.cursor()

        allowed_fields = ["name", "status", "unsubscribed_at", "last_delivery_date"]
        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

        if not update_fields:
            return True

        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values()) + [email]

        cursor.execute(
            f"""
            UPDATE recipients SET {set_clause} WHERE email = ?
        """,
            values,
        )

        conn.commit()
        logger.info(f"수신인 업데이트: {email}")
        return True

    def delete_recipient(self, email: str) -> bool:
        """수신인 정보 삭제"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM recipients WHERE email = ?", (email,))
        conn.commit()

        logger.info(f"수신인 삭제: {email}")
        return True

    # --- Execution Log ---
    def get_execution(self, execution_key: str) -> Optional[Dict]:
        """실행 기록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        self._cleanup_expired_items(cursor, "execution_log")

        cursor.execute(
            "SELECT * FROM execution_log WHERE execution_key = ?", (execution_key,)
        )
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))

        return None

    def put_execution(self, item: Dict) -> bool:
        """
        실행 기록 삽입 (멱등성 보장)
        SQLite의 INSERT OR IGNORE 기능 사용
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

        cursor.execute(
            """
            INSERT OR IGNORE INTO execution_log
            (execution_key, date, mode, request_id, execution_time, ttl)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                item.get("execution_key"),
                item.get("date"),
                item.get("mode"),
                item.get("request_id"),
                item.get("execution_time"),
                ttl,
            ),
        )

        conn.commit()
        inserted = cursor.rowcount > 0
        logger.info(f"실행 기록: {item.get('execution_key')} (삽입: {inserted})")
        return inserted

    # --- Failure Tracking ---
    def get_failure(self, date: str) -> Optional[Dict]:
        """실패 기록 조회"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM delivery_failures WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))

        return None

    def increment_failure(self, date: str, error: str) -> int:
        """실패 카운트 원자적 증가 (INSERT ... ON CONFLICT ...)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()
        ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())

        cursor.execute(
            """
            INSERT INTO delivery_failures (date, failure_count, last_error, updated_at, ttl)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT(date)
            DO UPDATE SET
                failure_count = failure_count + 1,
                last_error = ?,
                updated_at = ?,
                ttl = ?
        """,
            (date, error[:500], now, ttl, error[:500], now, ttl),
        )

        conn.commit()

        # 증가 후 카운트 확인
        cursor.execute(
            "SELECT failure_count FROM delivery_failures WHERE date = ?", (date,)
        )
        row = cursor.fetchone()
        new_count = row[0] if row else 1

        logger.info(f"실패 카운트 증가: {date} - {new_count}회")
        return new_count

    def delete_failure(self, date: str) -> bool:
        """실패 기록 삭제 (성공 후 리셋용)"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM delivery_failures WHERE date = ?", (date,))
        conn.commit()

        logger.info(f"실패 기록 삭제: {date}")
        return True

    def __del__(self):
        """DB 커넥션 종료"""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
