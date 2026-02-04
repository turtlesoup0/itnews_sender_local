"""
ITFIND 웹사이트에서 최신 PDF로 Chapter 추출 테스트
"""
import sys
import os
import re
import requests
from pathlib import Path

# PyMuPDF import
try:
    import fitz
except ImportError:
    print("PyMuPDF (fitz)가 설치되지 않았습니다.")
    sys.exit(1)


def get_latest_streamdocs_id():
    """ITFIND 웹사이트에서 최신 streamdocs_id 추출"""
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    try:
        # 1. 메인 페이지 접근 (쿠키 획득)
        print("   메인 페이지 접근 중...")
        response = session.get("https://www.itfind.or.kr/", headers=headers, timeout=30)
        response.raise_for_status()

        # 2. 주간기술동향 목록 페이지 접근
        print("   주간기술동향 목록 접근 중...")
        list_url = "https://www.itfind.or.kr/Library/List.do?searchType=6&menuCd=MEM050401"
        response = session.get(list_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 3. 최신 항목의 detail_id 추출
        # 패턴: javascript:goDetail('12345')
        match = re.search(r"javascript:goDetail\('(\d+)'\)", response.text)
        if not match:
            print("   ❌ detail_id를 찾을 수 없습니다")
            return None

        detail_id = match.group(1)
        print(f"   ✅ detail_id: {detail_id}")

        # 4. detail 페이지 접근
        print("   상세 페이지 접근 중...")
        detail_url = f"https://www.itfind.or.kr/library/Detail.do?={detail_id}"
        response = session.get(detail_url, headers=headers, timeout=30)
        response.raise_for_status()

        # 제목 추출
        title_match = re.search(r'<title>([^<]+)</title>', response.text)
        if title_match:
            print(f"   제목: {title_match.group(1).strip()}")

        # 5. StreamDocs Regi API 호출
        print("   StreamDocs 정보 요청 중...")
        regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
        response = session.get(regi_url, headers=headers, timeout=30, allow_redirects=True)

        # 6. streamdocs_id 추출 (redirect URL 또는 HTML)
        streamdocs_id = None

        # 방법 1: redirect URL
        if 'streamdocsId=' in response.url:
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response.url)
            if match:
                streamdocs_id = match.group(1)

        # 방법 2: HTML 본문
        if not streamdocs_id:
            match = re.search(r'streamdocsId["\s]*[:=]["\s]*([A-Za-z0-9_-]+)', response.text)
            if match:
                streamdocs_id = match.group(1)

        if streamdocs_id:
            print(f"   ✅ streamdocs_id: {streamdocs_id}")
            return streamdocs_id
        else:
            print("   ❌ streamdocs_id를 찾을 수 없습니다")
            return None

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return None


def download_pdf(streamdocs_id: str, save_path: str) -> bool:
    """PDF 다운로드"""
    url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/pdf,*/*',
        'Referer': 'https://www.itfind.or.kr/'
    }

    print(f"   PDF 다운로드 중...")

    try:
        response = requests.get(url, headers=headers, timeout=60, stream=True)

        # 첫 청크로 PDF 확인
        first_chunk = next(response.iter_content(5), b'')
        if first_chunk[:5] != b'%PDF-':
            print(f"   ❌ PDF 시그니처 없음: {first_chunk[:20]}")
            return False

        # 저장
        with open(save_path, 'wb') as f:
            f.write(first_chunk)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(save_path)
        print(f"   ✅ 다운로드 완료: {file_size:,} bytes")
        return True

    except Exception as e:
        print(f"   ❌ 다운로드 실패: {e}")
        return False


def extract_topics_from_chapters(pdf_path: str):
    """Chapter 기반 토픽 추출"""
    print(f"\n   PDF 분석 중...")

    doc = fitz.open(pdf_path)

    # 전체 텍스트 추출
    full_text = ""
    for page in doc:
        text = page.get_text()
        full_text += text + "\n"

    doc.close()

    # 라인 단위 분리
    lines = full_text.split('\n')

    # Chapter 패턴 탐지
    chapter_indices = []
    for i, line in enumerate(lines):
        line = line.strip()
        if re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):
            chapter_indices.append(i)

    print(f"   감지된 Chapter 수: {len(chapter_indices)}")

    # 각 Chapter 다음 라인에서 토픽 추출
    extracted_topics = []
    for chapter_idx in chapter_indices:
        for j in range(chapter_idx + 1, min(chapter_idx + 10, len(lines))):
            next_line = lines[j].strip()

            if not next_line:
                continue

            # 필터링
            if len(next_line) < 10 or len(next_line) > 100:
                continue
            if re.match(r'^\d+$', next_line):
                continue
            if re.match(r'^Chapter\s+\d+', next_line, re.IGNORECASE):
                continue
            if re.match(r'^\d+\s*\-\s*\d+$', next_line):
                continue

            extracted_topics.append(next_line)
            print(f"   Chapter {len(extracted_topics)}: {next_line[:60]}...")
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


def _map_topics_to_categories(topics):
    """토픽을 카테고리로 매핑"""
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
        mid = (n + 1) // 2
        result['기획시리즈'] = topics[:mid]
        result['ICT 신기술'] = topics[mid:]

    return result


def main():
    """메인 실행"""
    print("="*60)
    print("ITFIND 최신 호 Chapter 추출 테스트")
    print("="*60)

    # 1. streamdocs_id 획득
    print("\n1. 최신 정보 수집 중...")
    streamdocs_id = get_latest_streamdocs_id()
    if not streamdocs_id:
        print("\n❌ streamdocs_id를 가져올 수 없습니다")
        return

    # 2. PDF 다운로드
    pdf_path = "/tmp/itfind_test.pdf"
    print(f"\n2. PDF 다운로드 중...")
    if not download_pdf(streamdocs_id, pdf_path):
        return

    # 3. 토픽 추출
    print(f"\n3. 토픽 추출 중...")
    result = extract_topics_from_chapters(pdf_path)

    # 4. 결과 출력
    print(f"\n4. 최종 결과:")
    print("="*60)
    for category, topics in result.items():
        print(f"\n[{category}] ({len(topics)}개):")
        for i, topic in enumerate(topics, 1):
            print(f"  {i}. {topic}")

    # 5. 정리
    try:
        os.remove(pdf_path)
    except:
        pass

    print("\n" + "="*60)
    print("✅ 테스트 완료")
    print("="*60)


if __name__ == "__main__":
    main()
