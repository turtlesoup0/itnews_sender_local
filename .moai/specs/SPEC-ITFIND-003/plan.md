# SPEC-ITFIND-003: 구현 계획

**SPEC ID**: SPEC-ITFIND-003
**작성일**: 2026-02-04
**상태**: Planned
**담당자**: TBD

## 개요 (Overview)

본 계획은 전자신문 이메일에 1페이지 스크린샷 추가, 주간기술동향 PDF 메타데이터에 토픽 저장, 주간기술동향 iCloud 자동 업로드 기능을 구현하기 위한 상세 절차를 정의합니다.

## 구현 마일스톤 (Milestones)

### 1차 목표 (Primary Goals)
- 전자신문 1페이지 이미지 추출 및 이메일 포함
- 주간기술동향 PDF 메타데이터에 토픽 저장

### 2차 목표 (Secondary Goals)
- 주간기술동향 iCloud Drive 업로드
- 통합 테스트 및 검증

## 기술 접근 방식 (Technical Approach)

### TASK-1: 전자신문 1페이지 이미지 추출 함수

**파일**: `src/pdf_image_extractor.py`

**구현 내용**:
```python
def extract_first_page_for_email(pdf_path: str) -> Optional[bytes]:
    """
    전자신문 PDF 1페이지를 이메일용 이미지로 추출

    Args:
        pdf_path: 전자신문 PDF 파일 경로

    Returns:
        PNG 이미지 바이트 또는 None (실패 시)
    """
    return extract_page_as_image(pdf_path, page_number=0, dpi=200, max_width=600)
```

**기술 포인트**:
- 기존 `extract_page_as_image()` 함수 재사용
- `page_number=0`으로 1페이지 추출
- DPI 200, 최대 너비 600px (ITFIND 설정과 동일)

**검증 방법**:
- 전자신문 PDF로 로컬 테스트
- 이미지 크기 확인 (500KB 이내)
- 이미지 품질 확인

### TASK-2: 이메일 본문에 전자신문 이미지 포함

**파일**: `src/email_sender.py`

**구현 내용**:
1. `_create_message()` 함수에 전자신문 이미지 추출 로직 추가
2. 전자신문 이미지를 MIMEImage로 첨부 (CID: `etnews_first_page`)
3. `_create_email_body()` 함수에 전자신문 이미지 HTML 추가

**코드 변경**:
```python
# _create_message() 함수
etnews_image_bytes = None
if not is_itfind_only:  # 전자신문 이메일인 경우만
    try:
        from .pdf_image_extractor import extract_first_page_for_email
        etnews_image_bytes = extract_first_page_for_email(pdf_path)
        if etnews_image_bytes:
            logger.info("✅ 전자신문 1페이지 이미지 추출 성공")
    except Exception as e:
        logger.warning(f"전자신문 이미지 추출 실패: {e}")

# 이미지 첨부 (기존 ITFIND TOC 이미지 로직 참고)
if etnews_image_bytes:
    etnews_image = MIMEImage(etnews_image_bytes, _subtype='png')
    etnews_image.add_header('Content-ID', '<etnews_first_page>')
    etnews_image.add_header('Content-Disposition', 'inline', filename='etnews_p1.png')
    msg.attach(etnews_image)
```

**이메일 본문 변경**:
```python
# _create_email_body() 함수
def _create_email_body(
    self,
    recipient_email: Optional[str] = None,
    itfind_info: Optional["WeeklyTrend"] = None,
    has_toc_image: bool = False,
    has_etnews_image: bool = False  # NEW PARAMETER
) -> str:
```

**전자신문 본문 HTML**:
```html
<div style="text-align: center; margin: 20px 0;">
    <p style="font-size: 0.9em; color: #666;">📰 오늘의 주요 기사 미리보기</p>
    <img src="cid:etnews_first_page" alt="전자신문 1페이지" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;" />
</div>
```

### TASK-3: PDF 메타데이터에 토픽 저장

**파일**: `lambda_itfind_downloader.py`

**구현 내용**:
1. `download_itfind_pdf()` 함수에서 PDF 다운로드 후 메타데이터 설정
2. PyMuPDF의 `doc.set_metadata()` 사용
3. `categorized_topics`를 JSON string으로 변환하여 저장

**코드 변경**:
```python
# download_itfind_pdf() 함수 - 3.5단계 이후에 추가
# 3.6단계: PDF 메타데이터에 카테고리별 토픽 저장
logger.info("3.6단계: PDF 메타데이터에 카테고리별 토픽 저장")

try:
    import fitz  # PyMuPDF
    import json

    doc = fitz.open(local_path)

    # 메타데이터 형식: JSON string
    metadata_description = json.dumps(categorized_topics, ensure_ascii=False, indent=2)

    # 메타데이터 설정
    doc.set_metadata({"description": metadata_description})

    # 증분 저장 (빠름, 파일 크기 증가 최소화)
    doc.saveIncr()
    doc.close()

    logger.info(f"✅ PDF 메타데이터 저장 완료: {len(metadata_description)} chars")

except Exception as e:
    logger.warning(f"PDF 메타데이터 저장 실패 (무시): {e}")
```

**기술 포인트**:
- `saveIncr()` 사용으로 저장 속도 최적화
- JSON `indent=2`로 가독성 확보
- `ensure_ascii=False`로 한글 텍스트 지원

### TASK-4: ITFIND iCloud 업로드 함수

**파일**: `src/workflow/icloud_workflow.py`

**구현 내용**:
```python
def upload_itfind_to_icloud(pdf_path: str, issue_number: str, publish_date: str) -> Optional[str]:
    """
    주간기술동향 PDF를 iCloud Drive에 업로드

    Args:
        pdf_path: 주간기술동향 PDF 파일 경로
        issue_number: 호수 (예: "2203")
        publish_date: 발행일 (YYYY-MM-DD)

    Returns:
        업로드된 iCloud Drive 경로, 실패 시 None
    """
    # Lambda 환경이면 스킵
    if os.environ.get("AWS_EXECUTION_ENV"):
        logger.info("Lambda 환경 — ITFIND iCloud 업로드 스킵")
        return None

    try:
        # KST 기준 연도 추출
        kst = timezone(timedelta(hours=9))
        pub_dt = datetime.strptime(publish_date, "%Y-%m-%d").replace(tzinfo=kst)
        yyyy = pub_dt.strftime("%Y")
        yyyymmdd = pub_dt.strftime("%Y%m%d")

        # iCloud 경로 생성
        itfind_base_path = os.path.expanduser(
            "~/Library/Mobile Documents/com~apple~CloudDocs/주간 기술 동향"
        )
        dest_dir = os.path.join(itfind_base_path, yyyy)
        os.makedirs(dest_dir, exist_ok=True)

        # 파일명 생성
        filename = f"ITFIND_주간기술동향_{issue_number}호_{yyyymmdd}.pdf"
        dest_path = os.path.join(dest_dir, filename)

        # 파일 복사
        shutil.copy2(pdf_path, dest_path)
        logger.info(f"✅ iCloud Drive에 ITFIND PDF 복사 완료: {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(f"ITFIND iCloud 업로드 실패 (무시): {e}")
        return None
```

**기술 포인트**:
- 기존 `upload_to_icloud()` 함수와 동일한 패턴 사용
- 파일명 형식: `ITFIND_주간기술동향_XXXX호_YYYYMMDD.pdf`
- 연도별 폴더 구조: `주간 기술 동향/YYYY/`

### TASK-5: Lambda Handler에서 iCloud 업로드 호출

**파일**: `lambda_handler.py`

**구현 내용**:
1. 이메일 발송 완료 후 ITFIND iCloud 업로드 호출
2. `cleanup_temp_files()`에 `itfind_pdf_path` 추가 이미 있음

**코드 변경**:
```python
# handler() 함수 - 4-1단계 이후에 추가
# 4-2. ITFIND iCloud Drive 업로드 (로컬 전용)
if itfind_pdf_path and itfind_trend_info:
    try:
        from src.workflow.icloud_workflow import upload_itfind_to_icloud
        upload_itfind_to_icloud(
            itfind_pdf_path,
            itfind_trend_info.get('issue_number', ''),
            itfind_trend_info.get('publish_date', '')
        )
    except Exception as icloud_error:
        logger.error(f"ITFIND iCloud 업로드 실패 (무시): {icloud_error}")
```

## 의존성 관계 (Dependencies)

```
TASK-1 (전자신문 이미지 추출)
    ↓
TASK-2 (이메일 본문에 포함)
    ↓ (독립)
TASK-3 (PDF 메타데이터) ← TASK-4 (iCloud 업로드) ← TASK-5 (Handler 호출)
```

**병렬 실행 가능**:
- TASK-1/TASK-2와 TASK-3/TASK-4는 독립적으로 개발 가능
- TASK-1과 TASK-2는 순차 실행 필요
- TASK-3과 TASK-4는 독립 실행 가능

## 위험 요소 및 대응 계획 (Risks and Mitigation)

### 위험 1: 전자신문 1페이지 이미지 크기 초과
- **위험**: 1페이지 내용이 많아 이미지가 500KB 초과
- **대응**: DPI 낮추기 (150) 또는 max_width 축소 (400px)

### 위험 2: PDF 메타데이터 호환성
- **위험**: 일부 PDF 뷰어가 Description 메타데이터를 표시하지 않음
- **대응**: 주요 뷰어(Adobe Acrobat, Preview, Chrome)에서 테스트

### 위험 3: iCloud 경로 존재하지 않음
- **위험**: 로컬 환경에 iCloud Drive가 설정되지 않음
- **대응**: 경로 검사 후 없으면 경고 로그 후 스킵

### 위험 4: Lambda 환경에서 PyMuPDF 메타데이터 쓰기 오류
- **위험**: Lambda 환경에서 PDF 수정 권한 문제
- **대응**: try-except로 감싸고 실패 시 경고 로그 후 계속

## 테스트 계획 (Testing Plan)

### 단위 테스트
- `test_pdf_image_extractor.py`: `extract_first_page_for_email()` 테스트
- `test_icloud_workflow.py`: `upload_itfind_to_icloud()` 테스트

### 통합 테스트
- 전자신문 이메일 발송 후 1페이지 이미지 포함 확인
- 주간기술동향 PDF 다운로드 후 메타데이터 확인
- 주간기술동향 iCloud 업로드 확인 (로컬만)

### 수동 테스트 절차
1. 전자신문 이메일 발송 테스트
   - `python -m src.scraper`로 전자신문 다운로드
   - `src/email_sender.py`로 이메일 발송
   - 이메일 수신 후 1페이지 이미지 확인

2. 주간기술동향 메타데이터 테스트
   - `python lambda_itfind_downloader.py`로 PDF 다운로드
   - Preview.app에서 PDF 열고 속성(Description) 확인

3. iCloud 업로드 테스트
   - 로컬에서 `lambda_handler.py` 실행 (test mode)
   - `~/Library/Mobile Documents/com~apple~CloudDocs/주간 기술 동향/YYYY/` 경로 확인

## 배포 계획 (Deployment Plan)

### 단계 1: 로컬 개발 및 테스트
1. 각 기능 별도 개발
2. 로컬에서 통합 테스트
3. 테스트 이메일 발송

### 단계 2: Lambda 배포
1. Lambda 레이어에 PyMuPDF 포함 확인
2. Lambda 함수 배포
3. 테스트 모드로 Lambda 실행

### 단계 3: OPR 모드 전환
1. 수요일에 수요일만 정상 동작 확인
2. OPR 모드로 정식 릴리스

## 정의 완료 기준 (Definition of Done)

- [ ] 전자신문 이메일에 1페이지 이미지 포함됨
- [ ] 주간기술동향 PDF Description 메타데이터에 토픽 저장됨
- [ ] 주간기술동향 PDF가 iCloud Drive에 업로드됨
- [ ] 단위 테스트 통과
- [ ] 수동 테스트 통과
- [ ] Lambda 배포 및 테스트 완료
- [ ] 코드 리뷰 완료
- [ ] CHANGELOG.md 업데이트

## 추적 가능성 (Traceability)

**TAG**: `SPEC-ITFIND-003`

**관련 SPEC**:
- SPEC-ITFIND-001: ITFIND 주간기술동향 이메일 개선 (기반 기능)
- SPEC-ITFIND-002: Chapter 기반 토픽 추출 (토픽 데이터 소스)

**구현 작업**:
- TASK-1: 전자신문 1페이지 이미지 추출 함수
- TASK-2: 이메일 본문에 전자신문 이미지 포함
- TASK-3: PDF 메타데이터에 토픽 저장
- TASK-4: ITFIND iCloud 업로드 함수
- TASK-5: Lambda Handler에서 iCloud 업로드 호출
- TASK-6: 테스트 및 검증
