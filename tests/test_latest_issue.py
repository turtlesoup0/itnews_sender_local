"""
최신 ITFIND 주간기술동향으로 Chapter 추출 테스트
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


def get_latest_trend_from_rss():
    """RSS에서 최신 주간기술동향 정보 가져오기"""
    rss_url = "https://www.itfind.or.kr/Library/Search/rss.do?typeCd=31&viewType=T"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    response = requests.get(rss_url, headers=headers, timeout=30)
    response.raise_for_status()

    # RSS 파싱
    import xml.etree.ElementTree as ET
    root = ET.fromstring(response.content)

    # 첫 번째 아이템 (최신)
    item = root.find('.//item')

    title = item.find('title').text
    link = item.find('link').text

    # 호수 추출 (예: "제2154호" -> "2154")
    match = re.search(r'제(\d+)호', title)
    issue_number = match.group(1) if match else "unknown"

    return {
        'title': title,
        'link': link,
        'issue_number': issue_number
    }


def get_streamdocs_id(detail_id: str) -> str:
    """detail 페이지에서 streamdocs_id 추출"""
    import requests

    session = requests.Session()

    # 1. detail 페이지 접근
    detail_url = f"https://www.itfind.or.kr/library/Detail.do?={detail_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    response = session.get(detail_url, headers=headers, timeout=30)

    # 2. StreamDocs Regi 페이지 접근
    streamdocs_regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"

    response2 = session.get(streamdocs_regi_url, headers=headers, timeout=30, allow_redirects=True)

    # 3. redirect URL에서 streamdocs_id 추출
    if 'streamdocsId=' in response2.url:
        match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.url)
        if match:
            return match.group(1)

    # 4. HTML 본문에서 추출
    match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.text)
    if match:
        return match.group(1)

    return None


def download_pdf(streamdocs_id: str, save_path: str) -> bool:
    """PDF 다운로드"""
    url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/pdf,*/*',
        'Referer': 'https://www.itfind.or.kr/'
    }

    response = requests.get(url, headers=headers, timeout=60, stream=True)

    # 첫 청크로 PDF 확인
    first_chunk = next(response.iter_content(5), b'')
    if first_chunk[:5] != b'%PDF-':
        return False

    # 저장
    with open(save_path, 'wb') as f:
        f.write(first_chunk)
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return True


def extract_topics_from_chapters(pdf_path: str):
    """Chapter 기반 토픽 추출"""
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

    print(f"\n   감지된 Chapter 수: {len(chapter_indices)}")

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
            print(f"   Chapter {len(extracted_topics)}: {next_line}")
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
    print("최신 ITFIND 주간기술동향 Chapter 추출 테스트")
    print("="*60)

    # 1. RSS에서 최신 정보 가져오기
    print("\n1. RSS에서 최신 정보 가져오는 중...")
    trend = get_latest_trend_from_rss()
    print(f"   제목: {trend['title']}")
    print(f"   호수: {trend['issue_number']}")
    print(f"   링크: {trend['link']}")

    # 2. detail_id 추출
    match = re.search(r'=(\d+)', trend['link'])
    if not match:
        print("   ❌ detail_id를 추출할 수 없습니다")
        return

    detail_id = match.group(1)
    print(f"\n2. detail_id: {detail_id}")

    # 3. streamdocs_id 추출
    print(f"\n3. streamdocs_id 추출 중...")
    streamdocs_id = get_streamdocs_id(detail_id)
    if not streamdocs_id:
        print("   ❌ streamdocs_id를 추출할 수 없습니다")
        return

    print(f"   ✅ streamdocs_id: {streamdocs_id}")

    # 4. PDF 다운로드
    pdf_path = f"/tmp/itfind_latest.pdf"
    print(f"\n4. PDF 다운로드 중...")
    if not download_pdf(streamdocs_id, pdf_path):
        print("   ❌ PDF 다운로드 실패")
        return

    file_size = os.path.getsize(pdf_path)
    print(f"   ✅ PDF 다운로드 성공: {file_size:,} bytes")

    # 5. 토픽 추출
    print(f"\n5. Chapter 기반 토픽 추출 중...")
    result = extract_topics_from_chapters(pdf_path)

    # 6. 결과 출력
    print(f"\n6. 추출 결과:")
    print("="*60)
    for category, topics in result.items():
        print(f"\n[{category}]:")
        for i, topic in enumerate(topics, 1):
            print(f"  {i}. {topic}")

    # 7. 임시 파일 삭제
    os.remove(pdf_path)

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    main()
