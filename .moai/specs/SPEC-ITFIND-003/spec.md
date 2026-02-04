# SPEC-ITFIND-003: 전자신문/주간기술동향 이메일 및 저장 개선

**SPEC ID**: SPEC-ITFIND-003
**작성일**: 2026-02-04
**상태**: Planned
**우선순위**: Medium
**담당자**: TBD

## TAG BLOCK

```yaml
tags:
  - email
  - etnews
  - itfind
  - icloud
  - pdf
  - metadata
domains:
  - email
  - storage
  - pdf_processing
```

## 개요 (Overview)

전자신문 이메일에 1페이지 스크린샷 추가, 주간기술동향 PDF에 토픽 메타데이터 저장, 주간기술동향 iCloud 자동 업로드 기능을 추가하여 사용자 경험을 개선합니다.

## 환경 (Environment)

### 시스템 환경
- **Python 버전**: 3.14+
- **PyMuPDF (fitz)**: PDF 이미지 추출 및 메타데이터 설정
- **iCloud Drive**: 로컬 환경에서만 동작 (Lambda 환경에서 스킵)
- **SMTP**: Gmail SMTP를 통한 이메일 발송

### 현재 시스템 상태
- 전자신문: 광고 페이지 제거 후 이메일 발송
- 주간기술동향: 수요일에만 다운로드되어 이메일 첨부
- 주간기술동향: PDF 3페이지 목차 이미지를 이메일 본문에 포함
- iCloud: 전자신문만 `전자신문/YYYY/MM/` 폴더에 저장

### 제약 조건
- Lambda 환경에서는 iCloud 업로드 스킵 (로컬 전용)
- PDF 메타데이터는 PyMuPDF로만 수정 가능 (pypdf는 메타데이터 쓰기 제한)
- 이메일 이미지 크기 제한: 500KB (기존 정책 유지)

## 가정 (Assumptions)

1. **PDF 구조 가정**: 전자신문 PDF는 1페이지 이상 존재
2. **토픽 추출 성공**: 주간기술동향 토픽 추출이 성공적으로 완료됨
3. **iCloud 경로 존재**: 로컬 환경에 iCloud Drive가 설정되어 있음
4. **메타데이터 호환**: PDF 뷰어가 Description 메타데이터를 표시할 수 있음

## 요구사항 (Requirements)

### REQ-1: 전자신문 1페이지 스크린샷 메일 포함

**WHEN** 전자신문 이메일 발송 시 **THEN** 시스템은 전자신문 PDF의 1페이지를 이미지로 캡처하여 메일 본문 상단에 포함해야 한다.

**상세 요구사항:**
- `src/pdf_image_extractor.py`에 `extract_first_page_for_email()` 함수 추가
- `page_number=0`으로 `extract_page_as_image()` 호출
- DPI 200, 최대 너비 600px (기존 ITFIND 설정과 동일)
- `src/email_sender.py`의 `_create_message()`에서 전자신문 이미지 추출 및 첨부
- 이미지 CID: `etnews_first_page`, 파일명: `etnews_p1.png`
- 이메일 본문 상단에 "📰 오늘의 주요 기사 미리보기" 섹션 추가

### REQ-2: 주간기술동향 PDF 메타데이터에 토픽 추가

**WHEN** 주간기술동향 PDF 다운로드 완료 후 **THEN** 시스템은 추출된 카테고리별 토픽을 PDF 파일의 Description 메타데이터에 저장해야 한다.

**상세 요구사항:**
- `lambda_itfind_downloader.py`의 `download_itfind_pdf()` 함수에서 처리
- PyMuPDF의 `doc.set_metadata()` 사용
- 메타데이터 키: `description`
- 형식: JSON string 또는 텍스트로 카테고리별 토픽 저장
- 저장 예시: `{"기획시리즈": ["토픽1", "토픽2"], "ICT 신기술": ["토픽3"]}`
- PDF 수정 후 저장 (동일 경로에 덮어쓰기)

### REQ-3: 주간기술동향 iCloud 저장

**WHEN** 주간기술동향 이메일 발송 완료 후 **THEN** 시스템은 주간기술동향 PDF를 iCloud Drive에 업로드해야 한다.

**상세 요구사항:**
- `src/workflow/icloud_workflow.py`에 `upload_itfind_to_icloud()` 함수 추가
- 경로: `Mobile Documents/com~apple~CloudDocs/주간 기술 동향/YYYY/`
- 파일명: `ITFIND_주간기술동향_XXXX호_YYYYMMDD.pdf` 형식
- `lambda_handler.py`에서 이메일 발송 후 iCloud 업로드 호출
- Lambda 환경에서는 자동 스킵 (기존 전자신문 로직 재사용)

## 비기능 요구사항 (Non-Functional Requirements)

### 성능 (Performance)
- 전자신문 1페이지 이미지 추출: 3초 이내
- PDF 메타데이터 설정: 1초 이내
- iCloud 업로드: 5초 이내 (로컬 환경)

### 호환성 (Compatibility)
- PDF 메타데이터: Adobe Acrobat, Preview, Chrome PDF Viewer 등 주요 뷰어 지원
- 이메일 이미지: Gmail, Outlook, Apple Mail 등 주요 이메일 클라이언트 호환

### 신뢰성 (Reliability)
- 이미지 추출 실패 시 이메일 발송 계속 (텍스트만 발송)
- 메타데이터 설정 실패 시 경고 로그 후 계속
- iCloud 업로드 실패 시 예외를 발생시키지 않고 로그만 기록

## 명세 (Specifications)

### SPEC-1: 전자신문 1페이지 이미지 추출

```python
# src/pdf_image_extractor.py
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

### SPEC-2: 이메일 본문에 전자신문 이미지 포함

```python
# src/email_sender.py
def _create_message(...):
    # 전자신문 1페이지 이미지 추출
    etnews_image_bytes = None
    if not is_itfind_only:  # 전자신문 이메일인 경우만
        try:
            from .pdf_image_extractor import extract_first_page_for_email
            etnews_image_bytes = extract_first_page_for_email(pdf_path)
        except Exception as e:
            logger.warning(f"전자신문 이미지 추출 실패: {e}")

    # 이메일 본문 생성
    body = self._create_email_body(
        recipient_email,
        itfind_info,
        has_etnews_image=(etnews_image_bytes is not None),
        has_toc_image=(toc_image_bytes is not None)
    )
```

### SPEC-3: PDF 메타데이터에 토픽 저장

```python
# lambda_itfind_downloader.py
async def download_itfind_pdf() -> Optional[Dict[str, Any]]:
    # ... 기존 다운로드 로직 ...

    # 3.6단계: PDF 메타데이터에 토픽 저장
    logger.info("3.6단계: PDF 메타데이터에 카테고리별 토픽 저장")

    try:
        import fitz  # PyMuPDF
        doc = fitz.open(local_path)

        # 메타데이터 형식: JSON string
        import json
        metadata_description = json.dumps(categorized_topics, ensure_ascii=False)

        # 메타데이터 설정
        doc.set_metadata({"description": metadata_description})
        doc.saveIncr()  # 증분 저장 (빠름)
        doc.close()

        logger.info(f"✅ PDF 메타데이터 저장 완료: {len(metadata_description)} chars")

    except Exception as e:
        logger.warning(f"PDF 메타데이터 저장 실패 (무시): {e}")
```

### SPEC-4: iCloud 업로드

```python
# src/workflow/icloud_workflow.py
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

        # iCloud 경로 생성
        itfind_base_path = os.path.expanduser(
            "~/Library/Mobile Documents/com~apple~CloudDocs/주간 기술 동향"
        )
        dest_dir = os.path.join(itfind_base_path, yyyy)
        os.makedirs(dest_dir, exist_ok=True)

        # 파일명 생성
        yyyymmdd = pub_dt.strftime("%Y%m%d")
        filename = f"ITFIND_주간기술동향_{issue_number}호_{yyyymmdd}.pdf"
        dest_path = os.path.join(dest_dir, filename)

        # 파일 복사
        shutil.copy2(pdf_path, dest_path)
        logger.info(f"iCloud Drive에 ITFIND PDF 복사 완료: {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(f"ITFIND iCloud 업로드 실패 (무시): {e}")
        return None
```

### SPEC-5: Lambda Handler에서 iCloud 업로드 호출

```python
# lambda_handler.py
def handler(event, context):
    # ... 기존 로직 ...

    # 4-2. ITFIND iCloud Drive 업로드 (로컬 전용)
    if itfind_pdf_path and itfind_trend_info:
        from src.workflow.icloud_workflow import upload_itfind_to_icloud
        upload_itfind_to_icloud(
            itfind_pdf_path,
            itfind_trend_info.get('issue_number', ''),
            itfind_trend_info.get('publish_date', '')
        )
```

## 변경 영향 (Impact Analysis)

### 영향 받는 파일
1. `src/pdf_image_extractor.py` - `extract_first_page_for_email()` 함수 추가
2. `src/email_sender.py` - 전자신문 이미지 첨부 로직 추가
3. `lambda_itfind_downloader.py` - PDF 메타데이터 설정 로직 추가
4. `src/workflow/icloud_workflow.py` - `upload_itfind_to_icloud()` 함수 추가
5. `lambda_handler.py` - ITFIND iCloud 업로드 호출 추가

### 영향 받지 않는 파일
- `src/pdf_processor.py` - 전자신문 광고 제거 로직 unchanged
- `src/recipients/` - 수신자 관리 unchanged
- `src/storage/` - DynamoDB 스토리지 unchanged

## 추적 가능성 (Traceability)

**TAG**: `SPEC-ITFIND-003`

**관련 SPEC**:
- SPEC-ITFIND-001: ITFIND 주간기술동향 이메일 개선 (기반 기능)
- SPEC-ITFIND-002: Chapter 기반 토픽 추출 (토픽 데이터 소스)

**구현 작업**:
- [ ] TASK-1: 전자신문 1페이지 이미지 추출 함수 구현
- [ ] TASK-2: 이메일 본문에 전자신문 이미지 포함
- [ ] TASK-3: PDF 메타데이터에 토픽 저장 구현
- [ ] TASK-4: ITFIND iCloud 업로드 함수 구현
- [ ] TASK-5: Lambda Handler에서 iCloud 업로드 호출
- [ ] TASK-6: 테스트 및 검증
