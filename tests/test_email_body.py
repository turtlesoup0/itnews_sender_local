"""
Email Body Generation Tests
Unit tests for email body HTML generation with TOC image and topics
"""
import pytest
from typing import List
from dataclasses import dataclass
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.email_sender import EmailSender


@dataclass
class WeeklyTrend:
    """Mock WeeklyTrend for testing"""
    title: str
    issue_number: str
    publish_date: str
    pdf_url: str
    topics: List[str]
    detail_id: str


class TestEmailBodyGeneration:
    """Test email body HTML generation"""

    def setup_method(self):
        """Setup test fixtures"""
        # Mock config
        self.mock_config = Mock()
        self.mock_config.GMAIL_USER = "test@example.com"
        self.mock_config.ADMIN_EMAIL = "admin@example.com"
        self.mock_config.UNSUBSCRIBE_FUNCTION_URL = "https://example.com/unsubscribe"

        # Create EmailSender with mocked config
        self.sender = EmailSender()
        self.sender.config = self.mock_config
        self.sender.unsubscribe_url_base = "https://example.com/unsubscribe"

        # Mock token generation
        self.sender._generate_unsubscribe_token = Mock(return_value="test_token_123")

    def test_body_with_toc_image(self):
        """Email body should include TOC image when has_toc_image=True"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI 트렌드", "클라우드 컴퓨팅", "보안 기술"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        assert '<img src="cid:toc_image"' in body
        assert 'alt="주간기술동향 목차"' in body
        assert 'border' in body.lower()  # Image has border styling

    def test_body_without_toc_image(self):
        """Email body should not include image tag when has_toc_image=False"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI 트렌드", "클라우드 컴퓨팅"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=False
        )

        assert '<img src="cid:' not in body
        assert 'toc_image' not in body

    def test_body_with_topics_list(self):
        """Email body should display topics as bulleted list"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI 트렌드", "클라우드 컴퓨팅", "보안 기술"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=False
        )

        # Check that all topics are present
        assert "AI 트렌드" in body
        assert "클라우드 컴퓨팅" in body
        assert "보안 기술" in body
        # Check bullet point format
        assert "• " in body or "<br>" in body

    def test_body_with_image_and_topics(self):
        """Email body should display image above topics when both present"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI 트렌드", "클라우드 컴퓨팅"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        img_pos = body.find('<img src="cid:toc_image"')
        topics_pos = body.find('이번 호 주요 토픽')

        # Image should appear before topics section
        assert img_pos < topics_pos
        assert '<img src="cid:toc_image"' in body
        assert '이번 호 주요 토픽' in body

    def test_image_styling(self):
        """TOC image should have border styling for better visibility"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        # Check for border styling in image tag
        assert 'border' in body.lower()
        assert 'max-width' in body.lower()

    def test_itfind_only_email_structure(self):
        """ITFIND-only email should have proper structure"""
        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI 트렌드", "클라우드 컴퓨팅"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        # Check required elements
        assert '주간기술동향 2203호' in body
        assert 'ITFIND' in body.upper() or 'itfind' in body
        assert '정보통신기획평가원' in body
        assert 'GitHub 프로젝트' in body
        assert 'unsubscribe' in body.lower()

    def test_email_without_itfind_info(self):
        """Email body without ITFIND info should use default template"""
        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=None,
            has_toc_image=False
        )

        # Check for regular email template elements
        assert 'IT뉴스 PDF 뉴스지면' in body
        assert 'GitHub 프로젝트' in body
        # Should NOT have ITFIND specific content
        assert '주간기술동향' not in body

    def test_unsubscribe_link_generation(self):
        """Unsubscribe link should be generated with token"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="user@example.com",
            itfind_info=itfind_info,
            has_toc_image=False
        )

        # Check that unsubscribe URL is present
        assert 'https://example.com/unsubscribe' in body
        assert 'token=' in body

    def test_empty_topics_list(self):
        """Email body should handle empty topics list gracefully"""
        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=[],  # Empty topics
            detail_id="1388"
        )

        body = self.sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=False
        )

        # Should still create valid HTML
        assert '<html>' in body
        assert '</html>' in body
        assert '주간기술동향 2203호' in body


@pytest.mark.characterization
class TestCurrentEmailBodyBehavior:
    """Characterization tests for current email body generation"""

    def test_current_itfind_body_structure(self):
        """Document current ITFIND email body structure"""
        sender = EmailSender()
        sender.config = Mock()
        sender.config.GMAIL_USER = "test@example.com"
        sender.config.ADMIN_EMAIL = "admin@example.com"
        sender.config.UNSUBSCRIBE_FUNCTION_URL = "https://example.com/unsubscribe"
        sender.unsubscribe_url_base = "https://example.com/unsubscribe"
        sender._generate_unsubscribe_token = Mock(return_value="test_token")

        itfind_info = WeeklyTrend(
            title="AI 트렌드",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI", "Cloud"],
            detail_id="1388"
        )

        body = sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        # Verify HTML structure (body may have leading/trailing whitespace)
        assert '<html>' in body
        assert '</html>' in body

    def test_current_no_image_support(self):
        """Document current behavior: has_toc_image controls image inclusion"""
        sender = EmailSender()
        sender.config = Mock()
        sender.config.GMAIL_USER = "test@example.com"
        sender.config.ADMIN_EMAIL = "admin@example.com"
        sender.config.UNSUBSCRIBE_FUNCTION_URL = "https://example.com/unsubscribe"
        sender.unsubscribe_url_base = "https://example.com/unsubscribe"
        sender._generate_unsubscribe_token = Mock(return_value="test_token")

        itfind_info = WeeklyTrend(
            title="Test",
            issue_number="2203",
            publish_date="2026-02-04",
            pdf_url="https://example.com/test.pdf",
            topics=["AI"],
            detail_id="1388"
        )

        body_with_image = sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=True
        )

        body_without_image = sender._create_email_body(
            recipient_email="test@example.com",
            itfind_info=itfind_info,
            has_toc_image=False
        )

        # Verify image tag presence based on has_toc_image
        assert '<img src="cid:toc_image"' in body_with_image
        assert '<img src="cid:toc_image"' not in body_without_image
