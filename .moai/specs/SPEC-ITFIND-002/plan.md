# SPEC-ITFIND-002: 구현 계획

**SPEC ID**: SPEC-ITFIND-002
**Status**: Draft
**Created**: 2026-02-04

---

## 1. 구현 개요

Chapter 패턴 기반 토픽 추출 기능을 구현하여 기존 page3 목차 추출 방식의 신뢰성 문제를 해결합니다.

---

## 2. 구현 단계 (우선순위별)

### Phase 1: 핵심 기능 구현 (Priority High)

**목표**: Chapter 패턴 기반 토픽 추출 함수 구현

**작업**:
1. `extract_topics_from_chapters()` 함수 생성
2. Chapter 패턴 정규표현식 구현
3. 토픽 제목 추출 로직 구현
4. 카테고리 매핑 함수 구현

**파일**: `lambda_itfind_downloader.py`

**검증**:
- 단위 테스트: Chapter 패턴 감지
- 단위 테스트: 토픽 추출
- 단위 테스트: 카테고리 매핑

### Phase 2: 기존 코드와 통합 (Priority High)

**목표**: `download_itfind_pdf()` 함수에서 새로운 추출 방식 사용

**작업**:
1. `download_itfind_pdf()`에서 `extract_topics_from_pdf_page3()` 호출 제거
2. `extract_topics_from_chapters()` 호출로 변경
3. 반환 형식 호환성 확인

**파일**: `lambda_itfind_downloader.py`

**검증**:
- 통합 테스트: 전체 PDF 다운로드 및 토픽 추출
- 호환성 테스트: 기존 반환 형식 유지

### Phase 3: 로깅 및 에러 처리 (Priority Medium)

**목표**: 상세한 로깅과 견고한 에러 처리

**작업**:
1. Chapter 감지 로깅 추가
2. 토픽 추출 로깅 추가
3. 카테고리 분류 로깅 추가
4. 에러 발생 시 fallback 메커니즘

**파일**: `lambda_itfind_downloader.py`

**검증**:
- 로그 확인 테스트
- 에러 시나리오 테스트

### Phase 4: 레거시 코드 정리 (Priority Low)

**목표**: 불필요한 코드 제거 및 문서화

**작업**:
1. `extract_topics_from_pdf_page3()` 함수 deprecated 표시
2. 함수별 docstring 추가
3. README 업데이트 (필요 시)

**파일**: `lambda_itfind_downloader.py`, README.md

**검증**:
- 코드 리뷰
- 문서 검증

---

## 3. 기술 접근 방식

### 3.1 Chapter 패턴 감지

**정규표현식**:
```python
import re

CHAPTER_PATTERN = re.compile(r'^Chapter\s+(\d+)', re.MULTILINE)
```

**감지 로직**:
1. PDF 전체 텍스트 추출 (PyMuPDF)
2. Chapter 패턴으로 모든 일치 항목 찾기
3. Chapter 번호 순서 확인

### 3.2 토픽 제목 추출

**알고리즘**:
```
For each Chapter pattern found:
    1. Find next non-empty line after Chapter
    2. Validate topic (length 10-100, not digits only)
    3. Add to topics list
    4. Skip next few lines (to avoid sub-items)
```

**하위 목차 필터링**:
- 길이 < 10자: 제외
- 숫자로만 구성: 제외
- Chapter 패턴 포함: 제외

### 3.3 카테고리 매핑

**전략**:
```python
def map_topics_to_categories(topics: List[str]) -> Dict[str, List[str]]:
    """
    토픽 리스트를 카테고리로 매핑

    규칙:
    - 2개 토픽: [0] -> 기획시리즈, [1] -> ICT 신기술
    - 3개 토픽: [0:2] -> 기획시리즈, [2:] -> ICT 신기술
    - 4개 이상: 절반 -> 기획시리즈, 나머지 -> ICT 신기술
    """
    result = {"기획시리즈": [], "ICT 신기술": []}

    if len(topics) == 2:
        result["기획시리즈"] = [topics[0]]
        result["ICT 신기술"] = [topics[1]]
    elif len(topics) == 3:
        result["기획시리즈"] = topics[:2]
        result["ICT 신기술"] = topics[2:]
    elif len(topics) >= 4:
        mid = (len(topics) + 1) // 2
        result["기획시리즈"] = topics[:mid]
        result["ICT 신기술"] = topics[mid:]

    return result
```

### 3.4 호환성 유지

**반환 형식**:
```python
Dict[str, List[str]]
# 예: {"기획시리즈": ["주제1"], "ICT 신기술": ["주제2"]}
```

**함수 시그니처**:
```python
def extract_topics_from_chapters(pdf_path: str) -> Dict[str, List[str]]:
    """
    PDF 전체 본문에서 Chapter 패턴으로 토픽 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        카테고리별 토픽 딕셔너리
        예: {"기획시리즈": ["주제1"], "ICT 신기술": ["주제2"]}

    Raises:
        FileNotFoundError: PDF 파일이 없는 경우
        ValueError: PDF 형식이 아닌 경우
    """
```

---

## 4. 위험 및 완화 계획

### 4.1 Chapter 패턴 미발견

**위험**: 일부 PDF에서 Chapter 패턴이 다른 형식을 사용할 수 있음

**완화**:
- 정규표현식에 여러 변형 추가 (예: "CHAPTER 01", "chapter 01")
- 패턴 미발견 시 기존 page3 추출 방식으로 fallback

### 4.2 하위 목차 오류 추출

**위험**: Chapter 바로 다음 줄이 하위 목차일 수 있음

**완화**:
- 토픽 길이 검증 (10자 이상)
- 키워드 필터링 (예: "개요", "결론" 제외)
- 다음 줄 확인 로직

### 4.3 카테고리 분류 오류

**위험**: 토픽 순서가 기대와 다를 수 있음

**완화**:
- 테스트 케이스로 검증
- 필요 시 키워드 기반 분류 추가

---

## 5. 파일 수정 계획

### 5.1 `lambda_itfind_downloader.py`

**추가**:
```python
def extract_topics_from_chapters(pdf_path: str) -> Dict[str, List[str]]:
    """Chapter 패턴 기반 토픽 추출 (새로운 방식)"""
    # ... 구현 ...

def map_topics_to_categories(topics: List[str]) -> Dict[str, List[str]]:
    """토픽 리스트를 카테고리로 매핑"""
    # ... 구현 ...
```

**수정**:
```python
# download_itfind_pdf() 함수에서
# 기존: categorized_topics = extract_topics_from_pdf_page3(local_path)
# 변경: categorized_topics = extract_topics_from_chapters(local_path)
```

**Deprecated**:
```python
def extract_topics_from_pdf_page3(pdf_path: str) -> Dict[str, List[str]]:
    """
    PDF 3페이지(목차)에서 카테고리별 토픽 추출

    .. deprecated::
        Chapter 기반 추출 방식으로 대체되었습니다.
        extract_topics_from_chapters()를 사용하세요.
    """
    # ... 기존 구현 ...
```

---

## 6. 검증 계획

### 6.1 단위 테스트

**파일**: `tests/test_chapter_extraction.py`

```python
import pytest
from lambda_itfind_downloader import extract_topics_from_chapters, map_topics_to_categories

def test_chapter_pattern_detection():
    """Chapter 패턴 감지 테스트"""
    # Given
    text = "Chapter 01\n주제1\n\nChapter 02\n주제2"

    # When
    import re
    pattern = re.compile(r'^Chapter\s+(\d+)', re.MULTILINE)
    matches = pattern.findall(text)

    # Then
    assert len(matches) == 2
    assert matches == ['01', '02']

def test_topic_extraction():
    """토픽 추출 테스트"""
    # Given: PDF 경로
    pdf_path = "/path/to/test.pdf"

    # When
    result = extract_topics_from_chapters(pdf_path)

    # Then
    assert "기획시리즈" in result
    assert "ICT 신기술" in result

def test_category_mapping():
    """카테고리 매핑 테스트"""
    # Given
    topics = ["주제1", "주제2", "주제3"]

    # When
    result = map_topics_to_categories(topics)

    # Then
    assert len(result["기획시리즈"]) == 2
    assert len(result["ICT 신기술"]) == 1
```

### 6.2 통합 테스트

**파일**: `tests/test_chapter_extraction_integration.py`

```python
def test_full_pdf_workflow():
    """전체 PDF 처리 워크플로우 테스트"""
    # Given: 테스트 PDF 파일 (2154호)
    pdf_path = "/data/itfind_2154.pdf"

    # When
    result = extract_topics_from_chapters(pdf_path)

    # Then: 기대 토픽 확인
    assert "6G 이동통신을 위한 과금정책" in result["기획시리즈"][0]
    assert "공간 확장을 위한 차세대 통신" in result["ICT 신기술"][0]
```

### 6.3 테스트 케이스 검증

| 호수 | 기대 결과 | 검증 방법 |
|------|----------|----------|
| 2154 | 기획시리즈: 6G 이동통신..., ICT: 공간 확장... | pytest |
| 2198 | 기획시리즈: AI를 위한 자동화..., ICT: AI 기술 융합... | pytest |
| 2199 | 기획시리즈: 건설 분야 AI..., ICT: 트랜스포머 최적화... | pytest |
| 2200 | 기획시리즈: AI 학습 데이터..., ICT: 도시문제 해결... | pytest |
| 2203 | 기획시리즈: 2개, ICT: 1개 | pytest |

---

## 7. 배포 계획

### 7.1 로컬 테스트

```bash
# 1. 단위 테스트 실행
pytest tests/test_chapter_extraction.py -v

# 2. 통합 테스트 실행
pytest tests/test_chapter_extraction_integration.py -v

# 3. 수동 테스트
python lambda_itfind_downloader.py
```

### 7.2 배포 체크리스트

- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과
- [ ] 5개 테스트 케이스 모두 통과
- [ ] 로깅 확인
- [ ] 에러 처리 확인
- [ ] 기존 기능 영향 없음 확인

### 7.3 롤백 계획

**문제 발생 시**:
1. `extract_topics_from_chapters()` 호출 제거
2. `extract_topics_from_pdf_page3()` 복원
3. git revert로 코드 롤백

---

## 8. 추적 정보

**Traceability Tags**:
- SPEC: SPEC-ITFIND-002
- Related: SPEC-ITFIND-001
- Files: lambda_itfind_downloader.py
- Tests: tests/test_chapter_extraction.py
