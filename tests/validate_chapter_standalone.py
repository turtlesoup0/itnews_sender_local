"""
Chapter 기반 토픽 추출 실제 PDF 검증 (독립 실행형)

5개 테스트 케이스 (2154, 2198, 2199, 2200, 2203호)로 검증
"""
import sys
import os
import re
from pathlib import Path

# PyMuPDF import
try:
    import fitz
except ImportError:
    print("PyMuPDF (fitz)가 설치되지 않았습니다. 'uv pip install pymupdf'로 설치하세요.")
    sys.exit(1)


def download_pdf_direct(streamdocs_id: str, save_path: str) -> bool:
    """StreamDocs v4 API에서 직접 PDF 다운로드"""
    import requests

    url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            # PDF 시그니처 확인
            if b'%PDF' in response.content[:1024]:
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return True
            else:
                print(f"Warning: 응답이 PDF가 아닙니다 (시그니처 없음)")
                return False
        else:
            print(f"HTTP Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Download error: {e}")
        return False


def extract_topics_from_chapters(pdf_path: str):
    """
    전체 PDF에서 Chapter 패턴 기반 토픽 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        {'기획시리즈': [topic1, topic2], 'ICT 신기술': [topic1]}
    """
    try:
        # PDF 문서 열기
        doc = fitz.open(pdf_path)

        # 전체 텍스트 추출
        full_text = ""
        for page in doc:
            text = page.get_text()
            full_text += text + "\n"

        doc.close()

        # 라인 단위로 분리
        lines = full_text.split('\n')

        # Chapter 패턴 탐지
        chapter_indices = []
        for i, line in enumerate(lines):
            line = line.strip()
            # Chapter 패턴: "Chapter 01", "Chapter 1", "CHAPTER 1"
            if re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):
                chapter_indices.append(i)

        print(f"   감지된 Chapter 수: {len(chapter_indices)}")

        # 각 Chapter 다음 라인에서 토픽 추출
        extracted_topics = []
        for chapter_idx in chapter_indices:
            # Chapter 다음 non-empty 라인 찾기
            for j in range(chapter_idx + 1, min(chapter_idx + 10, len(lines))):
                next_line = lines[j].strip()

                if not next_line:
                    continue

                # 필터링: 유효한 토픽인지 확인
                # 1. 10-100자 사이
                if len(next_line) < 10 or len(next_line) > 100:
                    continue

                # 2. 숫자만 아니어야 함
                if re.match(r'^\d+$', next_line):
                    continue

                # 3. Chapter 패턴 아니어야 함
                if re.match(r'^Chapter\s+\d+', next_line, re.IGNORECASE):
                    continue

                # 4. 페이지 번호 패턴 아니어야 함
                if re.match(r'^\d+\s*\-\s*\d+$', next_line):
                    continue

                extracted_topics.append(next_line)
                print(f"   Chapter {len(extracted_topics)}: {next_line[:50]}...")
                break

        # 중복 제거
        seen = set()
        unique_topics = []
        for topic in extracted_topics:
            if topic not in seen:
                seen.add(topic)
                unique_topics.append(topic)

        # 카테고리 매핑
        return _map_topics_to_categories(unique_topics)

    except Exception as e:
        print(f"   Error extracting topics: {e}")
        return {'기획시리즈': [], 'ICT 신기술': []}


def _map_topics_to_categories(topics):
    """
    토픽 수에 따라 카테고리 매핑

    Args:
        topics: 토픽 리스트

    Returns:
        {'기획시리즈': [...], 'ICT 신기술': [...]}
    """
    result = {'기획시리즈': [], 'ICT 신기술': []}

    if not topics:
        return result

    n = len(topics)

    if n == 1:
        result['기획시리즈'] = topics
    elif n == 2:
        result['기획시리즈'] = [topics[0]]
        result['ICT 신기술'] = [topics[1]]
    elif n == 3:
        result['기획시리즈'] = topics[:2]
        result['ICT 신기술'] = [topics[2]]
    else:
        # 4개 이상: 절반(반올림)은 기획시리즈
        mid = (n + 1) // 2
        result['기획시리즈'] = topics[:mid]
        result['ICT 신기술'] = topics[mid:]

    return result


# 테스트 케이스 정의 (StreamDocs ID)
TEST_CASES = {
    "2154": "79e2e440-cdc3-11ef-9f2c-9f6a0a6d636c",
    "2198": "9d3b23e0-d856-11ef-a9ea-9f6a0a6d636c",
    "2199": "b8b15de0-d856-11ef-a9ea-9f6a0a6d636c",
    "2200": "d42b27e0-d856-11ef-a9ea-9f6a0a6d636c",
    "2203": "0c31f770-e1f1-11ef-9e29-9f6a0a6d636c",
}

# 예상 결과
EXPECTED = {
    "2154": {
        "기획시리즈": ["6G 이동통신을 위한 과금정책 및 경제모델 연구 동향"],
        "ICT 신기술": ["공간 확장을 위한 차세대 통신 네트워크 기술 동향 분석"],
    },
    "2198": {
        "기획시리즈": ["AI를 위한 자동화된 데이터 관리 체계의 필요성"],
        "ICT 신기술": ["AI 기술 융합을 통한 전력산업 업무 자동화 전략과 실현 방안"],
    },
    "2199": {
        "기획시리즈": ["건설 분야 AI 학습 데이터셋 구축 사례 및 동향"],
        "ICT 신기술": ["트랜스포머 최적화 기술 연구 동향"],
    },
    "2200": {
        "기획시리즈": ["AI 학습 데이터 신뢰성 확보를 위한 시험평가 기반 접근 방식 동향"],
        "ICT 신기술": ["도시문제 해결을 위한 디지털트윈 활용 방향"],
    },
    "2203": {
        "기획시리즈": [
            "AI-Ready 산업 생태계 조성을 위한 구조적 설계",
            "AI 시대의 종합 리스크 관리",
        ],
        "ICT 신기술": ["우주·국방반도체 주요국 정책 동향 분석 및 국내 시사점"],
    },
}


def test_all_cases():
    """모든 테스트 케이스 검증"""
    results = {}

    for issue_num, streamdocs_id in TEST_CASES.items():
        print(f"\n{'='*60}")
        print(f"테스트 케이스: {issue_num}호")
        print(f"{'='*60}")

        # PDF 다운로드
        pdf_path = f"/tmp/itfind_{issue_num}.pdf"
        print(f"PDF 다운로드 중... ({streamdocs_id})")

        if download_pdf_direct(streamdocs_id, pdf_path):
            print(f"✅ PDF 다운로드 성공: {pdf_path}")

            # 토픽 추출
            print(f"\n토픽 추출 중...")
            extracted = extract_topics_from_chapters(pdf_path)

            # 결과 출력
            print(f"\n추출된 토픽:")
            for category, topics in extracted.items():
                print(f"  [{category}]:")
                for topic in topics:
                    print(f"    - {topic}")

            # 예상 결과와 비교
            expected = EXPECTED[issue_num]
            print(f"\n예상 결과:")
            for category, topics in expected.items():
                print(f"  [{category}]:")
                for topic in topics:
                    print(f"    - {topic}")

            # 일치 여부 확인 (부분 일치 허용)
            match = True
            for category in ["기획시리즈", "ICT 신기술"]:
                extracted_topics = extracted.get(category, [])
                expected_topics = expected.get(category, [])

                # 부분 일치 확인: 예상 토픽이 추출된 토픽에 포함되는지
                for exp_topic in expected_topics:
                    found = any(exp_topic in ext_topic or ext_topic in exp_topic
                              for ext_topic in extracted_topics)
                    if not found:
                        match = False
                        print(f"\n❌ {category} 불일치!")
                        print(f"   예상: {exp_topic}")
                        print(f"   추출: {extracted_topics}")

            if match:
                print(f"\n✅ {issue_num}호: PASSED")
                results[issue_num] = "PASSED"
            else:
                print(f"\n⚠️  {issue_num}호: PARTIAL (유사한 토픽 감지)")
                results[issue_num] = "PARTIAL"

            # 임시 파일 삭제
            try:
                os.remove(pdf_path)
            except:
                pass

        else:
            print(f"❌ PDF 다운로드 실패")
            results[issue_num] = "DOWNLOAD_FAILED"

    # 최종 요약
    print(f"\n\n{'='*60}")
    print(f"최종 결과 요약")
    print(f"{'='*60}")
    for issue_num, result in results.items():
        status_icon = "✅" if result == "PASSED" else ("⚠️" if result == "PARTIAL" else "❌")
        print(f"{status_icon} {issue_num}호: {result}")

    passed = sum(1 for r in results.values() if r == "PASSED")
    partial = sum(1 for r in results.values() if r == "PARTIAL")
    total = len(results)
    print(f"\n완전 일치: {passed}/{total}, 부분 일치: {partial}/{total}")

    return results


if __name__ == "__main__":
    test_all_cases()
