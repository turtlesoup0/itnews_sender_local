"""
PDF Image Extractor Module
Extract PDF pages as images using PyMuPDF for email embedding
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# PyMuPDF (fitz) import with graceful degradation
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) not available. PDF image extraction disabled.")


def extract_page_as_image(
    pdf_path: str,
    page_number: int = 2,  # 0-based, so 2 = page 3
    dpi: int = 200,
    max_width: int = 600
) -> Optional[bytes]:
    """
    PDF 페이지를 이미지로 추출 (이메일 임베딩용)

    Args:
        pdf_path: PDF 파일 경로
        page_number: 추출할 페이지 번호 (0-based, 기본값 2 = page 3)
        dpi: 이미지 해상도 (기본값 200)
        max_width: 최대 너비 (픽셀, 기본값 600)

    Returns:
        PNG 이미지 바이트 또는 None (실패 시)
    """
    if not PYMUPDF_AVAILABLE:
        logger.warning("PyMuPDF를 사용할 수 없어 이미지 추출을 건너뜁니다")
        return None

    try:
        # PDF 문서 열기
        doc = fitz.open(pdf_path)

        # 페이지 수 확인
        if page_number >= len(doc):
            logger.warning(f"PDF에 {page_number + 1}페이지가 없습니다 (총 {len(doc)}페이지)")
            doc.close()
            return None

        # 페이지 로드
        page = doc[page_number]

        # 페이지를 pixmap으로 렌더링
        zoom = dpi / 72  # 72 DPI가 기본
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # 이미지 크기 조정 생략 (PyMuPDF 최신 버전 호환성 문제로 원본 크기 사용)
        if pix.width > max_width:
            logger.info(f"이미지 크기: {pix.width}x{pix.height} 픽셀 (max_width 제한 미적용)")

        # PNG 바이트로 변환
        img_bytes = pix.tobytes("png")
        doc.close()

        # 파일 크기 확인 (500KB 제한)
        max_size = 512000  # 500KB
        if len(img_bytes) > max_size:
            logger.warning(f"이미지 크기가 {len(img_bytes):,} bytes로 500KB 제한 초과")

        logger.info(f"✅ PDF 페이지 {page_number + 1} 이미지 추출 성공: {len(img_bytes):,} bytes ({pix.width}x{pix.height}px)")
        return img_bytes

    except Exception as e:
        logger.error(f"PDF 페이지 이미지 추출 실패: {e}")
        return None


def extract_toc_page_for_email(pdf_path: str) -> Optional[bytes]:
    """
    이메일용 ITFIND PDF 목차 페이지 추출 (page 3)

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        PNG 이미지 바이트 또는 None
    """
    # ITFIND 목차는 보통 page 3 (index 2)
    return extract_page_as_image(pdf_path, page_number=2, dpi=200, max_width=600)


def extract_first_page_for_email(pdf_path: str) -> Optional[bytes]:
    """
    이메일용 전자신문 PDF 1페이지 추출

    전자신문 이메일 본문 상단에 표시할 1페이지 이미지를 추출합니다.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        PNG 이미지 바이트 또는 None (실패 시)
    """
    # 전자신문 1페이지 (page_number=0)
    return extract_page_as_image(pdf_path, page_number=0, dpi=200, max_width=600)


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        test_pdf = sys.argv[1]
        result = extract_toc_page_for_email(test_pdf)
        if result:
            print(f"이미지 추출 성공: {len(result):,} bytes")
        else:
            print("이미지 추출 실패")
    else:
        print("사용법: python pdf_image_extractor.py <pdf_path>")
