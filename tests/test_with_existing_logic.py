"""
기존 itfind 로직으로 PDF 다운로드 후 Chapter 추출 테스트
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


def extract_streamdocs_id_from_detail_page(detail_id: str):
    """
    detail 페이지에서 streamdocs_id 추출 (lambda_itfind_downloader.py의 로직 활용)
    """
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
    }

    try:
        # 1. detail 페이지 접근
        detail_url = f"https://www.itfind.or.kr/library/Detail.do?={detail_id}"
        print(f"   detail 페이지 접근: {detail_url}")

        response = session.get(detail_url, headers=headers, timeout=30)

        # 2. StreamDocs Regi 페이지 접근
        streamdocs_regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
        print(f"   StreamDocs Regi 페이지 접근...")

        response2 = session.get(streamdocs_regi_url, headers=headers, timeout=30, allow_redirects=True)

        # 3. redirect URL에서 streamdocs_id 추출
        streamdocs_id = None

        if 'streamdocsId=' in response2.url:
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.url)
            if match:
                streamdocs_id = match.group(1)
                print(f"   ✅ streamdocs_id 추출 (redirect URL): {streamdocs_id}")
                return streamdocs_id

        # 4. HTML 본문에서 추출
        match = re.search(r'streamdocsId["\s]*[:=]["\s]*([A-Za-z0-9_-]+)', response2.text)
        if match:
            streamdocs_id = match.group(1)
            print(f"   ✅ streamdocs_id 추출 (HTML): {streamdocs_id}")
            return streamdocs_id

        # 5. iframe src에서 추출
        match = re.search(r'<iframe[^>]*src=["\']([^"\']*streamdocs[^"\']*)["\']', response2.text, re.IGNORECASE)
        if match:
            iframe_src = match.group(1)
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', iframe_src)
            if match:
                streamdocs_id = match.group(1)
                print(f"   ✅ streamdocs_id 추출 (iframe): {streamdocs_id}")
                return streamdocs_id

        print(f"   ❌ streamdocs_id를 찾을 수 없습니다")
        return None

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return None


def download_pdf_direct(streamdocs_id: str, save_path: str) -> bool:
    """PDF 다운로드"""
    api_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/pdf,*/*',
        'Referer': 'https://www.itfind.or.kr/'
    }

    try:
        print(f"   PDF 다운로드 중... ({streamdocs_id})")
        response = requests.get(api_url, headers=headers, timeout=60, stream=True)

        # 첫 청크로 PDF 확인
        first_chunk = next(response.iter_content(5), b'')
        if first_chunk[:5] != b'%PDF-':
            print(f"   ❌ PDF 시그니처 없음")
            return False

        # 저장
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)
        with open(save_path, 'wb') as f:
            f.write(first_chunk)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(save_path)
        print(f"   ✅ 다운로드 완료: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
        return True

    except Exception as e:
        print(f"   ❌ 다운로드 실패: {e}")
        return False


def extract_topics_from_chapters(pdf_path: str):
    """Chapter 기반 토픽 추출"""
    print(f"\n   PDF 분석 중...")

    try:
        doc = fitz.open(pdf_path)

        # 전체 텍스트 추출
        full_text = ""
        for page in doc:
            text = page.get_text()
            full_text += text + "\n"

        doc.close()

        # 라인 단위 분리
        lines = full_text.split('\n')

        # Chapter 패턴 탐지 (대소문자 무시)
        chapter_indices = []
        for i, line in enumerate(lines):
            line = line.strip()
            if re.match(r'^Chapter\s+\d+', line, re.IGNORECASE):
                chapter_indices.append((i, line))

        print(f"   감지된 Chapter 수: {len(chapter_indices)}")

        if chapter_indices:
            # 첫 몇 개 Chapter 출력
            for idx, (line_num, line_text) in enumerate(chapter_indices[:3]):
                print(f"     - {line_text}")

        # 각 Chapter 다음 라인에서 토픽 추출
        extracted_topics = []
        for chapter_idx, _ in chapter_indices:
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

                # 4. 페이지 번호 패턴 (예: "1-1", "2 - 3")
                if re.match(r'^\d+\s*[\-\–\—]\s*\d+$', next_line):
                    continue

                # 5. 일반적인 페이지 번호
                if re.match(r'^\d+\s*$', next_line):
                    continue

                extracted_topics.append(next_line)
                print(f"   토픽 {len(extracted_topics)}: {next_line[:70]}...")
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
        print(f"   ❌ 추출 실패: {e}")
        return {'기획시리즈': [], 'ICT 신기술': []}


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


def get_latest_detail_id():
    """최신 주간기술동향의 detail_id 가져오기"""
    session = requests.Session()

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        # 주간기술동향 목록 페이지 접근
        list_url = "https://www.itfind.or.kr/Library/List.do?searchType=6&menuCd=MEM050401"
        print("   목록 페이지 접근 중...")

        response = session.get(list_url, headers=headers, timeout=30)

        # 여러 패턴 시도
        patterns = [
            r"javascript:goDetail\('(\d+)'\)",
            r"goDetail\('(\d+)'\)",
            r"Detail\.do\?=(\d+)",
            r'boardNo["\s]*[:=]["\s]*(\d+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, response.text)
            if matches:
                detail_id = matches[0]
                print(f"   ✅ detail_id 추출: {detail_id} (패턴: {pattern[:20]}...)")
                return detail_id

        # HTML 저장하여 디버깅
        debug_path = "/tmp/itfind_list_debug.html"
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"   ❌ detail_id를 찾을 수 없습니다. HTML 저장: {debug_path}")
        return None

    except Exception as e:
        print(f"   ❌ 오류: {e}")
        return None


def main():
    """메인 실행"""
    print("="*60)
    print("ITFIND Chapter 기반 토픽 추출 테스트")
    print("="*60)

    # 1. 최신 detail_id 획득
    print("\n1. 최신 호 정보 수집 중...")
    detail_id = get_latest_detail_id()
    if not detail_id:
        print("\n❌ detail_id를 가져올 수 없습니다")
        return

    # 2. streamdocs_id 획득
    print(f"\n2. streamdocs_id 추출 중...")
    streamdocs_id = extract_streamdocs_id_from_detail_page(detail_id)
    if not streamdocs_id:
        return

    # 3. PDF 다운로드
    pdf_path = "/tmp/itfind_test_chapter.pdf"
    print(f"\n3. PDF 다운로드 중...")
    if not download_pdf_direct(streamdocs_id, pdf_path):
        return

    # 4. 토픽 추출
    print(f"\n4. Chapter 기반 토픽 추출 중...")
    result = extract_topics_from_chapters(pdf_path)

    # 5. 결과 출력
    print(f"\n5. 최종 결과:")
    print("="*60)
    for category, topics in result.items():
        print(f"\n[{category}] ({len(topics)}개):")
        for i, topic in enumerate(topics, 1):
            print(f"  {i}. {topic}")

    # 6. 정리
    try:
        os.remove(pdf_path)
    except:
        pass

    print("\n" + "="*60)
    print("✅ 테스트 완료")
    print("="*60)


if __name__ == "__main__":
    main()
