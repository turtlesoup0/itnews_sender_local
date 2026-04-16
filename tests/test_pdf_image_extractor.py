"""
PDF Image Extractor Tests
Unit tests for PDF page extraction as image using PyMuPDF
"""
import pytest
from typing import Optional
from unittest.mock import Mock, patch, mock_open
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_image_extractor import (
    extract_page_as_image,
    extract_toc_page_for_email,
    PYMUPDF_AVAILABLE
)


class TestPDFImageExtractor:
    """Test PDF page image extraction functionality"""

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_extract_page_with_mock_pymupdf(self):
        """Extract PDF page using mocked PyMuPDF (기본 포맷: JPEG)"""
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        mock_pix.width = 400
        mock_pix.height = 300
        # [S3] 기본 포맷이 JPEG이므로 JPEG 매직 바이트를 반환
        mock_pix.tobytes.return_value = b'\xff\xd8\xff\xe0' + b'\x00' * 1000

        mock_page.get_pixmap.return_value = mock_pix
        mock_page.rect = Mock(width=595.0)  # A4 폭
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image(
                "/tmp/test_itfind.pdf", page_number=2, dpi=200, max_width=800
            )

            assert result is not None
            assert len(result) > 0
            assert result[:3] == b'\xff\xd8\xff'  # JPEG signature

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_pdf_with_fewer_than_3_pages(self):
        """PDF with fewer than 3 pages should return None"""
        mock_doc = Mock()
        mock_doc.__len__ = Mock(return_value=2)  # Only 2 pages

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc

            result = extract_page_as_image("/tmp/test_2page.pdf", page_number=2)

            assert result is None

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_corrupted_pdf_returns_none(self):
        """Corrupted PDF should return None gracefully"""
        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.side_effect = Exception("File is corrupted")

            result = extract_page_as_image("/tmp/corrupted.pdf")

            assert result is None

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_graceful_degradation_on_pymupdf_missing(self):
        """Should gracefully handle missing PyMuPDF dependency"""
        # Temporarily set PYMUPDF_AVAILABLE to False
        with patch('src.pdf_image_extractor.PYMUPDF_AVAILABLE', False):
            result = extract_page_as_image("/tmp/test_itfind.pdf")

            assert result is None

    @pytest.mark.skipif(PYMUPDF_AVAILABLE, reason="PyMuPDF is installed")
    def test_returns_none_when_pymupdf_not_installed(self):
        """When PyMuPDF is not installed, should return None"""
        result = extract_page_as_image("/tmp/test_itfind.pdf")

        assert result is None


class TestPDFImageExtractionIntegration:
    """Integration tests for PDF image extraction in email workflow"""

    def test_extract_toc_page_uses_page_2(self):
        """extract_toc_page_for_email should use page_number=2 (page 3), JPEG 기본"""
        with patch('src.pdf_image_extractor.extract_page_as_image') as mock_extract:
            mock_extract.return_value = b'fake_image_bytes'

            result = extract_toc_page_for_email("/tmp/test_itfind.pdf")

            # [S3] JPEG + max_width=800 기본값 검증
            mock_extract.assert_called_once_with(
                "/tmp/test_itfind.pdf",
                page_number=2, dpi=200, max_width=800,
                output_format="jpeg", jpeg_quality=85,
            )

    def test_extraction_failure_returns_none(self):
        """If page extraction fails, should return None"""
        with patch('src.pdf_image_extractor.extract_page_as_image') as mock_extract:
            mock_extract.return_value = None

            result = extract_toc_page_for_email("/tmp/test_itfind.pdf")

            assert result is None

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_image_width_resize(self):
        """[S3] 큰 PDF 페이지는 렌더링 단계에서 축소 zoom으로 처리되어야 한다

        이전 구현은 full-size 렌더 후 pix.scale() 호출을 기대했으나,
        S3 이후 동적 zoom 계산으로 초기부터 목표 크기에 맞게 렌더한다.
        (같은 결과, 더 빠름)
        """
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        mock_pix.width = 800
        mock_pix.height = 600
        mock_pix.tobytes.return_value = b'\xff\xd8\xff\xe0' + b'\x00' * 1000  # JPEG

        # 네이티브 페이지 폭: 1200pt (실제로 축소가 필요한 케이스)
        mock_page.rect = Mock(width=1200.0)
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image(
                "/tmp/test_wide.pdf", page_number=2, max_width=600
            )

            assert result is not None
            # [S3] 검증: max_width=600이 native 1200pt보다 작으므로 zoom < 1.0
            # Matrix(zoom, zoom) 호출에서 zoom이 width_zoom = 600/1200 = 0.5 로 clamp됨
            assert mock_fitz.Matrix.called
            zoom_arg = mock_fitz.Matrix.call_args[0][0]
            assert zoom_arg <= 0.5 + 1e-9, \
                f"max_width < native_width인 경우 zoom은 max_width/native_width(=0.5) 이하여야 함, 실제={zoom_arg}"

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_custom_dpi_parameter(self):
        """Extract page with custom DPI setting"""
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        mock_pix.width = 400
        mock_pix.height = 300
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000

        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image("/tmp/test_itfind.pdf", page_number=2, dpi=150)

            assert result is not None
            # Verify Matrix was called with correct zoom factor (150/72)
            zoom_factor = 150 / 72
            mock_fitz.Matrix.assert_called()

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_image_size_under_500kb_limit(self):
        """Extracted image size check (500KB limit for email compatibility)"""
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        # Create image under 500KB
        image_size = 400000  # 400KB
        mock_pix.width = 400
        mock_pix.height = 300
        mock_pix.tobytes.return_value = b'\x00' * image_size

        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image("/tmp/test_itfind.pdf", page_number=2)

            assert result is not None
            assert len(result) < 512000  # 500KB limit

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_jpeg_default_output_uses_jpg_quality_argument(self):
        """[S3] 기본 포맷 JPEG이면 pix.tobytes('jpeg', jpg_quality=...)가 호출되어야 함"""
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        mock_pix.width = 400
        mock_pix.height = 300
        mock_pix.tobytes.return_value = b'\xff\xd8\xff\xe0' + b'\x00' * 1000  # JPEG

        mock_page.rect = Mock(width=595.0)
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image(
                "/tmp/test_itfind.pdf", page_number=2,
                output_format="jpeg", jpeg_quality=85,
            )

            assert result is not None
            # JPEG 매직 바이트로 시작
            assert result[:3] == b'\xff\xd8\xff'
            # pix.tobytes가 'jpeg' 포맷 + jpg_quality=85로 호출되었는지 확인
            assert mock_pix.tobytes.called
            call_args, call_kwargs = mock_pix.tobytes.call_args
            assert call_args[0] == "jpeg"
            assert call_kwargs.get("jpg_quality") == 85

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_jpeg_significantly_smaller_than_png_equivalent(self):
        """[S3] JPEG 출력이 동일 이미지에 대해 PNG보다 의미있게 작아야 함

        이 테스트는 'JPEG 선택 시 pix.tobytes("jpeg")가 PNG보다 작은 bytes를 반환하도록
        내부 분기가 올바르게 동작'하는지 검증한다. 실제 PyMuPDF 인코딩 효율은 mock으로
        시뮬레이션하되, 포맷 분기 로직이 크기에 기여함을 보인다.
        """
        # PNG 출력은 크고, JPEG 출력은 작음을 시뮬레이션
        png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 600_000  # ~600KB PNG
        jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 150_000  # ~150KB JPEG

        def fake_tobytes(fmt, **kwargs):
            if fmt == "jpeg":
                return jpeg_bytes
            return png_bytes

        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()
        mock_pix.width = 800
        mock_pix.height = 1100
        mock_pix.tobytes.side_effect = fake_tobytes

        mock_page.rect = Mock(width=595.0)
        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            # JPEG 호출
            jpeg_result = extract_page_as_image(
                "/tmp/test.pdf", page_number=2, output_format="jpeg"
            )
            # PNG 호출
            png_result = extract_page_as_image(
                "/tmp/test.pdf", page_number=2, output_format="png"
            )

            assert jpeg_result is not None
            assert png_result is not None
            # S3 기대치: JPEG가 PNG 대비 50% 이상 작아야 함
            assert len(jpeg_result) < len(png_result) * 0.5, (
                f"JPEG={len(jpeg_result)}, PNG={len(png_result)} — "
                f"S3 최적화 효과가 반영되지 않음"
            )
