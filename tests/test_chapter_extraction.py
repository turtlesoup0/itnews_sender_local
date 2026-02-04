"""
Chapter-based Topic Extraction Tests
Unit tests for extract_topics_from_chapters() function
"""
import pytest
from unittest.mock import patch, MagicMock, Mock
import sys
import os
import builtins

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lambda_itfind_downloader import extract_topics_from_chapters, _map_topics_to_categories


def mock_fitz_open():
    """Create a mock fitz module with open() method"""
    mock_fitz_module = MagicMock()
    mock_doc = MagicMock()
    mock_fitz_module.open.return_value = mock_doc
    return mock_fitz_module


def create_mock_pdf_page(text_content: str) -> MagicMock:
    """Create a mock PDF page with given text content"""
    mock_page = MagicMock()
    mock_page.get_text.return_value = text_content
    return mock_page


class TestTopicCategorization:
    """Test topic categorization logic"""

    def test_single_topic(self):
        """Single topic should be categorized as 기획시리즈"""
        topics = ["6G 이동통신을 위한 과금정책 및 경제모델 연구 동향"]
        result = _map_topics_to_categories(topics)

        assert "기획시리즈" in result
        assert "ICT 신기술" in result
        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 0
        assert result["기획시리즈"][0] == topics[0]

    def test_two_topics(self):
        """Two topics: first should be 기획시리즈, second should be ICT 신기술"""
        topics = [
            "6G 이동통신을 위한 과금정책 및 경제모델 연구 동향",
            "공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석"
        ]
        result = _map_topics_to_categories(topics)

        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert result["기획시리즈"][0] == topics[0]
        assert result["ICT 신기술"][0] == topics[1]

    def test_three_topics(self):
        """Three topics (2203호 special case): first two should be 기획시리즈, third should be ICT 신기술"""
        topics = [
            "AI-Ready 산업 생태계 조성을 위한 구조적 설계",
            "AI 시대의 종합 리스크 관리",
            "우주국방반도체 주요국 정책 동향 분석 및 국내 시사점"
        ]
        result = _map_topics_to_categories(topics)

        assert len(result["기획시리즈"]) == 2
        assert len(result["ICT 신기술"]) == 1
        assert result["기획시리즈"][0] == topics[0]
        assert result["기획시리즈"][1] == topics[1]
        assert result["ICT 신기술"][0] == topics[2]

    def test_four_topics(self):
        """Four topics: half (rounded up) should be 기획시리즈, rest should be ICT 신기술"""
        topics = [
            "주제1: 첫 번째 주제",
            "주제2: 두 번째 주제",
            "주제3: 세 번째 주제",
            "주제4: 네 번째 주제"
        ]
        result = _map_topics_to_categories(topics)

        assert len(result["기획시리즈"]) == 2  # (4 + 1) // 2 = 2
        assert len(result["ICT 신기술"]) == 2
        assert result["기획시리즈"][0] == topics[0]
        assert result["기획시리즈"][1] == topics[1]
        assert result["ICT 신기술"][0] == topics[2]
        assert result["ICT 신기술"][1] == topics[3]

    def test_five_topics(self):
        """Five topics: half (rounded up) should be 기획시리즈, rest should be ICT 신기술"""
        topics = [
            "주제1: 첫 번째 주제",
            "주제2: 두 번째 주제",
            "주제3: 세 번째 주제",
            "주제4: 네 번째 주제",
            "주제5: 다섯 번째 주제"
        ]
        result = _map_topics_to_categories(topics)

        assert len(result["기획시리즈"]) == 3  # (5 + 1) // 2 = 3
        assert len(result["ICT 신기술"]) == 2

    def test_empty_topics(self):
        """Empty topics should return empty categories"""
        topics = []
        result = _map_topics_to_categories(topics)

        assert len(result["기획시리즈"]) == 0
        assert len(result["ICT 신기술"]) == 0

    def test_duplicate_topics_removal(self):
        """Duplicate topics should be removed (happens in extract_topics_from_chapters, not _map_topics_to_categories)"""
        # This test verifies that _map_topics_to_categories correctly maps whatever topics it receives
        # Duplicate removal is handled by extract_topics_from_chapters before calling this function
        topics = [
            "중복 주제",
            "다른 주제",
            "중복 주제"  # 중복 (but this function doesn't remove duplicates)
        ]
        result = _map_topics_to_categories(topics)

        # _map_topics_to_categories maps all topics it receives (including duplicates)
        # Duplicate removal is done by extract_topics_from_chapters
        total_topics = len(result["기획시리즈"]) + len(result["ICT 신기술"])
        assert total_topics == 3  # All 3 topics are mapped


class TestChapterPatternDetection:
    """Test Chapter pattern detection and topic extraction"""

    def test_chapter_pattern_extraction_success(self):
        """Test successful Chapter pattern extraction"""
        # Mock PDF content with Chapter patterns
        full_text = """
Chapter 01
6G 이동통신을 위한 과금정책 및 경제모델 연구 동향

본문 내용...

Chapter 02
공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석

본문 내용...
"""

        # Create mock document
        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        # Patch fitz.open to return our mock document
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        # Patch builtins.__import__ to return our mock fitz module
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        assert "기획시리즈" in result
        assert "ICT 신기술" in result
        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert "6G 이동통신" in result["기획시리즈"][0]
        assert "공간 확장" in result["ICT 신기술"][0]

    def test_chapter_pattern_with_blank_lines(self):
        """Test Chapter pattern extraction with blank lines between Chapter and topic"""
        full_text = """
Chapter 01


6G 이동통신을 위한 과금정책 및 경제모델 연구 동향

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        assert len(result["기획시리즈"]) == 1
        assert "6G 이동통신" in result["기획시리즈"][0]

    def test_chapter_pattern_no_topics_found(self):
        """Test when Chapter pattern exists but no valid topics found"""
        full_text = """
Chapter 01
개요

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        # Should return empty result since topic is too short (< 10 chars)
        assert len(result.get("기획시리즈", [])) == 0
        assert len(result.get("ICT 신기술", [])) == 0

    def test_chapter_pattern_filtered_out_sub_items(self):
        """Test that sub-items are filtered out (numbers only, short text)"""
        full_text = """
Chapter 01
6G 이동통신을 위한 과금정책 및 경제모델 연구 동향

01  # Should be filtered (number only)
I. 서론  # Should be filtered (too short)

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        # Only the main topic should be extracted
        assert len(result["기획시리즈"]) == 1
        assert "6G 이동통신" in result["기획시리즈"][0]

    def test_chapter_pattern_not_found(self):
        """Test when Chapter pattern is not found"""
        full_text = """
This PDF has no Chapter patterns
Just regular content
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        # Should return empty dict (no Chapter pattern found)
        assert result == {}


class TestErrorHandling:
    """Test error handling"""

    def test_file_not_found(self):
        """Test FileNotFoundError when PDF file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            result = extract_topics_from_chapters("/nonexistent/path/test.pdf")

        # Should return empty dict
        assert result == {}

    def test_encrypted_pdf(self):
        """Test encrypted PDF handling"""
        mock_doc = MagicMock()
        mock_doc.is_encrypted = True

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/encrypted.pdf")

        # Should return empty dict
        assert result == {}

    def test_fitz_import_error(self):
        """Test when PyMuPDF (fitz) is not available"""
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                raise ImportError("No module named 'fitz'")
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/test.pdf")

        # Should return empty dict
        assert result == {}


class TestAcceptanceCriteria:
    """Test acceptance criteria from SPEC-ITFIND-002"""

    def test_acceptance_2154호(self):
        """Acceptance test for issue 2154"""
        full_text = """
Chapter 01
6G 이동통신을 위한 과금정책 및 경제모델 연구 동향

본문 내용...

Chapter 02
공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/2154.pdf")

        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert "6G 이동통신을 위한 과금정책 및 경제모델 연구 동향" == result["기획시리즈"][0]
        assert "공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석" == result["ICT 신기술"][0]

    def test_acceptance_2203호_three_topics(self):
        """Acceptance test for issue 2203 (3 topics - special case)"""
        full_text = """
Chapter 01
AI-Ready 산업 생태계 조성을 위한 구조적 설계

본문 내용...

Chapter 02
AI 시대의 종합 리스크 관리

본문 내용...

Chapter 03
우주국방반도체 주요국 정책 동향 분석 및 국내 시사점

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/2203.pdf")

        # 2203호 특례: 첫 두 개는 기획시리즈, 세 번째는 ICT 신기술
        assert len(result["기획시리즈"]) == 2
        assert len(result["ICT 신기술"]) == 1
        assert "AI-Ready 산업 생태계 조성을 위한 구조적 설계" == result["기획시리즈"][0]
        assert "AI 시대의 종합 리스크 관리" == result["기획시리즈"][1]
        assert "우주국방반도체 주요국 정책 동향 분석 및 국내 시사점" == result["ICT 신기술"][0]

    def test_acceptance_2198호(self):
        """Acceptance test for issue 2198"""
        full_text = """
Chapter 01
AI를 위한 자동화된 데이터 관리 체계의 필요성

본문 내용...

Chapter 02
AI 기술 융합을 통한 전력산업 업무 자동화 전략과 실현 방안

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/2198.pdf")

        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert "AI를 위한 자동화된 데이터 관리 체계의 필요성" == result["기획시리즈"][0]
        assert "AI 기술 융합을 통한 전력산업 업무 자동화 전략과 실현 방안" == result["ICT 신기술"][0]

    def test_acceptance_2199호(self):
        """Acceptance test for issue 2199"""
        full_text = """
Chapter 01
건설 분야 AI 학습 데이터셋 구축 사례 및 동향

본문 내용...

Chapter 02
트랜스포머 최적화 기술 연구 동향

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/2199.pdf")

        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert "건설 분야 AI 학습 데이터셋 구축 사례 및 동향" == result["기획시리즈"][0]
        assert "트랜스포머 최적화 기술 연구 동향" == result["ICT 신기술"][0]

    def test_acceptance_2200호(self):
        """Acceptance test for issue 2200"""
        full_text = """
Chapter 01
AI 학습 데이터 신뢰성 확보를 위한 시험평가 기반 접근 방식 동향

본문 내용...

Chapter 02
도시문제 해결을 위한 디지털트윈 활용 방향

본문 내용...
"""

        mock_doc = MagicMock()
        mock_page = create_mock_pdf_page(full_text)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.is_encrypted = False
        mock_doc.__len__ = MagicMock(return_value=1)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'fitz':
                return mock_fitz
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            with patch('os.path.exists', return_value=True):
                result = extract_topics_from_chapters("/fake/path/2200.pdf")

        assert len(result["기획시리즈"]) == 1
        assert len(result["ICT 신기술"]) == 1
        assert "AI 학습 데이터 신뢰성 확보를 위한 시험평가 기반 접근 방식 동향" == result["기획시리즈"][0]
        assert "도시문제 해결을 위한 디지털트윈 활용 방향" == result["ICT 신기술"][0]
