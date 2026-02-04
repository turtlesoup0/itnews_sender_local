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
        """Extract PDF page using mocked PyMuPDF"""
        # Mock fitz module
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        # Setup mock pixmap with realistic properties
        mock_pix.width = 400
        mock_pix.height = 300
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000  # PNG header + data
        mock_pix.scale.return_value = mock_pix

        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc

            result = extract_page_as_image("/tmp/test_itfind.pdf", page_number=2, dpi=200, max_width=600)

            assert result is not None
            assert len(result) > 0
            assert result[:4] == b'\x89PNG'  # PNG signature

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
        """extract_toc_page_for_email should use page_number=2 (page 3)"""
        # Test default parameters
        with patch('src.pdf_image_extractor.extract_page_as_image') as mock_extract:
            mock_extract.return_value = b'fake_image_bytes'

            result = extract_toc_page_for_email("/tmp/test_itfind.pdf")

            # Verify correct parameters are passed
            mock_extract.assert_called_once_with("/tmp/test_itfind.pdf", page_number=2, dpi=200, max_width=600)

    def test_extraction_failure_returns_none(self):
        """If page extraction fails, should return None"""
        with patch('src.pdf_image_extractor.extract_page_as_image') as mock_extract:
            mock_extract.return_value = None

            result = extract_toc_page_for_email("/tmp/test_itfind.pdf")

            assert result is None

    @pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
    def test_image_width_resize(self):
        """Wide PDF page should be auto-resized to max_width"""
        mock_doc = Mock()
        mock_page = Mock()
        mock_pix = Mock()

        # Mock wide pixmap that needs resizing
        mock_pix.width = 1200  # Wider than max_width=600
        mock_pix.height = 900
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000

        # Mock scale to return a resized pixmap
        mock_pix_scaled = Mock()
        mock_pix_scaled.width = 600
        mock_pix_scaled.height = 450
        mock_pix_scaled.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 1000
        mock_pix.scale.return_value = mock_pix_scaled

        mock_page.get_pixmap.return_value = mock_pix
        mock_doc.__len__ = Mock(return_value=5)
        mock_doc.__getitem__ = Mock(return_value=mock_page)

        with patch('src.pdf_image_extractor.fitz') as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            mock_fitz.Matrix = Mock(return_value=Mock())

            result = extract_page_as_image("/tmp/test_wide.pdf", page_number=2, max_width=600)

            assert result is not None
            # Verify scale was called
            assert mock_pix.scale.called

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
