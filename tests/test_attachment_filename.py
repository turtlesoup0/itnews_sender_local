"""
Korean Attachment Filename Tests
Unit tests for Korean filename generation with RFC 2231 encoding
"""
import pytest
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from dataclasses import dataclass
from typing import List

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.email_sender import generate_korean_filename


@dataclass
class WeeklyTrend:
    """Mock WeeklyTrend for testing"""
    title: str
    issue_number: str
    publish_date: str
    pdf_url: str
    topics: List[str]
    detail_id: str


class TestKoreanFilenameGeneration:
    """Test Korean filename generation for ITFIND PDF attachments"""

    def test_standard_filename_format(self):
        """Standard filename should be 주기동YYMMDD-xxxx호.pdf"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI", "Cloud"],
            detail_id="1388"
        )

        korean_filename, ascii_filename = generate_korean_filename(itfind_info)

        assert korean_filename == "주기동260204-2203호.pdf"
        assert ascii_filename == "itfind_260204-2203.pdf"

    def test_issue_number_with_ho_suffix(self):
        """Issue number already containing '호' should be handled correctly"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203호",  # Already has '호'
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        korean_filename, ascii_filename = generate_korean_filename(itfind_info)

        # Should strip existing '호', then add '호' suffix
        assert korean_filename == "주기동260204-2203호.pdf"
        assert "호" not in ascii_filename

    def test_ascii_fallback_filename(self):
        """ASCII fallback filename should be provided for older email clients"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        korean_filename, ascii_filename = generate_korean_filename(itfind_info)

        assert ascii_filename == "itfind_260204-2203.pdf"
        # ASCII filename should not contain Korean characters
        assert all(ord(c) < 128 or c in '._-' for c in ascii_filename)

    def test_no_itfind_info_fallback(self):
        """When itfind_info is None, should use default filename format"""
        result = generate_korean_filename(None)

        korean_filename, ascii_filename = result

        today = datetime.now().strftime("%Y%m%d")
        assert korean_filename == f"itfind_{today}.pdf"
        assert ascii_filename == f"itfind_{today}.pdf"

    def test_different_date_formats(self):
        """Should handle various date formats correctly"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2025-12-31",  # Year rollover
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        korean_filename, ascii_filename = generate_korean_filename(itfind_info)

        assert "251231" in korean_filename
        assert "251231" in ascii_filename

    def test_invalid_publish_date_fallback(self):
        """Should fallback to today's date when publish_date is invalid"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="invalid-date",  # Invalid date format
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        korean_filename, ascii_filename = generate_korean_filename(itfind_info)

        # Should use today's date when parsing fails
        today = datetime.now().strftime("%y%m%d")
        assert f"주기동{today}" in korean_filename
        assert f"itfind_{today}" in ascii_filename


@pytest.mark.characterization
class TestCurrentFilenameBehavior:
    """Characterization tests for current filename generation behavior"""

    def test_filename_returns_tuple(self):
        """generate_korean_filename returns (korean_filename, ascii_filename)"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        result = generate_korean_filename(itfind_info)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(name, str) for name in result)

    def test_korean_filename_contains_hangul(self):
        """Korean filename should contain Hangul characters"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        korean_filename, _ = generate_korean_filename(itfind_info)

        # Check for Korean characters (주기동)
        has_hangul = any('가' <= c <= '힣' for c in korean_filename)
        assert has_hangul
