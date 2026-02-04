"""
Content Freshness Validation Tests
Unit tests for is_content_fresh() function
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lambda_itfind_downloader import is_content_fresh, parse_rss_pubdate


class TestContentFreshness:
    """Test content freshness validation logic"""

    def test_fresh_content_today(self):
        """Fresh content (today) should return True"""
        publish_date = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is True

    def test_fresh_content_three_days_old(self):
        """Fresh content (3 days old) should return True"""
        publish_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=3)).strftime("%Y-%m-%d")
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is True

    def test_fresh_content_exactly_seven_days(self):
        """Fresh content (exactly 7 days old) should return True"""
        publish_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=7)).strftime("%Y-%m-%d")
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is True

    def test_stale_content_eight_days_old(self):
        """Stale content (8 days old) should return False"""
        publish_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=8)).strftime("%Y-%m-%d")
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is False

    def test_stale_content_thirty_days_old(self):
        """Stale content (30 days old) should return False"""
        publish_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=30)).strftime("%Y-%m-%d")
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is False

    def test_invalid_date_format(self):
        """Invalid date format should return False"""
        publish_date = "invalid-date"
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is False

    def test_empty_date_string(self):
        """Empty date string should return False"""
        publish_date = ""
        staleness_days = 7

        result = is_content_fresh(publish_date, staleness_days)

        assert result is False

    def test_custom_staleness_threshold(self):
        """Custom staleness threshold should be respected"""
        publish_date = (datetime.now(timezone(timedelta(hours=9))) - timedelta(days=5)).strftime("%Y-%m-%d")
        staleness_days = 3

        result = is_content_fresh(publish_date, staleness_days)

        assert result is False


@pytest.mark.characterization
class TestRSSPubDateParsing:
    """Characterization tests for RSS pubDate parsing behavior"""

    def test_rss_pubdate_format_rfc822(self):
        """Parse RFC 822 format pubDate correctly"""
        pubdate_str = "Mon, 03 Feb 2026 00:00:00 KST"

        result = parse_rss_pubdate(pubdate_str)

        assert result == "2026-02-03"

    def test_rss_pubdate_format_with_gmt(self):
        """Parse RFC 822 format pubDate with GMT timezone"""
        pubdate_str = "Tue, 28 Jan 2026 00:00:00 GMT"

        result = parse_rss_pubdate(pubdate_str)

        assert result == "2026-01-28"

    def test_rss_pubdate_without_timezone(self):
        """Parse pubDate without timezone information"""
        pubdate_str = "Mon, 03 Feb 2026 00:00:00"

        result = parse_rss_pubdate(pubdate_str)

        assert result == "2026-02-03"

    def test_rss_pubdate_iso_format(self):
        """Parse ISO 8601 format date"""
        pubdate_str = "2026-02-03"

        result = parse_rss_pubdate(pubdate_str)

        assert result == "2026-02-03"

    def test_rss_pubdate_compact_format(self):
        """Parse compact date format"""
        pubdate_str = "20260203"

        result = parse_rss_pubdate(pubdate_str)

        assert result == "2026-02-03"

    def test_rss_pubdate_invalid_format(self):
        """Invalid pubDate format should return None"""
        pubdate_str = "invalid-date-format"

        result = parse_rss_pubdate(pubdate_str)

        assert result is None


@pytest.mark.integration
class TestFreshnessIntegration:
    """Integration tests for freshness check in download flow"""

    def test_fresh_content_proceeds_to_download(self):
        """Fresh content should proceed with PDF download"""
        # Test that fresh content (within staleness threshold) returns True
        result = is_content_fresh("2026-02-01", 7)

        assert result is True

    def test_stale_content_skips_download(self):
        """Stale content should skip PDF download and return None"""
        # Test that stale content (beyond staleness threshold) returns False
        result = is_content_fresh("2026-01-01", 7)

        assert result is False
