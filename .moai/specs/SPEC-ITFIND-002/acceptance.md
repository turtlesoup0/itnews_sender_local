# SPEC-ITFIND-002: 인수 기준

**SPEC ID**: SPEC-ITFIND-002
**Status**: Draft
**Created**: 2026-02-04

---

## 1. 인수 기준 개요

Chapter 패턴 기반 토픽 추출 기능이 5개 테스트 케이스(2154, 2198, 2199, 2200, 2203호)에서 정확하게 작동하는지 검증합니다.

---

## 2. 기능 인수 기준 (Given-When-Then 형식)

### AC-1: Chapter 패턴 감지

**Scenario 1.1: Chapter 패턴이 존재하는 PDF**

```
Given: ITFIND PDF 파일이 존재하고
And: PDF 본문에 "Chapter 01", "Chapter 02" 패턴이 포함되어 있을 때
When: extract_topics_from_chapters() 함수를 호출하면
Then: 모든 Chapter 패턴을 감지해야 한다
And: Chapter 번호를 순서대로 반환해야 한다
```

**Expected Result**:
- Chapter 01, Chapter 02, ..., Chapter NN 패턴 감지
- 감지된 Chapter 수 ≥ 2

---

### AC-2: 토픽 제목 추출

**Scenario 2.1: Chapter 다음 줄에 토픽 제목이 있는 경우**

```
Given: Chapter 패턴을 감지하고
And: Chapter 다음 비어있지 않은 줄에 토픽 제목이 있을 때
When: 토픽 추출 로직을 실행하면
Then: 토픽 제목을 정확히 추출해야 한다
And: 하위 목차는 추출하지 않아야 한다
```

**Expected Result**:
- 토픽 제목 길이: 10-100자
- 하위 목차(짧은 텍스트) 제외됨

**Scenario 2.2: 2203호 (3개 토픽) 경우**

```
Given: 2203호 PDF 파일이 있고
And: 3개의 Chapter (01, 02, 03)가 존재할 때
When: 토픽 추출을 실행하면
Then: 3개의 토픽을 모두 추출해야 한다
```

**Expected Result**:
- 추출된 토픽 수: 3개
- 토픽1: "AI-Ready 산업 생태계 조성을 위한 구조적 설계"
- 토픽2: "AI 시대의 종합 리스크 관리"
- 토픽3: "우주국방반도체 주요국 정책 동향 분석 및 국내 시사점"

---

### AC-3: 카테고리 매핑

**Scenario 3.1: 2개 토픽 (일반적인 경우)**

```
Given: 추출된 토픽이 2개이고
And: 첫 번째 토픽이 기획시리즈이고
And: 두 번째 토픽이 ICT 신기술일 때
When: 카테고리 매핑을 실행하면
Then: 첫 번째 토픽은 "기획시리즈"로 분류해야 한다
And: 두 번째 토픽은 "ICT 신기술"로 분류해야 한다
```

**Expected Result**:
```python
{
    "기획시리즈": ["주제1"],
    "ICT 신기술": ["주제2"]
}
```

**Scenario 3.2: 3개 토픽 (2203호 특례)**

```
Given: 추출된 토픽이 3개이고
And: 첫 두 토픽이 기획시리즈이고
And: 세 번째 토픽이 ICT 신기술일 때
When: 카테고리 매핑을 실행하면
Then: 첫 두 토픽은 "기획시리즈"로 분류해야 한다
And: 세 번째 토픽은 "ICT 신기술"로 분류해야 한다
```

**Expected Result**:
```python
{
    "기획시리즈": ["AI-Ready 산업 생태계...", "AI 시대의 종합 리스크..."],
    "ICT 신기술": ["우주국방반도체 주요국..."]
}
```

---

### AC-4: 테스트 케이스 검증

**Scenario 4.1: 2154호**

```
Given: 2154호 PDF 파일이 있을 때
When: extract_topics_from_chapters()를 호출하면
Then: 기획시리즈로 "6G 이동통신을 위한 과금정책 및 경제모델 연구 동향"이 추출되어야 한다
And: ICT 신기술로 "공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석"이 추출되어야 한다
```

**Scenario 4.2: 2198호**

```
Given: 2198호 PDF 파일이 있을 때
When: extract_topics_from_chapters()를 호출하면
Then: 기획시리즈로 "AI를 위한 자동화된 데이터 관리 체계의 필요성"이 추출되어야 한다
And: ICT 신기술로 "AI 기술 융합을 통한 전력산업 업무 자동화 전략과 실현 방안"이 추출되어야 한다
```

**Scenario 4.3: 2199호**

```
Given: 2199호 PDF 파일이 있을 때
When: extract_topics_from_chapters()를 호출하면
Then: 기획시리즈로 "건설 분야 AI 학습 데이터셋 구축 사례 및 동향"이 추출되어야 한다
And: ICT 신기술로 "트랜스포머 최적화 기술 연구 동향"이 추출되어야 한다
```

**Scenario 4.4: 2200호**

```
Given: 2200호 PDF 파일이 있을 때
When: extract_topics_from_chapters()를 호출하면
Then: 기획시리즈로 "AI 학습 데이터 신뢰성 확보를 위한 시험평가 기반 접근 방식 동향"이 추출되어야 한다
And: ICT 신기술로 "도시문제 해결을 위한 디지털트윈 활용 방향"이 추출되어야 한다
```

**Scenario 4.5: 2203호 (3개 토픽)**

```
Given: 2203호 PDF 파일이 있을 때
When: extract_topics_from_chapters()를 호출하면
Then: 기획시리즈로 2개 토픽이 추출되어야 한다
And: ICT 신기술로 1개 토픽이 추출되어야 한다
```

**Expected Result for 2203호**:
```python
{
    "기획시리즈": [
        "AI-Ready 산업 생태계 조성을 위한 구조적 설계",
        "AI 시대의 종합 리스크 관리"
    ],
    "ICT 신기술": [
        "우주국방반도체 주요국 정책 동향 분석 및 국내 시사점"
    ]
}
```

---

### AC-5: 하위 목차 필터링

**Scenario 5.1: 하위 목차가 토픽으로 추출되지 않음**

```
Given: Chapter 다음에 하위 목차(짧은 텍스트)가 있을 때
When: 토픽 추출 로직을 실행하면
Then: 하위 목차는 토픽으로 간주하지 않아야 한다
```

**Unwanted Examples** (토픽으로 간주하지 않음):
- "개요"
- "결론"
- "I. 서론"
- "01"
- "123"

---

### AC-6: 에러 처리

**Scenario 6.1: PDF 파일이 없는 경우**

```
Given: 존재하지 않는 PDF 파일 경로일 때
When: extract_topics_from_chapters()를 호출하면
Then: FileNotFoundError 예외를 발생시켜야 한다
```

**Scenario 6.2: PDF 형식이 아닌 경우**

```
Given: PDF 형식이 아닌 파일일 때
When: extract_topics_from_chapters()를 호출하면
Then: ValueError 예외를 발생시켜야 한다
```

**Scenario 6.3: Chapter 패턴이 없는 경우**

```
Given: Chapter 패턴이 없는 PDF일 때
When: extract_topics_from_chapters()를 호출하면
Then: 빈 딕셔너리를 반환해야 한다
And: 경고 로그를 출력해야 한다
```

---

### AC-7: 호환성

**Scenario 7.1: 반환 형식 호환성**

```
Given: extract_topics_from_chapters()를 호출하고
And: 토픽 추출에 성공했을 때
When: 반환값을 확인하면
Then: Dict[str, List[str]] 형식이어야 한다
And: "기획시리즈" 키가 존재해야 한다
And: "ICT 신기술" 키가 존재해야 한다
```

**Expected Result**:
```python
result = extract_topics_from_chapters(pdf_path)
assert isinstance(result, dict)
assert "기획시리즈" in result
assert "ICT 신기술" in result
assert isinstance(result["기획시리즈"], list)
assert isinstance(result["ICT 신기술"], list)
```

---

## 3. 비기능 인수 기준

### NFR-1: 성능

```
Given: 일반적인 ITFIND PDF 파일 (약 5MB)이고
When: extract_topics_from_chapters()를 실행하면
Then: 3초 이내에 추출을 완료해야 한다
```

### NFR-2: 로깅

```
Given: 토픽 추출이 실행 중일 때
When: 각 단계가 진행되면
Then: 다음 로그가 출력되어야 한다
And: "Chapter XX 감지" 로그가 있어야 한다
And: "토픽 추출 완료: N개 카테고리" 로그가 있어야 한다
And: "[기획시리즈] N개 주제" 로그가 있어야 한다
```

### NFR-3: 신뢰성

```
Given: 5개 테스트 케이스 (2154, 2198, 2199, 2200, 2203호)이고
When: 각 테스트 케이스에서 extract_topics_from_chapters()를 실행하면
Then: 모든 테스트 케이스에서 올바른 토픽을 추출해야 한다
And: 정확도는 100%여야 한다
```

---

## 4. Definition of Done

**완료 기준**:

- [ ] 모든 단위 테스트 통과
- [ ] 5개 테스트 케이스 (2154, 2198, 2199, 2200, 2203호) 모두 통과
- [ ] 하위 목차가 토픽으로 추출되지 않음
- [ ] 카테고리 분류가 정확함
- [ ] 에러 처리가 완료됨
- [ ] 로깅이 상세함
- [ ] 기존 기능과 호환성 유지
- [ ] 코드 리뷰 완료
- [ ] 문서화 완료

---

## 5. 검증 방법

### 5.1 자동화된 테스트

```bash
# 단위 테스트
pytest tests/test_chapter_extraction.py -v

# 통합 테스트
pytest tests/test_chapter_extraction_integration.py -v

# 전체 테스트
pytest tests/ -v -k "chapter"
```

### 5.2 수동 테스트

```bash
# 로컬에서 테스트 PDF로 실행
python -c "
from lambda_itfind_downloader import extract_topics_from_chapters
result = extract_topics_from_chapters('/path/to/test.pdf')
print(result)
"
```

### 5.3 검증 체크리스트

| 항목 | 검증 방법 | 기대 결과 |
|------|----------|----------|
| Chapter 패턴 감지 | 단위 테스트 | 모든 Chapter 감지 |
| 토픽 추출 정확도 | 5개 테스트 케이스 | 100% 정확도 |
| 하위 목차 필터링 | 부정 테스트 | 하위 목차 제외됨 |
| 카테고리 매핑 | 단위 테스트 | 정확한 분류 |
| 에러 처리 | 예외 테스트 | 적절한 예외 발생 |
| 로깅 | 로그 확인 | 상세한 로그 출력 |
| 성능 | 시간 측정 | 3초 이내 완료 |
| 호환성 | 형식 검증 | Dict[str, List[str]] |

---

## 6. 추적 정보

**Traceability Tags**:
- SPEC: SPEC-ITFIND-002
- Test Cases: 2154, 2198, 2199, 2200, 2203
- Related: SPEC-ITFIND-001
- Files: lambda_itfind_downloader.py
- Tests: tests/test_chapter_extraction.py
