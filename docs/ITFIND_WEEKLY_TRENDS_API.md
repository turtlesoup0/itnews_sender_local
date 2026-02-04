# ITFIND 주간기술동향 API 문서

이 문서는 SPEC-ITFIND-001에서 구현된 ITFIND 주간기술동향 관련 API 함수에 대한 상세 설명입니다.

---

## 목차

- [컨텐츠 신선도 검증](#컨텐츠-신선도-검증)
- [PDF 페이지 이미지 추출](#pdf-페이지-이미지-추출)
- [한국어 첨부파일명 생성](#한국어-첨부파일명-생성)
- [RSS 발행일 파싱](#rss-발행일-파싱)
- [사용 예제](#사용-예제)

---

## 컨텐츠 신선도 검증

### `is_content_fresh()`

컨텐츠의 발행일이 지정된 일수 이내인지 확인하여 오래된 컨텐츠가 발송되는 것을 방지합니다.

**함수 시그니처:**
```python
def is_content_fresh(publish_date: str, staleness_days: int) -> bool
```

**파라미터:**
- `publish_date` (str): 발행일 문자열 (YYYY-MM-DD 형식, 예: "2026-02-04")
- `staleness_days` (int): 신선도 임계값 (일 단위)

**반환값:**
- `bool`: 컨텐츠가 신선하면 `True`, 그렇지 않으면 `False`

**동작:**
1. KST 타임존을 기준으로 날짜 계산
2. 현재 날짜와 발행일의 차이를 일 단위로 계산
3. 나이가 `staleness_days` 이하이면 신선한 것으로 간주
4. 날짜 파싱 실패 시 `False` 반환

**사용 예시:**
```python
from lambda_itfind_downloader import is_content_fresh

# 3일 전 컨텐츠 (신선함)
is_fresh = is_content_fresh("2026-02-01", staleness_days=7)  # True

# 10일 전 컨텐츠 (신선하지 않음)
is_fresh = is_content_fresh("2026-01-25", staleness_days=7)  # False
```

**설정:**
- `src/config.py`의 `ITFIND_STALENESS_DAYS` 상수로 기본값 설정 (기본값: 7일)

---

## PDF 페이지 이미지 추출

### `extract_page_as_image()`

PDF의 특정 페이지를 이미지로 추출하여 이메일 본문에 임베딩합니다.

**함수 시그니처:**
```python
def extract_page_as_image(
    pdf_path: str,
    page_number: int = 2,  # 0-based, so 2 = page 3
    dpi: int = 200,
    max_width: int = 600
) -> Optional[bytes]
```

**파라미터:**
- `pdf_path` (str): PDF 파일 경로
- `page_number` (int): 추출할 페이지 번호 (0-based, 기본값 2 = 3페이지)
- `dpi` (int): 이미지 해상도 (기본값 200)
- `max_width` (int): 최대 너비 (픽셀, 기본값 600)

**반환값:**
- `Optional[bytes]`: PNG 이미지 바이트 또는 `None` (실패 시)

**동작:**
1. PyMuPDF (fitz)를 사용하여 PDF 열기
2. 지정된 페이지를 pixmap으로 렌더링
3. 너비가 `max_width`를 초과하면 자동 크기 조정
4. PNG 바이트로 변환
5. 파일 크기 500KB 제한 확인 (경고 로그)

**에러 처리:**
- PyMuPDF가 없는 경우 `None` 반환
- 페이지 번호가 PDF 총 페이지 수를 초과하면 `None` 반환
- 기타 예외 발생 시 로그 기록 후 `None` 반환

**사용 예시:**
```python
from src.pdf_image_extractor import extract_page_as_image

# PDF 3페이지를 이미지로 추출
img_bytes = extract_page_as_image("/tmp/itfind.pdf", page_number=2)

if img_bytes:
    print(f"이미지 추출 성공: {len(img_bytes):,} bytes")
else:
    print("이미지 추출 실패")
```

### `extract_toc_page_for_email()`

이메일용 ITFIND PDF 목차 페이지(3페이지)를 추출하는 편의 함수입니다.

**함수 시그니처:**
```python
def extract_toc_page_for_email(pdf_path: str) -> Optional[bytes]
```

**파라미터:**
- `pdf_path` (str): PDF 파일 경로

**반환값:**
- `Optional[bytes]`: PNG 이미지 바이트 또는 `None`

---

## 한국어 첨부파일명 생성

### `generate_korean_filename()`

ITFIND PDF 첨부파일용 한국어 파일명을 생성하고 RFC 2231 인코딩을 지원합니다.

**함수 시그니처:**
```python
def generate_korean_filename(itfind_info: Optional["WeeklyTrend"] = None) -> tuple[str, str]
```

**파라미터:**
- `itfind_info` (Optional[WeeklyTrend]): ITFIND 정보 객체 (발행일, 호수 포함)

**반환값:**
- `tuple[str, str]`: `(korean_filename, ascii_filename)` 튜플
  - `korean_filename`: `주기동YYMMDD-xxxx호.pdf` 형식
  - `ascii_filename`: `itfind_YYMMDD-xxxx.pdf` (ASCII fallback)

**파일명 형식:**
- 한국어: `주기동{YYMMDD}-{issue_number}호.pdf`
  - 예: `주기동260204-2203호.pdf`
- ASCII fallback: `itfind_{YYMMDD}-{issue_number}.pdf`
  - 예: `itfind_260204-2203.pdf`

**사용 예시:**
```python
from src.email_sender import generate_korean_filename
from src.itfind_scraper import WeeklyTrend

# WeeklyTrend 객체 생성
itfind_info = WeeklyTrend(
    title="AI 기술 동향",
    issue_number="2203호",
    publish_date="2026-02-04",
    pdf_url="...",
    topics=["AI", "Cloud"]
)

# 파일명 생성
korean_fn, ascii_fn = generate_korean_filename(itfind_info)
print(korean_fn)  # 주기동260204-2203호.pdf
print(ascii_fn)   # itfind_260204-2203.pdf
```

---

## RSS 발행일 파싱

### `parse_rss_pubdate()`

RSS pubDate 문자열을 YYYY-MM-DD 형식으로 파싱합니다.

**함수 시그니처:**
```python
def parse_rss_pubdate(pubdate_str: str) -> Optional[str]
```

**파라미터:**
- `pubdate_str` (str): RFC 822 형식의 pubDate 문자열
  - 예: `"Mon, 03 Feb 2026 00:00:00 KST"`

**반환값:**
- `Optional[str]`: YYYY-MM-DD 형식의 날짜 문자열 또는 `None` (파싱 실패 시)

**지원하는 날짜 형식:**
1. RFC 822 with timezone: `%a, %d %b %Y %H:%M:%S %Z`
2. RFC 822 with numeric timezone: `%a, %d %b %Y %H:%M:%S %z`
3. Without timezone: `%a, %d %b %Y %H:%M:%S`
4. ISO 8601: `%Y-%m-%d`
5. Compact: `%Y%m%d`

**사용 예시:**
```python
from lambda_itfind_downloader import parse_rss_pubdate

# RFC 822 형식 파싱
date = parse_rss_pubdate("Mon, 03 Feb 2026 00:00:00 KST")
print(date)  # 2026-02-03

# ISO 8601 형식 파싱
date = parse_rss_pubdate("2026-02-03")
print(date)  # 2026-02-03
```

---

## 사용 예제

### 완전한 ITFIND 처리 워크플로우

```python
from lambda_itfind_downloader import (
    get_latest_weekly_trend_from_rss,
    is_content_fresh,
    download_pdf_direct
)
from src.config import Config
from src.pdf_image_extractor import extract_toc_page_for_email

# 1. RSS에서 최신 정보 조회
trend = get_latest_weekly_trend_from_rss()
if not trend:
    print("주간기술동향을 찾을 수 없습니다")
    exit()

# 2. 컨텐츠 신선도 확인
if not is_content_fresh(trend['publish_date'], Config.ITFIND_STALENESS_DAYS):
    print(f"컨텐츠가 신선하지 않습니다 (발행일: {trend['publish_date']})")
    exit()

# 3. PDF 다운로드
local_path = f"/tmp/itfind_{trend['issue_number']}.pdf"
if not download_pdf_direct(trend['streamdocs_id'], local_path):
    print("PDF 다운로드 실패")
    exit()

# 4. 목차 이미지 추출
toc_image = extract_toc_page_for_email(local_path)
if toc_image:
    print(f"목차 이미지 추출 성공: {len(toc_image):,} bytes")
```

### 이메일 본문에 목차 이미지 포함

```python
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from src.pdf_image_extractor import extract_toc_page_for_email

# 이메일 메시지 생성 (inline image를 위한 'related' 타입)
msg = MIMEMultipart('related')

# 목차 이미지 추출
toc_image_bytes = extract_toc_page_for_email(pdf_path)

# 본문 HTML 생성
if toc_image_bytes:
    body = """
    <html>
        <body>
            <div style="text-align: center; margin: 20px 0;">
                <p style="font-size: 0.9em; color: #666;">📄 목차 미리보기</p>
                <img src="cid:toc_image" alt="주간기술동향 목차"
                     style="max-width: 100%; height: auto;" />
            </div>
        </body>
    </html>
    """
else:
    body = "<html><body><p>목차 이미지를 불러올 수 없습니다</p></body></html>"

msg.attach(MIMEText(body, "html", "utf-8"))

# 이미지 첨부 (inline, CID 참조)
if toc_image_bytes:
    toc_image = MIMEImage(toc_image_bytes, _subtype='png')
    toc_image.add_header('Content-ID', '<toc_image>')
    toc_image.add_header('Content-Disposition', 'inline', filename='toc.png')
    msg.attach(toc_image)
```

---

## 의존성

### 필수 패키지

```txt
# requirements.txt
PyMuPDF>=1.24.0  # PDF 페이지 렌더링
python-dateutil   # 유연한 날짜 파싱
```

### 설치

```bash
pip install PyMuPDF>=1.24.0 python-dateutil
```

---

## 테스트

모든 함수는 단위 테스트로 검증됩니다:

```bash
# 컨텐츠 신선도 테스트
pytest tests/test_content_freshness.py -v

# PDF 이미지 추출 테스트
pytest tests/test_pdf_image_extractor.py -v

# 첨부파일명 생성 테스트
pytest tests/test_attachment_filename.py -v

# 이메일 본문 생성 테스트
pytest tests/test_email_body.py -v
```

---

## 참고사항

### PyMuPDF 가용성 처리

PyMuPDF가 설치되지 않은 환경에서는 자동으로 비활성화됩니다:

```python
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) not available. PDF image extraction disabled.")
```

### 이메일 클라이언트 호환성

- **Gmail Web**: RFC 2231 완전 지원, 한국어 파일명 표시
- **Apple Mail**: RFC 2231 완전 지원, CID 이미지 렌더링
- **Outlook**: RFC 2231 지원, ASCII fallback 사용

### 이미지 최적화

- DPI: 200 (이메일용 최적화)
- 최대 너비: 600px (반응형)
- 파일 크기 제한: 500KB
- 포맷: PNG (호환성 우선)

---

## 변경 이력

| 버전 | 날짜 | 변경 사항 |
|------|------|-----------|
| 1.0.0 | 2026-02-04 | SPEC-ITFIND-001 초기 구현 |
