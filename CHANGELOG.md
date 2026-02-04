# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - 2026-02-04

#### ITFIND 주간기술동향 이메일 개선 (SPEC-ITFIND-001)

**REQ-1: 컨텐츠 신선도 검증**
- `is_content_fresh()` 함수: 발행일이 6일 이내인지 확인하여 오래된 컨텐츠 발송 방지
- `parse_rss_pubdate()` 함수: RSS pubDate를 YYYY-MM-DD 형식으로 파싱
- `src/config.py`에 `ITFIND_STALENESS_DAYS = 6` 설정 추가 (7일 → 6일 변경)
- 신선하지 않은 컨텐츠 발견 시 자동 스킵 및 로그 기록

**REQ-2: 한국어 첨부파일명**
- `generate_korean_filename()` 함수: `주기동YYMMDD-xxxx호.pdf` 형식의 파일명 생성
- RFC 2231 인코딩 지원 (Gmail, Apple Mail, Outlook 호환)
- ASCII fallback 파일명 제공 (레거시 클라이언트 지원)
- iCloud Drive 저장 파일명을 `주기동YYMMDD-xxxx호.pdf` 형식으로 통일

**REQ-3: PDF 목차 이미지 및 토픽 표시**
- `src/pdf_image_extractor.py` 모듈 추가 (PyMuPDF 기반)
- `extract_page_as_image()`: PDF 페이지를 PNG 이미지로 추출
- `extract_toc_page_for_email()`: 이메일용 목차 페이지(3페이지) 추출
- `extract_first_page_for_email()`: 전자신문 1페이지 이미지 추출 추가
- 이메일 본문에 목차 이미지를 inline으로 임베딩 (CID 참조)
- 전자신문 이메일에 1페이지 이미지 포함
- 이미지 추출 실패 시 텍스트만으로 정상 발송 (graceful degradation)

#### Chapter 기반 토픽 추출 및 PDF 메타데이터 (SPEC-ITFIND-002)

**Chapter 패턴 기반 토픽 추출**
- `extract_topics_from_chapters()`: PDF 전체 본문에서 Chapter 패턴 탐지
- 역방향 텍스트 추출: Chapter 라인 이전의 토픽 제목 추출
- 카테고리별 분류: 기획시리즈, ICT 신기술
- 대시 라인(`- xxx -`) 및 페이지 번호 패턴 필터링

**PDF 메타데이터에 토픽 저장**
- `doc.set_metadata({"subject": ...})`: PyMuPDF subject 필드에 토픽 저장
- macOS Preview "추가정보 > 설명"에 토픽 표시
- Incremental save로 파일 크기 최적화

**WeeklyTrend dataclass 확장**
- `categorized_topics` 필드 추가: `Dict[str, List[str]]`
- 기획시리즈/ICT 신기술 카테고리별 토픽 포함

#### 새로운 파일
- `src/pdf_image_extractor.py` - PDF 페이지 이미지 추출 모듈
- `tests/test_content_freshness.py` - 컨텐츠 신선도 검증 테스트 (19개)
- `tests/test_attachment_filename.py` - 첨부파일명 생성 테스트 (8개)
- `tests/test_pdf_image_extractor.py` - PDF 이미지 추출 테스트 (9개)
- `tests/test_email_body.py` - 이메일 본문 생성 테스트 (10개)
- `docs/ITFIND_WEEKLY_TRENDS_API.md` - API 문서

#### 수정된 파일
- `src/config.py` - `ITFIND_STALENESS_DAYS` 상수 추가 (7 → 6일로 변경)
- `lambda_itfind_downloader.py` - `is_content_fresh()`, `parse_rss_pubdate()`, Chapter 토픽 추출, PDF 메타데이터 저장 추가
- `src/email_sender.py` - `generate_korean_filename()`, TOC 이미지 임베딩, 전자신문 1페이지 이미지 추가
- `src/itfind_scraper.py` - `WeeklyTrend` dataclass에 `categorized_topics` 필드 추가
- `src/workflow/pdf_workflow.py` - `WeeklyTrend` import 및 categorized_topics 전달
- `src/workflow/icloud_workflow.py` - iCloud 파일명을 `주기동YYMMDD-xxxx호.pdf` 형식으로 변경
- `src/pdf_image_extractor.py` - `extract_first_page_for_email()` 함수 추가
- `lambda_handler.py` - WeeklyTrend 속성 접근 수정 (.get() → 직접 접근)
- `pyproject.toml` - 프로젝트 섹션 추가 (의존성 명시, requires-python 설정)

#### 테스트 커버리지
- 총 46개 테스트 (44 passed, 1 skipped)
- `pdf_image_extractor.py`: 90% 코드 커버리지

---

## [1.0.0] - 2026-01-XX

### Added
- 전자신문 PDF 자동 다운로드 및 광고 제거
- Gmail SMTP를 통한 이메일 자동 발송
- ITFIND 주간기술동향 수요일 자동 발송
- launchd 스케줄러 지원 (매일 06:00 KST)
- 수신인 관리 (DynamoDB/SQLite)
- 수신거부 기능 (HMAC 토큰 기반)
- iCloud Drive 자동 업로드 (로컬 전용)
- 구독 만료 알림 (7일 전)
- 멱등성 보장 (일 1회 실행)
- 실패 추적 (3회 초과 시 스킵)

---

[Unreleased]: https://github.com/your-username/your-repo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/your-username/your-repo/releases/tag/v1.0.0
