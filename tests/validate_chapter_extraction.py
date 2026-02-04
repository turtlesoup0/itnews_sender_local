"""
Chapter 기반 토픽 추출 실제 PDF 검증

5개 테스트 케이스 (2154, 2198, 2199, 2200, 2203호)로 검증
"""
import sys
import os
from pathlib import Path

# 프로젝트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from lambda_itfind_downloader import extract_topics_from_chapters, download_pdf_direct


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
        "ICT 신기술": ["우 space 국방반도체 주요국 정책 동향 분석 및 국내 시사점"],
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

            # 일치 여부 확인
            match = True
            for category in ["기획시리즈", "ICT 신기술"]:
                if extracted.get(category, []) != expected.get(category, []):
                    match = False
                    print(f"\n❌ {category} 불일치!")
                    print(f"   추출: {extracted.get(category, [])}")
                    print(f"   예상: {expected.get(category, [])}")

            if match:
                print(f"\n✅ {issue_num}호: PASSED")
                results[issue_num] = "PASSED"
            else:
                print(f"\n❌ {issue_num}호: FAILED")
                results[issue_num] = "FAILED"

            # 임시 파일 삭제
            os.remove(pdf_path)

        else:
            print(f"❌ PDF 다운로드 실패")
            results[issue_num] = "DOWNLOAD_FAILED"

    # 최종 요약
    print(f"\n\n{'='*60}")
    print(f"최종 결과 요약")
    print(f"{'='*60}")
    for issue_num, result in results.items():
        status_icon = "✅" if result == "PASSED" else "❌"
        print(f"{status_icon} {issue_num}호: {result}")

    passed = sum(1 for r in results.values() if r == "PASSED")
    total = len(results)
    print(f"\n통과: {passed}/{total}")

    return results


if __name__ == "__main__":
    test_all_cases()
