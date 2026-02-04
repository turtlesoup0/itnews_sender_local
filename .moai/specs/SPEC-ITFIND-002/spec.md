# SPEC-ITFIND-002: Chapter 기반 토픽 추출

**Status**: Draft
**Created**: 2026-02-04
**Author**: MoAI (manager-spec)
**Priority**: High (production issue)

---

## 1. 배경

### 1.1 문제 정의

현재 `extract_topics_from_pdf_page3()` 함수는 PDF 3페이지 목차에서 상태 머신(State Machine)을 사용하여 토픽을 추출합니다. 이 방식은 다음과 같은 문제가 있습니다:

1. **저자별 목차 구조 차이**: 다른 저자가 목차를 다르게 구성하여 상태 머신이 실패함
2. **하위 목차 오류 추출**: 하위 목차(세부 항목)가 메인 토픽으로 잘못 추출됨
3. **규칙 기반 필터링 한계**: 모든 변형을 처리할 수 없음

### 1.2 제안된 해결책

PDF 전체 본문에는 "Chapter 01", "Chapter 02", "Chapter 03" 패턴이 존재하여 각 토픽을 구분합니다. 이 구조는 모든 PDF에서 저자에 상관없이 일관적입니다.

**예시 PDF 구조**:
```
[PDF 본문]
Chapter 01
6G 이동통신을 위한 과금정책 및 경제모델 연구 동향
... (본문 내용) ...

Chapter 02
공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석
... (본문 내용) ...
```

### 1.3 테스트 케이스

| 호수 | 기획시리즈 | ICT 신기술 |
|------|-----------|-----------|
| 2154 | 6G 이동통신을 위한 과금정책 및 경제모델 연구 동향 | 공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석 |
| 2198 | AI를 위한 자동화된 데이터 관리 체계의 필요성 | AI 기술 융합을 통한 전력산업 업무 자동화 전략과 실현 방안 |
| 2199 | 건설 분야 AI 학습 데이터셋 구축 사례 및 동향 | 트랜스포머 최적화 기술 연구 동향 |
| 2200 | AI 학습 데이터 신뢰성 확보를 위한 시험평가 기반 접근 방식 동향 | 도시문제 해결을 위한 디지털트윈 활용 방향 |
| 2203 | AI-Ready 산업 생태계 조성을 위한 구조적 설계, AI 시대의 종합 리스크 관리 (2 topics) | 우주국방반도체 주요국 정책 동향 분석 및 국내 시사점 |

---

## 2. 환경 및 가정

### 2.1 환경

- **Python 버전**: 3.11+
- **PDF 라이브러리**: PyMuPDF (fitz) >= 1.24.0
- **배포 환경**: Mac Mini (로컬) + AWS Lambda (백업)

### 2.2 가정

- **ASSUMPTION-1**: 모든 ITFIND PDF는 "Chapter XX" 패턴을 사용하여 토픽을 구분
- **ASSUMPTION-2**: Chapter 번호는 01부터 순차적으로 증가 (01, 02, 03...)
- **ASSUMPTION-3**: Chapter 표시 바로 다음 줄에 토픽 제목이 위치
- **ASSUMPTION-4**: 토픽 제목은 10자 이상 100자 이하
- **ASSUMPTION-5**: 기획시리즈와 ICT 신기술은 순서로 구분 (먼저 나오는 쪽이 기획시리즈)

---

## 3. 요구사항 (EARS 형식)

### REQ-1: Chapter 패턴 기반 토픽 추출

**WHEN** 시스템이 ITFIND PDF 본문에서 "Chapter XX" 패턴을 감지하면,
**THE SYSTEM SHALL** Chapter 번호 다음 줄에서 토픽 제목을 추출하고,
**THE SYSTEM SHALL** 추출된 토픽을 순서대로 목록에 저장해야 한다.

**세부 요구사항**:
- **AC-1.1**: "Chapter 01", "Chapter 02", ..., "Chapter 99" 패턴을 정규표현식으로 감지
- **AC-1.2**: Chapter 패턴 다음 줄(비어있지 않은 첫 줄)을 토픽 제목으로 추출
- **AC-1.3**: 토픽 제목 길이 검증 (10자 이상 100자 이하)
- **AC-1.4**: 하위 목차(짧은 텍스트, 숫자)는 필터링
- **AC-1.5**: 중복 토픽 제거

### REQ-2: 카테고리 매핑

**WHEN** 시스템이 모든 토픽을 추출하면,
**THE SYSTEM SHALL** 토픽 순서를 기준으로 "기획시리즈"와 "ICT 신기술" 카테고리로 분류해야 한다.

**세부 요구사항**:
- **AC-2.1**: 첫 번째 토픽(또는 그룹)은 "기획시리즈"로 분류
- **AC-2.2**: 두 번째 토픽(또는 그룹)은 "ICT 신기술"로 분류
- **AC-2.3**: 3개 이상의 토픽이 있는 경우, 첫 2개를 기획시리즈, 나머지를 ICT 신기술로 분류 (2203호 특례)
- **AC-2.4**: 카테고리 분류 결과를 딕셔너리 형태로 반환

### REQ-3: 검증 로깅

**WHEN** 시스템이 Chapter 기반 토픽 추출을 실행하면,
**THE SYSTEM SHALL** 추출 과정을 상세히 로깅해야 한다.

**세부 요구사항**:
- **AC-3.1**: 감지된 Chapter 패턴 로깅 ("Chapter 01 감지")
- **AC-3.2**: 추출된 토픽 제목 로깅
- **AC-3.3**: 카테고리 분류 결과 로깅
- **AC-3.4**: 추출 실패 시 원인 로깅

### REQ-4: 호환성 유지

**WHEN** 시스템이 Chapter 기반 추출을 구현하면,
**THE SYSTEM SHALL** 기존 `extract_topics_from_pdf_page3()` 함수와의 호환성을 유지해야 한다.

**세부 요구사항**:
- **AC-4.1**: 동일한 반환 형식 유지 (Dict[str, List[str]])
- **AC-4.2**: 함수명 유지 또는 별칭(alias) 제공
- **AC-4.3**: 기존 호출 코드 수정 최소화

### REQ-5: 하지 않아야 할 동작 (Unwanted)

**IF** 추출된 텍스트가 다음 조건 중 하나를 만족하면,
**THE SYSTEM SHALL NOT** 해당 텍스트를 토픽으로 간주해야 한다:

- **AC-5.1**: 길이가 10자 미만인 경우
- **AC-5.2**: 숫자로만 구성된 경우 (예: "01", "123")
- **AC-5.3**: Chapter 패턴 자체인 경우 (예: "Chapter 01")
- **AC-5.4**: 페이지 번호로만 구성된 경우 (예: "3", "p.3")

---

## 4. 기술 사양

### 4.1 Chapter 패턴 정규표현식

```regex
^Chapter\s+(\d+)
```

**설명**:
- `^`: 줄 시작
- `Chapter`: 리터럴 "Chapter"
- `\s+`: 하나 이상의 공백
- `(\d+)`: 하나 이상의 숫자 (캡처 그룹)

### 4.2 토픽 추출 알고리즘

```python
def extract_topics_from_chapters(pdf_path: str) -> Dict[str, List[str]]:
    """
    PDF 전체 본문에서 Chapter 패턴으로 토픽 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        카테고리별 토픽 딕셔너리
        예: {"기획시리즈": ["주제1", "주제2"], "ICT 신기술": ["주제3"]}
    """
    import fitz  # PyMuPDF
    import re

    doc = fitz.open(pdf_path)
    all_text = ""

    # 모든 페이지 텍스트 추출
    for page in doc:
        all_text += page.get_text()

    doc.close()

    # Chapter 패턴 찾기
    chapter_pattern = re.compile(r'^Chapter\s+(\d+)', re.MULTILINE)
    chapters = chapter_pattern.findall(all_text)

    # 토픽 추출
    lines = all_text.split('\n')
    topics = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Chapter 패턴 감지
        if re.match(r'^Chapter\s+\d+', line):
            # 다음 비어있지 않은 줄 찾기
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                topic = lines[j].strip()
                # 토픽 유효성 검증
                if (10 <= len(topic) <= 100 and
                    not re.match(r'^\d+$', topic) and
                    not re.match(r'^Chapter\s+\d+', topic)):
                    topics.append(topic)

        i += 1

    # 카테고리 매핑
    return map_topics_to_categories(topics)
```

### 4.3 카테고리 매핑 전략

| 토픽 수 | 기획시리즈 | ICT 신기술 |
|--------|-----------|-----------|
| 2개 | 첫 번째 | 두 번째 |
| 3개 | 첫 두 개 | 나머지 |
| 4개 이상 | 절반(반올림) | 나머지 |

---

## 5. 종속성 분석

### 5.1 파일 수정

| 파일 | 변경 내용 |
|------|----------|
| `lambda_itfind_downloader.py` | `extract_topics_from_chapters()` 함수 추가 |
| `lambda_itfind_downloader.py` | `extract_topics_from_pdf_page3()` deprecated 또는 교체 |
| `lambda_itfind_downloader.py` | `download_itfind_pdf()`에서 새 함수 호출로 변경 |

### 5.2 새로운 의존성

없음 (PyMuPDF는 이미 사용 중)

### 5.3 영향 분석

| 컴포넌트 | 영향 | 변경 필요 |
|----------|------|----------|
| `extract_topics_from_pdf_page3()` | 대체됨 | 예 |
| `download_itfind_pdf()` | 호출 변경 | 예 |
| `src/workflow/pdf_workflow.py` | 간접 영향 | 아니오 |

---

## 6. 품질 게이트 (TRUST 5)

### Tested (테스트)
- 5개 테스트 케이스 (2154, 2198, 2199, 2200, 2203호) 모두 통과
- 단위 테스트: Chapter 패턴 감지, 토픽 추출, 카테고리 매핑
- 통합 테스트: 전체 PDF 처리 워크플로우

### Readable (가독성)
- 명확한 함수명: `extract_topics_from_chapters()`
- 상세한 주석: Chapter 패턴, 토픽 추출 로직 설명
- 로깅: 각 단계별 상세 로그

### Unified (통일성)
- 기존 반환 형식과 호환
- PEP 8 스타일 가이드 준수
- 일관된 에러 처리 패턴

### Secured (보안)
- PDF 파일 유효성 검증
- 경로 검증 (LFD 공격 방지)
- 예외 처리로 인젝션 방지

### Trackable (추적 가능성)
- Conventional Commit 메시지
- 상세한 로깅으로 디버깅 지원
- 테스트 케이스로 검증 가능

---

## 7. 추적 정보

**Traceability Tags**:
- SPEC: SPEC-ITFIND-002
- Related: SPEC-ITFIND-001 (기존 page3 추출)
- Test Cases: 2154, 2198, 2199, 2200, 2203호
- Files: lambda_itfind_downloader.py
