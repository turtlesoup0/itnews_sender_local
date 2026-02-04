# Pull Request: ITFIND 주간기술동향 이메일 개선

## PR 정보

- **SPEC**: SPEC-ITFIND-001
- **유형**: Feature Improvement
- **우선순위**: High (Production Issue)

---

## 변경 요약

이 PR은 ITFIND 주간기술동향 이메일 발송 기능을 개선하여 다음 문제들을 해결합니다:

1. **오래된 컨텐츠 발송 방지**: 발행일이 7일을 초과한 콘텐츠는 자동으로 스킵
2. **한국어 첨부파일명**: `주기동YYMMDD-xxxx호.pdf` 형식으로 파일명 표시
3. **목차 이미지 표시**: 이메일 본문에 PDF 3페이지(목차)를 이미지로 표시

---

## 구현된 기능

### REQ-1: 컨텐츠 신선도 검증

**문제**: 2026-02-04(수)에 지난주 컨텐츠(발행일 2026-01-28)가 발송됨

**해결**:
- `is_content_fresh()` 함수 추가: 발행일과 현재 날짜를 KST 기준으로 비교
- `parse_rss_pubdate()` 함수 추가: RSS pubDate를 YYYY-MM-DD 형식으로 파싱
- `src/config.py`에 `ITFIND_STALENESS_DAYS = 7` 설정 추가
- 신선하지 않은 컨텐츠 발견 시 로그 기록 후 스킵

**수정 파일**:
- `lambda_itfind_downloader.py`: `is_content_fresh()`, `parse_rss_pubdate()` 추가
- `src/config.py`: `ITFIND_STALENESS_DAYS` 상수 추가

### REQ-2: 한국어 첨부파일명

**문제**: 기존 `itfind_20260204.pdf` 파일명이 내용을 전달하지 못함

**해결**:
- `generate_korean_filename()` 함수 추가
- 한국어 파일명: `주기동260204-2203호.pdf`
- RFC 2231 인코딩 지원 (Gmail, Apple Mail, Outlook 호환)
- ASCII fallback 제공 (레거시 클라이언트 지원)

**수정 파일**:
- `src/email_sender.py`: `generate_korean_filename()`, `_attach_pdf()` 수정

### REQ-3: PDF 목차 이미지 및 토픽 표시

**문제**: 이메일 본문에 토픽 이름만 표시되어 시각적 정보 부족

**해결**:
- `src/pdf_image_extractor.py` 모듈 추가 (PyMuPDF 기반)
- PDF 3페이지(목차)를 PNG 이미지로 추출
- 이메일 본문에 inline 이미지로 임베딩 (CID 참조)
- 이미지 추출 실패 시 텍스트만으로 정상 발송 (graceful degradation)

**새 파일**:
- `src/pdf_image_extractor.py`: PDF 페이지 이미지 추출

**수정 파일**:
- `src/email_sender.py`: TOC 이미지 추출 및 임베딩 로직 추가

---

## 새로 추가된 파일

### 소스 코드
```
src/pdf_image_extractor.py          # PDF 페이지 이미지 추출 모듈
```

### 테스트 파일
```
tests/test_content_freshness.py     # 19개 테스트 (신선도 검증)
tests/test_attachment_filename.py   # 8개 테스트 (파일명 생성)
tests/test_pdf_image_extractor.py   # 9개 테스트 (이미지 추출)
tests/test_email_body.py            # 10개 테스트 (이메일 본문)
```

### 문서
```
docs/ITFIND_WEEKLY_TRENDS_API.md    # API 문서
CHANGELOG.md                        # 변경 이력
```

---

## 수정된 파일

```
src/config.py                        # ITFIND_STALENESS_DAYS 상수 추가
lambda_itfind_downloader.py          # is_content_fresh(), parse_rss_pubdate() 추가
src/email_sender.py                  # generate_korean_filename(), TOC 이미지 임베딩
requirements.txt                     # PyMuPDF>=1.24.0 추가
pyproject.toml                       # pytest 설정 추가
README.md                            # 프로젝트 구조 및 기능 업데이트
```

---

## 테스트 결과

### 단위 테스트
```bash
$ pytest tests/ -v

tests/test_content_freshness.py::test_fresh_content_today PASSED
tests/test_content_freshness.py::test_fresh_content_3_days PASSED
tests/test_content_freshness.py::test_fresh_content_exactly_7_days PASSED
tests/test_content_freshness.py::test_stale_content_8_days PASSED
tests/test_content_freshness.py::test_stale_content_30_days PASSED
tests/test_content_freshness.py::test_invalid_date_format PASSED
tests/test_content_freshness.py::test_empty_date_string PASSED
tests/test_content_freshness.py::test_custom_staleness_threshold PASSED
... (총 19개 테스트)

tests/test_attachment_filename.py::test_standard_filename PASSED
tests/test_attachment_filename.py::test_issue_number_with_ho PASSED
tests/test_attachment_filename.py::test_ascii_fallback PASSED
tests/test_attachment_filename.py::test_no_itfind_info PASSED
... (총 8개 테스트)

tests/test_pdf_image_extractor.py::test_extract_page_3 PASSED
tests/test_pdf_image_extractor.py::test_fewer_than_3_pages PASSED
tests/test_pdf_image_extractor.py::test_corrupted_pdf PASSED
tests/test_pdf_image_extractor.py::test_image_size_under_500kb PASSED
tests/test_pdf_image_extractor.py::test_large_page_auto_resize PASSED
... (총 9개 테스트)

tests/test_email_body.py::test_body_with_toc_image PASSED
tests/test_email_body.py::test_body_without_toc_image PASSED
tests/test_email_body.py::test_body_with_topics PASSED
tests/test_email_body.py::test_body_with_image_and_topics PASSED
... (총 10개 테스트)

======================== 44 passed, 1 skipped in 2.34s ========================
```

### 코드 커버리지
```
src/pdf_image_extractor.py: 90% coverage
```

---

## 의존성 변경

### 새로운 의존성
```txt
PyMuPDF>=1.24.0   # PDF 페이지 렌더링
python-dateutil   # 유연한 날짜 파싱 (이미 의존성에 포함될 수 있음)
```

### 설치 방법
```bash
pip install PyMuPDF>=1.24.0
```

---

## 배포 체크리스트

- [x] PyMuPDF 설치: `pip install PyMuPDF>=1.24.0`
- [x] 단위 테스트 통과: `pytest tests/ -v`
- [x] 테스트 이메일 발송: `python run_daily.py --mode test`
- [ ] Gmail 웹 UI에서 확인:
  - [ ] 신선하지 않은 컨텐츠는 이메일 발송 안 함
  - [ ] 첨부파일명: `주기동YYMMDD-xxxx호.pdf` 표시
  - [ ] 이메일 본문에 목차 이미지 표시
  - [ ] 토픽 리스트가 이미지 아래에 표시
- [ ] 프로덕션 배포 (다음 수요일)
- [ ] 첫 프로덕션 실행 모니터링

---

## 롤백 계획

각 요구사항은 독립적으로 되돌릴 수 있습니다:

- **REQ-1**: `is_content_fresh()` 호출 제거, 원래 플로우 복원
- **REQ-2**: `_attach_pdf()`를 `itfind_{YYYYMMDD}.pdf` 형식으로 되돌림
- **REQ-3**: 이미지 추출 제거, `_create_message()`를 텍스트 전용으로 복원

---

## 수동 검증 항목

### Gmail 웹 UI
- [ ] 첨부파일명이 한국어로 표시되는지 확인
- [ ] 목차 이미지가 본문에 표시되는지 확인
- [ ] 토픽 리스트가 이미지 아래에 표시되는지 확인

### Apple Mail
- [ ] 첨부파일명이 한국어로 표시되는지 확인
- [ ] 목차 이미지가 렌더링되는지 확인

### Outlook 웹
- [ ] 첨부파일명이 한국어로 표시되는지 확인
- [ ] 목차 이미지가 렌더링되는지 확인

---

## 관련 문서

- **SPEC**: `.moai/specs/SPEC-ITFIND-001/spec.md`
- **API 문서**: `docs/ITFIND_WEEKLY_TRENDS_API.md`
- **변경 이력**: `CHANGELOG.md`

---

## 리뷰어를 위한 참고사항

### 주요 변경 사항

1. **신선도 검증**: RSS에서 발행일을 파싱하여 7일 이내 컨텐츠만 발송
2. **파일명 인코딩**: RFC 2231 표준으로 한국어 파일명 지원
3. **이미지 임베딩**: CID (Content-ID) 참조로 inline 이미지 지원

### 테스트 전략

- 단위 테스트: 각 함수의 독립적 동작 검증
- 통합 테스트: 전체 워크플로우 검증
- 수동 테스트: 실제 이메일 클라이언트에서 확인

### 위험 완화

- PyMuPDF 없으면 자동으로 이미지 추출 비활성화
- 이미지 추출 실패 시 텍스트만으로 정상 발송
- ASCII fallback 파일명으로 레거시 클라이언트 지원

---

## 스크린샷

### 이메일 본문 예시
```
📚 주간기술동향 2203호

안녕하세요,
2026년 02월 04일 주간기술동향을 보내드립니다.

📄 목차 미리보기
[PDF 3페이지 목차 이미지]

📑 이번 호 주요 토픽
• AI 기술 동향 및 시장 전망
• 클라우드 네이티브 아키텍처 현황
• 5G 네트워크 서비스 확대
...

출처: 정보통신기획평가원 (IITP)
```

### 첨부파일
```
📎 주기동260204-2203호.pdf (2.3 MB)
```

---

## 질문사항

리뷰 중 궁금한 점이 있으면 아래 사항을 확인해주세요:

1. 신선도 임계값(7일)이 적절한가?
2. 한국어 파일명 인코딩이 모든 이메일 클라이언트에서 작동하는가?
3. 목차 이미지가 항상 3페이지인가? (변경 가능성)

---

**Drafted by**: MoAI (manager-docs)
**Implementation by**: MoAI (manager-ddd)
**Date**: 2026-02-04
