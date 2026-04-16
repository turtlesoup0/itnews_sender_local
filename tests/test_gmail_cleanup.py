"""
Gmail Cleanup Tests (S4′)

단위 테스트 — IMAP 서버에 실제로 연결하지 않고 mock 으로 로직 검증.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.gmail_cleanup import (  # noqa: E402
    CleanupReport,
    cleanup_sent_mails,
    compute_cutoff,
    find_old_message_uids,
    find_special_mailbox,
    format_imap_date,
    mark_uids_deleted,
    purge_trash,
)


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

class TestPureHelpers:
    def test_format_imap_date(self):
        dt = datetime(2026, 4, 17, tzinfo=timezone.utc)
        assert format_imap_date(dt) == "17-Apr-2026"

    def test_compute_cutoff_7days(self):
        now = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
        cutoff = compute_cutoff(now, 7)
        assert cutoff == datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)

    def test_compute_cutoff_rejects_zero(self):
        with pytest.raises(ValueError):
            compute_cutoff(datetime.now(timezone.utc), 0)

    def test_compute_cutoff_rejects_negative(self):
        with pytest.raises(ValueError):
            compute_cutoff(datetime.now(timezone.utc), -3)


class TestFindSpecialMailbox:
    def test_finds_sent_by_special_use_flag(self):
        resp = [
            b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
            b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Trash"',
        ]
        assert find_special_mailbox(resp, "\\Sent", []) == "[Gmail]/Sent Mail"

    def test_finds_trash_by_special_use_flag(self):
        resp = [
            b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
            b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Trash"',
        ]
        assert find_special_mailbox(resp, "\\Trash", []) == "[Gmail]/Trash"

    def test_falls_back_to_name_match(self):
        # 플래그 없음 → fallback 이름 매칭
        resp = [
            b'(\\HasNoChildren) "/" "INBOX"',
            '(\\HasNoChildren) "/" "[Gmail]/보낸편지함"'.encode("utf-8"),
        ]
        found = find_special_mailbox(
            resp, "\\Sent", ["[Gmail]/Sent Mail", "[Gmail]/보낸편지함"]
        )
        assert found == "[Gmail]/보낸편지함"

    def test_returns_none_when_absent(self):
        resp = [b'(\\HasNoChildren) "/" "INBOX"']
        assert find_special_mailbox(resp, "\\Sent", []) is None

    def test_handles_empty_list(self):
        assert find_special_mailbox([], "\\Sent", []) is None


# ---------------------------------------------------------------------------
# IMAP command tests (mocked)
# ---------------------------------------------------------------------------

class TestFindOldMessageUids:
    def test_search_uses_before_filter(self):
        imap = MagicMock()
        imap.select.return_value = ("OK", [b"10"])
        imap.uid.return_value = ("OK", [b"1 2 3"])

        cutoff = datetime(2026, 4, 10, tzinfo=timezone.utc)
        uids = find_old_message_uids(imap, "[Gmail]/Sent Mail", cutoff)

        assert uids == [b"1", b"2", b"3"]
        imap.select.assert_called_once_with('"[Gmail]/Sent Mail"')
        # SEARCH 쿼리에 BEFORE 10-Apr-2026 이 포함되어야 함
        args, _ = imap.uid.call_args
        assert args[0] == "SEARCH"
        assert '(BEFORE "10-Apr-2026")' in args[2]

    def test_empty_search_result(self):
        imap = MagicMock()
        imap.select.return_value = ("OK", [b"0"])
        imap.uid.return_value = ("OK", [b""])

        uids = find_old_message_uids(
            imap, "[Gmail]/Sent Mail", datetime(2026, 4, 10, tzinfo=timezone.utc)
        )
        assert uids == []

    def test_select_failure_raises(self):
        imap = MagicMock()
        imap.select.return_value = ("NO", [b"NOT FOUND"])

        with pytest.raises(RuntimeError, match="SELECT"):
            find_old_message_uids(
                imap, "nope", datetime(2026, 4, 10, tzinfo=timezone.utc)
            )


class TestMarkUidsDeleted:
    def test_zero_uids_noop(self):
        imap = MagicMock()
        assert mark_uids_deleted(imap, []) == 0
        imap.uid.assert_not_called()
        imap.expunge.assert_not_called()

    def test_marks_and_expunges(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b""])
        imap.expunge.return_value = ("OK", [b""])

        count = mark_uids_deleted(imap, [b"1", b"2", b"3"])

        assert count == 3
        # UID STORE 호출 확인
        args, _ = imap.uid.call_args
        assert args[0] == "STORE"
        assert args[1] == "1,2,3"
        assert args[2] == "+FLAGS"
        assert args[3] == "(\\Deleted)"
        imap.expunge.assert_called_once()

    def test_batches_large_uid_lists(self):
        imap = MagicMock()
        imap.uid.return_value = ("OK", [b""])
        imap.expunge.return_value = ("OK", [b""])

        uids = [str(i).encode() for i in range(1200)]
        count = mark_uids_deleted(imap, uids, batch_size=500)

        assert count == 1200
        # 1200 / 500 = 3 batches → STORE 3회, EXPUNGE 1회
        assert imap.uid.call_count == 3
        imap.expunge.assert_called_once()


class TestPurgeTrash:
    def test_purges_nonempty_trash(self):
        imap = MagicMock()
        imap.select.return_value = ("OK", [b"5"])
        imap.uid.side_effect = [
            ("OK", [b"1 2 3 4 5"]),  # SEARCH ALL
            ("OK", [b""]),            # STORE +FLAGS \Deleted
        ]
        imap.expunge.return_value = ("OK", [b""])

        assert purge_trash(imap, "[Gmail]/Trash") is True
        imap.select.assert_called_once_with('"[Gmail]/Trash"')
        imap.expunge.assert_called_once()

    def test_empty_trash_is_still_ok(self):
        imap = MagicMock()
        imap.select.return_value = ("OK", [b"0"])
        imap.uid.return_value = ("OK", [b""])
        imap.expunge.return_value = ("OK", [b""])

        assert purge_trash(imap, "[Gmail]/Trash") is True


# ---------------------------------------------------------------------------
# Orchestration tests — cleanup_sent_mails end-to-end with injected imap
# ---------------------------------------------------------------------------

def _make_fake_imap(sent_uids: list[bytes], trash_uids: list[bytes]):
    """테스트용 fake IMAP — select 대상에 따라 SEARCH 결과 분기"""
    imap = MagicMock()
    state = {"current": None}

    def select(mbox):
        state["current"] = mbox.strip('"')
        return ("OK", [b"1"])

    def uid_op(op, *args):
        if op == "SEARCH":
            # args: (None, '(BEFORE "...")') for sent, (None, "ALL") for trash
            if state["current"] and "Trash" in state["current"] or (
                state["current"] and "휴지통" in state["current"]
            ):
                return ("OK", [b" ".join(trash_uids) if trash_uids else b""])
            return ("OK", [b" ".join(sent_uids) if sent_uids else b""])
        if op == "STORE":
            return ("OK", [b""])
        return ("OK", [b""])

    imap.select.side_effect = select
    imap.uid.side_effect = uid_op
    imap.expunge.return_value = ("OK", [b""])
    imap.list.return_value = (
        "OK",
        [
            b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"',
            b'(\\HasNoChildren \\Trash) "/" "[Gmail]/Trash"',
        ],
    )
    imap.logout.return_value = ("BYE", [b""])
    return imap


def _fake_get_credential(key: str, default: str = "") -> str:
    """Config.get_credential 대체 (테스트용 고정 자격증명)"""
    return {
        "GMAIL_USER": "tester@example.com",
        "GMAIL_APP_PASSWORD": "fake-password",
    }.get(key, default)


@patch(
    "scripts.gmail_cleanup.Config.get_credential",
    side_effect=_fake_get_credential,
)
class TestCleanupOrchestration:
    def test_dry_run_does_not_delete(self, _mock_cred):
        imap = _make_fake_imap(sent_uids=[b"1", b"2", b"3"], trash_uids=[])
        report = cleanup_sent_mails(
            retention_days=7,
            dry_run=True,
            now=datetime(2026, 4, 17, tzinfo=timezone.utc),
            imap_factory=lambda: imap,
        )

        assert report.dry_run is True
        assert report.candidate_count == 3
        assert report.deleted_count == 0
        assert report.trash_purged is False
        # STORE / EXPUNGE 호출 없음 (SEARCH 만 수행)
        store_calls = [c for c in imap.uid.call_args_list if c.args[0] == "STORE"]
        assert store_calls == []
        imap.expunge.assert_not_called()

    def test_real_run_deletes_and_purges_trash(self, _mock_cred):
        imap = _make_fake_imap(
            sent_uids=[b"1", b"2", b"3"], trash_uids=[b"100", b"101"]
        )
        report = cleanup_sent_mails(
            retention_days=7,
            dry_run=False,
            now=datetime(2026, 4, 17, tzinfo=timezone.utc),
            imap_factory=lambda: imap,
        )

        assert report.candidate_count == 3
        assert report.deleted_count == 3
        assert report.trash_purged is True
        assert report.errors == []
        # EXPUNGE 2회 (보낸편지함 + 휴지통)
        assert imap.expunge.call_count == 2

    def test_uses_7_day_cutoff_in_search(self, _mock_cred):
        imap = _make_fake_imap(sent_uids=[], trash_uids=[])
        cleanup_sent_mails(
            retention_days=7,
            dry_run=True,
            now=datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc),
            imap_factory=lambda: imap,
        )
        # SEARCH 호출 중 BEFORE "10-Apr-2026" 확인
        search_calls = [c for c in imap.uid.call_args_list if c.args[0] == "SEARCH"]
        assert any('BEFORE "10-Apr-2026"' in str(c.args) for c in search_calls), (
            f"expected BEFORE '10-Apr-2026', got: {search_calls}"
        )

    def test_missing_credentials_returns_error_report(self, mock_cred):
        # 이 테스트만 get_credential 이 빈 값 반환하도록 재설정
        mock_cred.side_effect = None
        mock_cred.return_value = ""

        report = cleanup_sent_mails(
            retention_days=7,
            dry_run=False,
            now=datetime(2026, 4, 17, tzinfo=timezone.utc),
            imap_factory=lambda: _make_fake_imap([], []),
        )
        assert report.errors
        assert "GMAIL_USER" in report.errors[0]


class TestCleanupReport:
    def test_summary_includes_key_fields(self):
        r = CleanupReport(
            retention_days=7,
            cutoff_date="10-Apr-2026",
            sent_mailbox="[Gmail]/Sent Mail",
            trash_mailbox="[Gmail]/Trash",
            candidate_count=42,
            deleted_count=42,
            trash_purged=True,
        )
        text = r.summary()
        assert "retention=7d" in text
        assert "10-Apr-2026" in text
        assert "42" in text
        assert "[Gmail]/Sent Mail" in text

    def test_summary_flags_dry_run(self):
        r = CleanupReport(
            retention_days=7,
            cutoff_date="10-Apr-2026",
            candidate_count=10,
            dry_run=True,
        )
        assert "DRY RUN" in r.summary()
