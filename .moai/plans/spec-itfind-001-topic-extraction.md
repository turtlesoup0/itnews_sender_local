# SPEC-ITFIND-001: 구조 인식 기반 토픽 추출 계획

## 문제 정의

현재 `extract_topics_from_pdf_page3()` 함수는 규칙 기반 필터링을 사용하여 토픽을 추출합니다:

```python
line not in ['서론', '결론', '개요', '기대효과', '국내외 동향', '데이터 파이프라인이란?']
```

이 방식은 저자마다 글의 내용이 다르기 때문에 신뢰할 수 없습니다.

## PDF 구조 분석

사용자가 확인한 PDF 3페이지 구조:

```
Topic (20+ chars)    ← 주제 제목
Author (_ pattern)    ← 저자 정보 (김OO_기관)
Contents (short + page) ← 목차
...
Topic (20+ chars)    ← 다음 주제
Author (_ pattern)
Contents (short + page)
```

## 구조 인식 기반 상태 머신 설계

### 상태 정의

1. **WAITING_FOR_CATEGORY**: 카테고리("기획시리즈:", "ICT 신기술") 대기 중
2. **WAITING_FOR_TOPIC**: 첫 번째 주제 대기 중
3. **IN_TOPIC**: 주제 감지됨, 저자 대기 중
4. **IN_AUTHOR**: 저자 감지됨, 목차 대기 중
5. **IN_CONTENTS**: 목차 진행 중, 페이지 번호로 종료 대기

### 패턴 정의

| 상태 전환 | 패턴 | 조건 |
|-----------|------|------|
| → WAITING_FOR_TOPIC | `기획시리즈:`, `ICT 신기술` | 카테고리 키워드 |
| → IN_TOPIC | 긴 텍스트 (20-100자) | `_` 패턴 없음, 숫자만 아님 |
| → IN_AUTHOR | `_한글` 패턴 | `_\s*[가-힣]+` |
| → IN_CONTENTS | 짧은 텍스트 (<30자) 또는 저자 패턴 | 목차 진행 |
| → WAITING_FOR_TOPIC | 숫자만 | 페이지 번호로 목차 종료 |

### 핵심 알고리즘

```python
# 상태 머신 기반 토픽 추출
states = ['WAITING_CATEGORY', 'WAITING_TOPIC', 'IN_TOPIC', 'IN_AUTHOR', 'IN_CONTENTS']
state = states[0]
current_category = None
result = {}

for line in lines:
    line = line.strip()

    # 1. 카테고리 감지
    if line in ['기획시리즈:', 'ICT 신기술', '연구보고서:', '정책:']:
        current_category = line.rstrip(':')
        result[current_category] = []
        state = 'WAITING_TOPIC'
        continue

    # 2. 주제 감지 (긴 텍스트, 저자 패턴 없음)
    if state == 'WAITING_TOPIC':
        if 20 < len(line) < 100 and not re.search(r'_\s*[가-힣]', line):
            result[current_category].append(line)
            state = 'IN_AUTHOR'
            continue

    # 3. 저자 감지
    if state == 'IN_AUTHOR':
        if re.search(r'_\s*[가-힣]+', line):
            state = 'IN_CONTENTS'
            continue

    # 4. 목차 진행 중
    if state == 'IN_CONTENTS':
        # 페이지 번호만 = 목차 종료, 다음 주제 대기
        if re.match(r'^\d+$', line):
            state = 'WAITING_TOPIC'
```

## 수정할 파일

**`lambda_itfind_downloader.py`** (lines 213-332)
- `extract_topics_from_pdf_page3()` 함수 전면 재작성
- 상태 머신 구현
- 규칙 기반 필터링 (`line not in [...]`) 제거

## 검증 계획

사용자가 제공한 테스트 케이스:

| 호수 | 예상 토픽 수 | 카테고리 |
|------|-------------|----------|
| 2154 | 2개 | 기획시리즈, ICT 신기술 |
| 2198 | 2개 | 기획시리즈, ICT 신기술 |
| 2199 | 2개 | 기획시리즈, ICT 신기술 |
| 2200 | 2개 | 기획시리즈, ICT 신기술 |
| 2203 | 3개 | 기획시리즈 (2개), ICT 신기술 (1개) |

## 구현 단계

1. **Phase 1**: `extract_topics_from_pdf_page3()` 함수를 상태 머신으로 재작성
2. **Phase 2**: 5개 테스트 케이스로 검증
3. **Phase 3**: 로깅 추가 (상태 전환 추적)
4. **Phase 4**: 커밋 및 푸시
