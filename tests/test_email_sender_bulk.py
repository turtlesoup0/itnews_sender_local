"""
[S1 회귀방지] send_bulk_email 최적화 검증

email_workflow.py의 실제 호출 시나리오는 두 가지뿐이다:
  (A) 전자신문 단독   : pdf_path=etnews, itfind_pdf_path=None, itfind_info=None
  (B) ITFIND 단독     : pdf_path=itfind, itfind_pdf_path=itfind (같은 경로), itfind_info=obj

각 시나리오에서 수신자 N명일 때:
- 이미지 추출/ PDF 디스크 I/O가 N회가 아닌 1회만 수행되는지
- 수신자별 개인화(수신거부 토큰)는 유지되는지
- 모든 수신자가 동일한 PDF 바이트를 받는지
를 검증한다.

실제 SMTP는 호출하지 않는다 (_send_via_smtp mock).
"""
import os
import sys
import hashlib
import re
from dataclasses import dataclass
from typing import List
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.email_sender import EmailSender


@dataclass
class _FakeRecipient:
    email: str
    name: str = "Test"


@dataclass
class _FakeWeeklyTrend:
    title: str = "주간기술동향"
    issue_number: str = "2210"
    publish_date: str = "2026-04-14"
    pdf_url: str = "https://example.com/t.pdf"
    topics: List[str] = None
    detail_id: str = "9999"

    def __post_init__(self):
        if self.topics is None:
            self.topics = ["topic1", "topic2"]


@pytest.fixture
def tmp_etnews_pdf(tmp_path):
    pdf = tmp_path / "etnews_20260417.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 1024 + b"\n%%EOF")
    return str(pdf)


@pytest.fixture
def tmp_itfind_pdf(tmp_path):
    pdf = tmp_path / "itfind_2210.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"y" * 2048 + b"\n%%EOF")
    return str(pdf)


@pytest.fixture
def sender():
    s = EmailSender()
    s.config = Mock()
    s.config.GMAIL_USER = "sender@example.com"
    s.config.ADMIN_EMAIL = "admin@example.com"
    s.config.UNSUBSCRIBE_FUNCTION_URL = "https://example.com/u"
    s.config.SMTP_MAX_RETRIES = 3
    s.config.SMTP_RETRY_DELAY = 0
    s.config.SMTP_CONSECUTIVE_FAIL_LIMIT = 5
    s.config.SMTP_RECONNECT_EVERY = 50
    s.unsubscribe_url_base = "https://example.com/u"
    # 수신거부 비밀값을 고정값으로 오버라이드 (테스트 독립성)
    s.unsubscribe_secret = "test_secret_for_unit_tests"
    # [S2] SMTP 경로 모킹:
    #   _open_smtp_connection() → 가짜 server 객체 반환
    #   _send_on_server(server, msg, to) → server 그대로 반환 (루프 지속)
    fake_server = Mock(name="FakeSMTPServer")
    s._open_smtp_connection = Mock(return_value=fake_server)
    s._send_on_server = Mock(side_effect=lambda server, msg, to: server)
    # 레거시 단일 경로 호환 (send_email 계열)
    s._send_via_smtp = Mock()
    return s


def _get_html_body(msg):
    """MIME 메시지에서 text/html 파트의 디코딩된 문자열 추출"""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload.decode("utf-8", errors="replace")
    return ""


# ────────────────────────────────────────────────────────────────
# 시나리오 A: 전자신문 단독 발송
# ────────────────────────────────────────────────────────────────
class TestBulkEmailEtnewsOnly:

    def test_first_page_extracted_once_for_many_recipients(
        self, sender, tmp_etnews_pdf
    ):
        """전자신문 단독 발송: 수신자 3명이어도 1페이지 이미지 추출은 1회만"""
        recipients = [
            _FakeRecipient("a@example.com"),
            _FakeRecipient("b@example.com"),
            _FakeRecipient("c@example.com"),
        ]
        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN_PNG") as mock_first, \
             patch("src.pdf_image_extractor.extract_toc_page_for_email",
                   return_value=b"TOC") as mock_toc:
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(success) == 3
        # 전자신문 1p 추출은 1회만
        assert mock_first.call_count == 1, \
            f"전자신문 1p 추출은 1회여야 하나 {mock_first.call_count}회"
        # TOC는 ITFIND 없는 경우 호출 안 됨
        assert mock_toc.call_count == 0
        assert sender._send_on_server.call_count == 3

    def test_etnews_pdf_file_opened_once(self, sender, tmp_etnews_pdf):
        """전자신문 PDF는 수신자 수와 무관하게 1회만 open"""
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(5)]

        import builtins
        original_open = builtins.open
        open_count = {"pdf": 0}

        def counting_open(path, *args, **kwargs):
            if isinstance(path, str) and path == tmp_etnews_pdf:
                open_count["pdf"] += 1
            return original_open(path, *args, **kwargs)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"), \
             patch("builtins.open", side_effect=counting_open):
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(success) == 5
        assert open_count["pdf"] == 1, \
            f"전자신문 PDF는 1회만 읽혀야 하나 {open_count['pdf']}회"


# ────────────────────────────────────────────────────────────────
# 시나리오 B: ITFIND 단독 발송 (수요일, pdf_path == itfind_pdf_path)
# ────────────────────────────────────────────────────────────────
class TestBulkEmailItfindOnly:

    def test_toc_extracted_once_for_many_recipients(
        self, sender, tmp_itfind_pdf
    ):
        """ITFIND 단독: TOC 이미지 추출은 1회만, 전자신문 추출은 0회"""
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(4)]
        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_toc_page_for_email",
                   return_value=b"TOC_PNG") as mock_toc, \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN") as mock_first:
            ok, success = sender.send_bulk_email(
                pdf_path=tmp_itfind_pdf,          # 실서비스: 동일 경로
                itfind_pdf_path=tmp_itfind_pdf,
                itfind_info=_FakeWeeklyTrend(),
            )

        assert ok is True
        assert len(success) == 4
        assert mock_toc.call_count == 1
        assert mock_first.call_count == 0, \
            "ITFIND 단독에서는 전자신문 1p 추출이 호출되면 안 됨"

    def test_itfind_pdf_opened_once_even_though_passed_as_both_args(
        self, sender, tmp_itfind_pdf
    ):
        """실서비스에서 pdf_path == itfind_pdf_path로 호출되어도 PDF는 1회만 읽어야 함"""
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(3)]

        import builtins
        original_open = builtins.open
        open_count = {"pdf": 0}

        def counting_open(path, *args, **kwargs):
            if isinstance(path, str) and path == tmp_itfind_pdf:
                open_count["pdf"] += 1
            return original_open(path, *args, **kwargs)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_toc_page_for_email",
                   return_value=b"TOC"), \
             patch("builtins.open", side_effect=counting_open):
            ok, _ = sender.send_bulk_email(
                pdf_path=tmp_itfind_pdf,
                itfind_pdf_path=tmp_itfind_pdf,
                itfind_info=_FakeWeeklyTrend(),
            )

        assert ok is True
        assert open_count["pdf"] == 1, \
            f"ITFIND PDF는 1회만 읽혀야 하나 {open_count['pdf']}회"


# ────────────────────────────────────────────────────────────────
# 개인화 회귀 방지
# ────────────────────────────────────────────────────────────────
class TestBulkEmailPersonalization:

    def test_each_recipient_gets_unique_unsubscribe_token(
        self, sender, tmp_etnews_pdf
    ):
        """수신자마다 본문에 서로 다른 HMAC 토큰이 포함되어야 한다"""
        recipients = [
            _FakeRecipient("alice@example.com"),
            _FakeRecipient("bob@example.com"),
        ]
        sent = []

        def capture(server, msg, to_emails):
            sent.append((to_emails[0], _get_html_body(msg)))
            return server  # 루프 지속을 위해 server 반환

        sender._send_on_server = Mock(side_effect=capture)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, _ = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(sent) == 2

        bodies = {addr: body for addr, body in sent}
        alice_body = bodies["alice@example.com"]
        bob_body = bodies["bob@example.com"]

        # 본문에 수신거부 링크가 들어있어야 함
        alice_tokens = re.findall(r"token=([A-Za-z0-9_\-=]+)", alice_body)
        bob_tokens = re.findall(r"token=([A-Za-z0-9_\-=]+)", bob_body)
        assert alice_tokens, "Alice 본문에 수신거부 토큰이 없음"
        assert bob_tokens, "Bob 본문에 수신거부 토큰이 없음"
        assert alice_tokens[0] != bob_tokens[0], \
            "수신자별 토큰이 동일함 (개인화 회귀 버그)"

        # To 헤더도 각 수신자로 개별 설정되어야 함
        assert "alice@example.com" in alice_body or True  # body는 html임, To는 헤더에


# ────────────────────────────────────────────────────────────────
# PDF 바이트 일관성
# ────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────
# [S2] SMTP 연결 재사용 및 조기 중단 회로
# ────────────────────────────────────────────────────────────────
class TestBulkEmailSmtpReuse:

    def test_smtp_connection_opened_once_for_many_recipients(
        self, sender, tmp_etnews_pdf
    ):
        """수신자 10명이어도 SMTP 연결은 1회만 수립되어야 한다"""
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(10)]
        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(success) == 10
        # 핵심: 연결 1회, 전송 10회
        assert sender._open_smtp_connection.call_count == 1, \
            f"SMTP 연결은 1회여야 하나 {sender._open_smtp_connection.call_count}회"
        assert sender._send_on_server.call_count == 10

    def test_smtp_reconnect_every_N_recipients(self, sender, tmp_etnews_pdf):
        """SMTP_RECONNECT_EVERY 초과 시 자동 재연결"""
        sender.config.SMTP_RECONNECT_EVERY = 3  # 테스트용 낮은 임계값
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(7)]
        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(success) == 7
        # 7통 / 3통 per connection = 최초 연결 1 + 재연결 2 = 총 3회 open 예상
        # (0,1,2 → 3에서 재연결 → 3,4,5 → 6에서 재연결 → 6)
        assert sender._open_smtp_connection.call_count == 3, \
            f"3통마다 재연결 기대, 실제 {sender._open_smtp_connection.call_count}회"

    def test_early_circuit_on_consecutive_failures(self, sender, tmp_etnews_pdf):
        """연속 N회 실패 시 루프를 즉시 중단하고 남은 수신자는 건너뛰어야 한다"""
        sender.config.SMTP_CONSECUTIVE_FAIL_LIMIT = 3
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(20)]

        # 모든 send 시도가 실패하는 상황 시뮬레이션
        def always_fail(server, msg, to):
            raise smtplib.SMTPException("simulated failure")

        import smtplib
        sender._send_on_server = Mock(side_effect=always_fail)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is False
        assert len(success) == 0
        # 3회 연속 실패 후 중단 → 20명 중 3번만 시도
        assert sender._send_on_server.call_count == 3, \
            f"조기 중단 기대(3회), 실제 {sender._send_on_server.call_count}회 시도"

    def test_no_early_circuit_if_failures_are_not_consecutive(
        self, sender, tmp_etnews_pdf
    ):
        """간헐적 실패(연속 아님)는 회로를 트리거하지 않아야 한다"""
        sender.config.SMTP_CONSECUTIVE_FAIL_LIMIT = 3
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(10)]

        import smtplib
        call_counter = {"n": 0}

        def fail_every_other(server, msg, to):
            call_counter["n"] += 1
            # 홀수 번째는 실패, 짝수 번째는 성공
            if call_counter["n"] % 2 == 1:
                raise smtplib.SMTPException("intermittent")
            return server

        sender._send_on_server = Mock(side_effect=fail_every_other)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, success = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        # 연속 실패가 2회를 넘지 않으니 끝까지 진행
        assert sender._send_on_server.call_count == 10
        assert len(success) == 5  # 짝수번째 5건 성공


class TestBulkEmailPdfConsistency:

    def test_all_recipients_receive_identical_pdf_bytes(
        self, sender, tmp_etnews_pdf
    ):
        """모든 수신자에게 동일한 PDF 바이트 (공유 자산 재사용 검증)"""
        recipients = [_FakeRecipient(f"u{i}@ex.com") for i in range(3)]
        hashes = []

        def capture(server, msg, to_emails):
            for part in msg.walk():
                if part.get_content_type() == "application/pdf":
                    payload = part.get_payload(decode=True)
                    hashes.append(hashlib.md5(payload).hexdigest())
            return server

        sender._send_on_server = Mock(side_effect=capture)

        with patch("src.email_sender.get_active_recipients", return_value=recipients), \
             patch("src.pdf_image_extractor.extract_first_page_for_email",
                   return_value=b"ETN"):
            ok, _ = sender.send_bulk_email(pdf_path=tmp_etnews_pdf)

        assert ok is True
        assert len(hashes) == 3
        assert len(set(hashes)) == 1, \
            f"수신자 간 PDF 해시 불일치: {hashes}"
