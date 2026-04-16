"""
Gmail 보관함 정리 스크립트 (S4′)

목적
----
벌크 발송용 Gmail 계정의 **보낸편지함** 에 누적되는 대용량 첨부 메일을
N일(기본 7일) 보존 후 영구 삭제하여 보관함 용량을 안정적으로 유지한다.

동작 개요
---------
1. IMAP(SSL) 로 Gmail 접속 → GMAIL_USER / GMAIL_APP_PASSWORD 사용
2. `\\Sent` SPECIAL-USE 속성을 가진 메일함을 자동 탐색 (한/영 로케일 무관)
3. `SEARCH BEFORE <cutoff>` 로 오래된 메시지 UID 목록 조회
4. 각 UID 에 `\\Deleted` 플래그 + `EXPUNGE` → 보낸편지함에서 제거
5. `[Gmail]/휴지통` 또는 `\\Trash` 메일함 선택 후 `EXPUNGE` → 즉시 영구삭제

안전장치
--------
- `DRY_RUN=1` (환경변수) 또는 `--dry-run` 플래그로 삭제 없이 건수만 출력
- `RETENTION_DAYS` (기본 7) 환경변수로 보존 기간 오버라이드
- 대상 메일함을 `\\Sent` 플래그로만 선택 — 받은편지함/중요 라벨 절대 건드리지 않음
- IMAP `BEFORE` 필터는 "그 날짜 00:00 이전" 기준 → 경계일 오차 1일 여유

CLI
---
    # 실삭제 (기본 7일 보존)
    python scripts/gmail_cleanup.py

    # 30일 보존으로 dry-run
    RETENTION_DAYS=30 python scripts/gmail_cleanup.py --dry-run
"""
from __future__ import annotations

import argparse
import imaplib
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

# 프로젝트 루트를 path 에 추가하여 Config 재사용
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import Config  # noqa: E402

logger = logging.getLogger("gmail_cleanup")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Gmail 특수 메일함 후보 (locale 대응) — \Sent / \Trash 탐지 실패 시 fallback
SENT_FALLBACK_NAMES = [
    "[Gmail]/Sent Mail",
    "[Gmail]/보낸편지함",
]
TRASH_FALLBACK_NAMES = [
    "[Gmail]/Trash",
    "[Gmail]/휴지통",
]


@dataclass
class CleanupReport:
    """정리 결과 보고서"""

    retention_days: int
    cutoff_date: str
    sent_mailbox: Optional[str] = None
    trash_mailbox: Optional[str] = None
    candidate_count: int = 0
    deleted_count: int = 0
    trash_purged: bool = False
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"[Gmail Cleanup] retention={self.retention_days}d, cutoff={self.cutoff_date}",
            f"  mailbox(sent)  = {self.sent_mailbox}",
            f"  mailbox(trash) = {self.trash_mailbox}",
            f"  candidates     = {self.candidate_count}",
            f"  deleted        = {self.deleted_count} "
            f"{'(DRY RUN)' if self.dry_run else ''}",
            f"  trash purged   = {self.trash_purged}",
        ]
        if self.errors:
            lines.append(f"  errors         = {len(self.errors)}")
            for e in self.errors:
                lines.append(f"    - {e}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pure helpers (단위 테스트 용이성 우선)
# ---------------------------------------------------------------------------

def format_imap_date(dt: datetime) -> str:
    """IMAP 검색용 날짜 문자열 (DD-Mon-YYYY)"""
    return dt.strftime("%d-%b-%Y")


def compute_cutoff(now: datetime, retention_days: int) -> datetime:
    """보존 경계일 계산 (now 기준 retention_days 일 이전)"""
    if retention_days < 1:
        raise ValueError(f"retention_days must be >= 1, got {retention_days}")
    return now - timedelta(days=retention_days)


def find_special_mailbox(
    list_response: list[bytes], flag: str, fallbacks: list[str]
) -> Optional[str]:
    """IMAP LIST 응답에서 SPECIAL-USE 플래그가 붙은 메일함 찾기.

    Args:
        list_response: imap.list()[1] 결과 (bytes lines)
        flag: 탐색할 플래그 (예: "\\Sent", "\\Trash")
        fallbacks: 플래그 미발견 시 이름 매칭 후보

    Returns:
        메일함 이름 (IMAP 인코딩 그대로) 또는 None
    """
    if not list_response:
        return None

    import re

    # IMAP LIST 라인의 마지막 항목(메일함 이름) 추출
    # 형식 1: (flags) "delim" "mailbox name"   ← 따옴표 감싼 경우
    # 형식 2: (flags) "delim" mailbox           ← unquoted (공백 없는 이름)
    mailbox_re = re.compile(r'^\([^)]*\)\s+"[^"]*"\s+(?:"([^"]*)"|(\S+))\s*$')

    flag_lower = flag.lower()
    for raw in list_response:
        if raw is None:
            continue
        line = (
            raw.decode("utf-8", errors="replace")
            if isinstance(raw, bytes) else str(raw)
        ).strip()
        if "(" not in line or ")" not in line:
            continue
        flags_part = line[line.index("(") + 1 : line.index(")")]
        if flag_lower not in flags_part.lower():
            continue
        m = mailbox_re.match(line)
        if m:
            mailbox = m.group(1) or m.group(2)
            if mailbox:
                return mailbox

    # fallback: 이름 직매칭
    for raw in list_response:
        if raw is None:
            continue
        line = (
            raw.decode("utf-8", errors="replace")
            if isinstance(raw, bytes) else str(raw)
        )
        for name in fallbacks:
            if f'"{name}"' in line or line.rstrip().endswith(name):
                return name
    return None


# ---------------------------------------------------------------------------
# IMAP operations
# ---------------------------------------------------------------------------

def _imap_check(tag: str, typ: str, data) -> None:
    """IMAP 응답 검사 — OK 아니면 예외"""
    if typ != "OK":
        raise RuntimeError(f"IMAP {tag} failed: typ={typ}, data={data!r}")


def open_imap(user: str, password: str) -> imaplib.IMAP4_SSL:
    """IMAP SSL 연결 + 로그인"""
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    typ, data = imap.login(user, password)
    _imap_check("LOGIN", typ, data)
    logger.info(f"IMAP 로그인 성공: {user}")
    return imap


def discover_mailboxes(imap: imaplib.IMAP4_SSL) -> tuple[Optional[str], Optional[str]]:
    """보낸편지함 / 휴지통 자동 탐색"""
    typ, list_data = imap.list()
    _imap_check("LIST", typ, list_data)
    sent = find_special_mailbox(list_data, "\\Sent", SENT_FALLBACK_NAMES)
    trash = find_special_mailbox(list_data, "\\Trash", TRASH_FALLBACK_NAMES)
    return sent, trash


def find_old_message_uids(
    imap: imaplib.IMAP4_SSL, mailbox: str, cutoff: datetime
) -> list[bytes]:
    """지정 메일함에서 cutoff 이전 메시지 UID 목록"""
    # SELECT (readonly=False — 실제 플래그 수정이 필요하므로 read-write)
    typ, _ = imap.select(f'"{mailbox}"')
    _imap_check("SELECT", typ, mailbox)

    before_str = format_imap_date(cutoff)
    typ, search_data = imap.uid("SEARCH", None, f'(BEFORE "{before_str}")')
    _imap_check("SEARCH", typ, search_data)

    if not search_data or not search_data[0]:
        return []
    # search_data[0] 예: b"1 2 3 4"
    raw = search_data[0]
    if isinstance(raw, (bytes, bytearray)):
        tokens = raw.split()
    else:
        tokens = str(raw).split()
    return [t if isinstance(t, bytes) else t.encode() for t in tokens if t]


def mark_uids_deleted(
    imap: imaplib.IMAP4_SSL, uids: list[bytes], batch_size: int = 500
) -> int:
    """UID 들에 \\Deleted 플래그 설정 + EXPUNGE"""
    if not uids:
        return 0

    deleted = 0
    for i in range(0, len(uids), batch_size):
        batch = uids[i : i + batch_size]
        uid_seq = b",".join(batch).decode()
        typ, _ = imap.uid("STORE", uid_seq, "+FLAGS", "(\\Deleted)")
        _imap_check("STORE", typ, uid_seq)
        deleted += len(batch)

    typ, _ = imap.expunge()
    _imap_check("EXPUNGE", typ, None)
    logger.info(f"보낸편지함 EXPUNGE 완료: {deleted}건")
    return deleted


def purge_trash(imap: imaplib.IMAP4_SSL, trash_mailbox: str) -> bool:
    """휴지통 선택 후 전체 EXPUNGE (즉시 영구삭제)"""
    typ, _ = imap.select(f'"{trash_mailbox}"')
    _imap_check("SELECT TRASH", typ, trash_mailbox)
    # 휴지통의 모든 메시지에 \Deleted 플래그 + EXPUNGE
    typ, search_data = imap.uid("SEARCH", None, "ALL")
    _imap_check("SEARCH TRASH", typ, search_data)

    raw = search_data[0] if search_data else b""
    if not raw:
        logger.info("휴지통이 이미 비어있음")
        return True

    tokens = raw.split() if isinstance(raw, (bytes, bytearray)) else str(raw).split()
    uids = [t if isinstance(t, bytes) else t.encode() for t in tokens if t]

    if uids:
        typ, _ = imap.uid("STORE", b",".join(uids).decode(), "+FLAGS", "(\\Deleted)")
        _imap_check("STORE TRASH", typ, None)
    typ, _ = imap.expunge()
    _imap_check("EXPUNGE TRASH", typ, None)
    logger.info(f"휴지통 영구삭제 완료: {len(uids)}건")
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def cleanup_sent_mails(
    retention_days: int = 7,
    dry_run: bool = False,
    now: Optional[datetime] = None,
    imap_factory=None,
) -> CleanupReport:
    """Gmail 보낸편지함 정리 메인 엔트리.

    Args:
        retention_days: 보존 기간 (일)
        dry_run: True면 삭제하지 않고 건수만 수집
        now: 현재 시각 (테스트 주입용)
        imap_factory: IMAP 연결 팩토리 (테스트 주입용). None이면 open_imap 사용

    Returns:
        CleanupReport
    """
    now = now or datetime.now(timezone.utc)
    cutoff = compute_cutoff(now, retention_days)

    report = CleanupReport(
        retention_days=retention_days,
        cutoff_date=format_imap_date(cutoff),
        dry_run=dry_run,
    )

    user = Config.GMAIL_USER
    password = Config.GMAIL_APP_PASSWORD
    if not user or not password:
        report.errors.append("GMAIL_USER 또는 GMAIL_APP_PASSWORD 미설정")
        return report

    factory = imap_factory or (lambda: open_imap(user, password))
    imap = None
    try:
        imap = factory()

        sent_mb, trash_mb = discover_mailboxes(imap)
        report.sent_mailbox = sent_mb
        report.trash_mailbox = trash_mb

        if not sent_mb:
            report.errors.append("보낸편지함 메일함을 찾을 수 없음 (\\Sent)")
            return report

        uids = find_old_message_uids(imap, sent_mb, cutoff)
        report.candidate_count = len(uids)

        if dry_run:
            logger.info(f"[DRY RUN] 삭제 대상 {len(uids)}건 — 실제 삭제 없이 종료")
            return report

        if uids:
            report.deleted_count = mark_uids_deleted(imap, uids)

        if trash_mb:
            report.trash_purged = purge_trash(imap, trash_mb)
        else:
            report.errors.append("휴지통 메일함을 찾을 수 없음 (\\Trash)")

        return report

    except Exception as e:
        logger.exception("Gmail cleanup 중 예외")
        report.errors.append(f"{type(e).__name__}: {e}")
        return report
    finally:
        if imap is not None:
            try:
                imap.logout()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gmail 보낸편지함 정리 (7일 보존)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실삭제 없이 후보 개수만 출력",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("RETENTION_DAYS", "7")),
        help="보존 일수 (기본: RETENTION_DAYS env 또는 7)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    dry_run = args.dry_run or os.environ.get("DRY_RUN") == "1"
    report = cleanup_sent_mails(
        retention_days=args.retention_days, dry_run=dry_run
    )
    print(report.summary())
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
