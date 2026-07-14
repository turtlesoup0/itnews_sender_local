"""
ITFIND 주간기술동향 다운로드 관련 회귀 테스트

1) extract_streamdocs_id_from_detail_page: ITFIND 사이트가 JS location.href 방식에서
   서버 302 리다이렉트 체인으로 변경(2026-07)되면서 2216호 다운로드가 실패한 버그의
   재현/회귀 테스트.
2) is_itfind_day: 발행 당일(수) 자료 미게시로 인한 누락을 막기 위해 다운로드 요일을
   목요일로 이동한 게이트 검증.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lambda_itfind_downloader import extract_streamdocs_id_from_detail_page
from lambda_handler import is_itfind_day

KST = timezone(timedelta(hours=9))
STREAMDOCS_ID = "i6EzIHpSL9GZnRtwwZd_bUmU2OmF0pvLjbWooI-lcVE"


def _fake_response(url: str, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.url = url
    resp.text = text
    resp.status_code = 200
    return resp


class TestStreamDocsExtraction:
    """StreamDocs ID 추출 로직 회귀 테스트"""

    def test_extract_from_server_302_redirect_chain(self):
        """
        서버 302 체인(현재 ITFIND 동작): requests가 최종 뷰어 URL까지 따라가므로
        response.url의 streamdocsId를 추출해야 한다. (2216호 누락 재현/회귀)

        수정 전 코드는 response.text의 JS location.href만 찾아 None을 반환했다.
        """
        final_url = f"https://www.itfind.or.kr/streamdocs/view/sd;streamdocsId={STREAMDOCS_ID}"
        # 본문에는 JS 리다이렉트가 전혀 없음 (서버 302로 대체됨)
        fake = _fake_response(final_url, text="<html><body>viewer</body></html>")

        with patch("lambda_itfind_downloader.requests.Session.get", return_value=fake):
            result = extract_streamdocs_id_from_detail_page("1401")

        assert result == STREAMDOCS_ID

    def test_extract_returns_none_when_id_absent(self):
        """어디에도 streamdocsId가 없으면 None을 반환한다."""
        fake = _fake_response("https://www.itfind.or.kr/publication/notfound", text="<html></html>")

        with patch("lambda_itfind_downloader.requests.Session.get", return_value=fake):
            result = extract_streamdocs_id_from_detail_page("9999")

        assert result is None


class TestItfindDayGate:
    """ITFIND 다운로드 요일 게이트(목요일) 검증"""

    def _patch_now(self, dt: datetime):
        # is_itfind_day 내부의 datetime.now(kst) 호출을 고정 날짜로 대체
        mock_datetime = MagicMock()
        mock_datetime.now.return_value = dt
        return patch("lambda_handler.datetime", mock_datetime)

    def test_thursday_is_itfind_day(self):
        """목요일(2026-07-16)이면 True"""
        with self._patch_now(datetime(2026, 7, 16, 7, 0, tzinfo=KST)):
            assert is_itfind_day() is True

    def test_wednesday_is_not_itfind_day(self):
        """발행일인 수요일(2026-07-15)은 이제 False (다운로드는 다음 날)"""
        with self._patch_now(datetime(2026, 7, 15, 7, 0, tzinfo=KST)):
            assert is_itfind_day() is False

    def test_other_weekday_is_not_itfind_day(self):
        """월요일(2026-07-13)이면 False"""
        with self._patch_now(datetime(2026, 7, 13, 7, 0, tzinfo=KST)):
            assert is_itfind_day() is False
