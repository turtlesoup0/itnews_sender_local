#!/usr/bin/env python3
"""
ITFIND 주간기술동향 PDF 다운로드 Lambda 함수

매주 수요일 메인 Lambda에서 호출:
1. 최신 주간기술동향 조회 (RSS)
2. PDF 다운로드 (브라우저 없이!)
3. base64로 인코딩하여 반환
"""
import logging
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import base64

# 로컬 개발 환경에서 src 디렉토리를 PYTHONPATH에 추가
if os.path.exists('/var/task/src'):
    sys.path.insert(0, '/var/task/src')
elif os.path.exists('./src'):
    sys.path.insert(0, './src')

from src.itfind_scraper import ItfindScraper
import requests
import xml.etree.ElementTree as ET
import re

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_latest_weekly_trend_from_rss():
    """
    RSS 피드에서 최신 주간기술동향 정보 조회 (브라우저 불필요)

    Returns:
        dict: {'title': str, 'issue_number': str, 'publish_date': str, 'pdf_url': str, 'detail_id': str}
    """
    try:
        rss_url = "https://www.itfind.or.kr/ccenter/rss.do?codeAlias=all&rssType=02"
        logger.info(f"RSS 피드 조회: {rss_url}")

        response = requests.get(rss_url, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall('.//item')

        logger.info(f"RSS 피드 항목 수: {len(items)}")

        # 첫 번째 주간기술동향의 호수 찾기
        target_issue_number = None
        topics = []
        first_detail_id = None
        first_pdf_url = None
        first_publish_date = None  # 첫 번째 항목의 발행일 저장

        for item in items:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pubdate_elem = item.find('pubDate')

            if title_elem is None or link_elem is None:
                continue

            title = title_elem.text
            link = link_elem.text

            # 주간기술동향 필터링
            if not title or '[주간기술동향' not in title:
                continue

            # 호수 추출
            issue_match = re.search(r'\[주간기술동향\s+(\d+)호\]', title)
            if not issue_match:
                continue

            issue_number = issue_match.group(1)

            # 첫 번째 주간기술동향의 호수 저장
            if target_issue_number is None:
                target_issue_number = issue_number
                logger.info(f"✅ 주간기술동향 발견: {title} ({issue_number}호)")

                # 발행일 파싱 (실제 RSS pubDate 사용)
                if pubdate_elem is not None and pubdate_elem.text:
                    first_publish_date = parse_rss_pubdate(pubdate_elem.text)
                    logger.info(f"   RSS 발행일: {pubdate_elem.text} -> {first_publish_date}")

                # detail_id 추출 (첫 번째 것만 사용)
                detail_id_match = re.search(r'identifier=([\w-]+)', link)
                first_detail_id = detail_id_match.group(1).replace('TVOL_', '') if detail_id_match else None

                if first_detail_id:
                    first_pdf_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{first_detail_id}"
                else:
                    first_pdf_url = link.replace('http://', 'https://')

            # 같은 호수의 모든 토픽 수집
            if issue_number == target_issue_number:
                # 제목에서 토픽 추출 (호수 부분 제거)
                topic = re.sub(r'\s*\[주간기술동향\s+\d+호\]', '', title).strip()
                if topic:
                    topics.append(topic)
                    logger.info(f"   토픽 추가: {topic}")

        if target_issue_number and first_detail_id:
            # 발행일 (RSS에서 파싱한 실제 발행일 사용, 없으면 현재 날짜로 fallback)
            kst = timezone(timedelta(hours=9))
            publish_date = first_publish_date if first_publish_date else datetime.now(kst).strftime("%Y-%m-%d")

            # 첫 번째 토픽을 대표 제목으로 사용
            main_title = topics[0] if topics else f"주간기술동향 {target_issue_number}호"

            return {
                'title': main_title,  # 첫 번째 토픽 (호수 제외)
                'issue_number': target_issue_number,
                'publish_date': publish_date,
                'pdf_url': first_pdf_url,
                'detail_id': first_detail_id,
                'topics': topics  # 모든 토픽 리스트
            }

        logger.warning("RSS 피드에서 주간기술동향을 찾을 수 없습니다")
        return None

    except Exception as e:
        logger.error(f"RSS 피드 조회 실패: {e}")
        return None


def is_content_fresh(publish_date: str, staleness_days: int) -> bool:
    """
    컨텐츠 신선도 확인 (발행일이 지정된 일수 이내인지 확인)

    Args:
        publish_date: 발행일 문자열 (YYYY-MM-DD 형식)
        staleness_days: 신선도 임계값 (일)

    Returns:
        True if content is fresh (age <= staleness_days), False otherwise
    """
    try:
        # 날짜 파싱
        kst = timezone(timedelta(hours=9))
        pub_dt = datetime.strptime(publish_date, "%Y-%m-%d").replace(tzinfo=kst)
        now_dt = datetime.now(kst)

        # 나이 계산 (일)
        age_days = (now_dt - pub_dt).days

        logger.info(f"   컨텐츠 나이: {age_days}일 (임계값: {staleness_days}일)")

        # 신선도 확인
        is_fresh = age_days <= staleness_days

        if is_fresh:
            logger.info(f"✅ 컨텐츠 신선함: {publish_date} ({age_days}일 전)")
        else:
            logger.warning(f"⚠️  컨텐츠 부fresh: {publish_date} ({age_days}일 전, 임계값 {staleness_days}일 초과)")

        return is_fresh

    except ValueError as e:
        logger.error(f"날짜 형식 오류: {publish_date} - {e}")
        return False
    except Exception as e:
        logger.error(f"신선도 확인 실패: {e}")
        return False


def parse_rss_pubdate(pubdate_str: str) -> Optional[str]:
    """
    RSS pubDate 문자열을 YYYY-MM-DD 형식으로 파싱

    Args:
        pubdate_str: RFC 822 형식의 pubDate 문자열 (예: "Mon, 03 Feb 2026 00:00:00 KST")

    Returns:
        YYYY-MM-DD 형식의 날짜 문자열 또는 None (파싱 실패 시)
    """
    try:
        # 여러 가지 날짜 형식 시도
        date_formats = [
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 822 with timezone
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 822 with numeric timezone
            "%a, %d %b %Y %H:%M:%S",     # Without timezone
            "%Y-%m-%d",                    # ISO 8601
            "%Y%m%d",                      # Compact format
        ]

        from dateutil import parser as dateutil_parser

        # dateutil의 parser로 시도 (가장 유연함)
        dt = dateutil_parser.parse(pubdate_str)

        # KST 타임존으로 변환 (이미 KST인 경우 유지)
        kst = timezone(timedelta(hours=9))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=kst)
        else:
            dt = dt.astimezone(kst)

        return dt.strftime("%Y-%m-%d")

    except Exception as e:
        logger.warning(f"pubDate 파싱 실패: {pubdate_str} - {e}")
        return None


def extract_topics_from_pdf_page3(pdf_path: str) -> Dict[str, List[str]]:
    """
    PDF 3페이지(목차)에서 카테고리별 토픽 추출 (구조 인식 기반 상태 머신)

    PDF 구조: Topic (20+ chars) → Author (_ pattern) → Contents (short + page) → Next Topic

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        카테고리별 토픽 딕셔너리
        예: {"기획시리즈: 인공지능(AI)": ["주제1", "주제2"], "ICT 신기술": ["주제3"]}
    """
    try:
        # PyMuPDF (fitz) import
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF (fitz)를 사용할 수 없어 토픽 추출을 건너뜁니다")
            return {}

        logger.info(f"PDF 3페이지에서 카테고리별 토픽 추출 (상태 머신): {pdf_path}")

        doc = fitz.open(pdf_path)

        # 3페이지(인덱스 2) 텍스트 추출
        if len(doc) < 3:
            logger.warning(f"PDF에 3페이지가 없습니다 (총 {len(doc)}페이지)")
            doc.close()
            return {}

        page = doc[2]  # 0-based, so 2 = page 3
        text = page.get_text()
        doc.close()

        # 줄 단위로 분석
        lines = text.split('\n')

        # 상태 머신 상태 정의
        # WAITING_CATEGORY: 카테고리 대기 중
        # WAITING_TOPIC: 주제 대기 중 (카테고리 바로 다음)
        # SKIP_FIRST_AFTER_PAGE: 페이지 번호 후 첫 번째 텍스트 건너뜀
        # WAITING_TOPIC_AFTER_PAGE: 페이지 번호 후 주제 대기 중
        # IN_AUTHOR: 저자 대기 중
        # IN_CONTENTS: 목차 진행 중 (하위 목차 건너뜀)
        states = ['WAITING_CATEGORY', 'WAITING_TOPIC', 'SKIP_FIRST_AFTER_PAGE', 'WAITING_TOPIC_AFTER_PAGE', 'IN_AUTHOR', 'IN_CONTENTS']

        result = {}
        current_category = None
        state = states[0]
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # 빈 라인 무시
            if not line:
                i += 1
                continue

            # 상태: 카테고리 대기 중
            if state == 'WAITING_CATEGORY':
                # 카테고리 키워드 감지
                if line == '기획시리즈:':
                    # 하위 카테고리명(예: 5Gㆍ6Gㆍ위성)는 무시하고 "기획시리즈"만 사용
                    current_category = "기획시리즈"
                    result[current_category] = []
                    state = 'WAITING_TOPIC'
                    logger.info(f"[STATE] 카테고리 발견: {current_category}")

                elif line == 'ICT 신기술':
                    current_category = "ICT 신기술"
                    result[current_category] = []
                    state = 'WAITING_TOPIC'
                    logger.info(f"[STATE] 카테고리 발견: {current_category}")

                elif line in ['연구보고서:', '정책:']:
                    current_category = line.rstrip(':')
                    result[current_category] = []
                    state = 'WAITING_TOPIC'
                    logger.info(f"[STATE] 카테고리 발견: {current_category}")

            # 상태: 주제 대기 중 (카테고리 바로 다음)
            elif state == 'WAITING_TOPIC':
                # 주제 패턴: 긴 텍스트 (15-100자), 저자 패턴 없음, 숫자만 아님
                if (15 < len(line) < 100 and
                    not re.search(r'_\s*[가-힣]', line) and
                    not re.match(r'^\d+$', line)):
                    result[current_category].append(line)
                    state = 'IN_AUTHOR'
                    logger.info(f"[STATE] 주제 감지: {line}")

            # 상태: 페이지 번호 후 주제 대기 중
            elif state == 'WAITING_TOPIC_AFTER_PAGE':
                # 카테고리 키워드를 먼저 확인 (ICT 신기술 등이 올 수 있음)
                if line in ['기획시리즈:', 'ICT 신기술', '연구보고서:', '정책:']:
                    # 카테고리가 바뀌면 상태를 재설정
                    if line == 'ICT 신기술':
                        current_category = "ICT 신기술"
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                    elif line == '기획시리즈:':
                        current_category = "기획시리즈"
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                    else:
                        current_category = line.rstrip(':')
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                # 주제 패턴: 긴 텍스트 (15-100자), 저자 패턴 없음, 숫자만 아님
                elif (15 < len(line) < 100 and
                    not re.search(r'_\s*[가-힣]', line) and
                    not re.match(r'^\d+$', line)):
                    result[current_category].append(line)
                    state = 'IN_AUTHOR'
                    logger.info(f"[STATE] 페이지 후 주제 감지: {line}")

            # 상태: 저자 대기 중
            elif state == 'IN_AUTHOR':
                # 저자 패턴: _한글 (예: 김OO_기관)
                if re.search(r'_\s*[가-힣]+', line):
                    state = 'IN_CONTENTS'
                    logger.info(f"[STATE] 저자 감지: {line[:30]}...")
                else:
                    # 저자가 없는 경우도 목차 상태로 진행
                    state = 'IN_CONTENTS'

            # 상태: 목차 진행 중 (하위 목차 건너뜀)
            elif state == 'IN_CONTENTS':
                # 어떤 내용이든 목차로 간주하고 건너뜀
                # 페이지 번호를 만나면 첫 번째 텍스트 건너뜀 상태로
                if re.match(r'^\d+$', line):
                    state = 'SKIP_FIRST_AFTER_PAGE'
                    logger.info(f"[STATE] 페이지 번호로 목차 종료, 첫 번째 텍스트 건너뜀: {line}")

            # 상태: 페이지 번호 후 첫 번째 텍스트 건너뜀
            elif state == 'SKIP_FIRST_AFTER_PAGE':
                # 카테고리 키워드를 먼저 확인
                if line in ['기획시리즈:', 'ICT 신기술', '연구보고서:', '정책:']:
                    # 카테고리가 바뀌면 상태를 재설정
                    if line == 'ICT 신기술':
                        current_category = "ICT 신기술"
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                    elif line == '기획시리즈:':
                        current_category = "기획시리즈"
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                    else:
                        current_category = line.rstrip(':')
                        result[current_category] = []
                        state = 'WAITING_TOPIC'
                        logger.info(f"[STATE] 카테고리 변경: {current_category}")
                # 첫 번째 텍스트는 무조건 건너뜀 (하위 목차 첫 항목)
                elif not re.match(r'^\d+$', line):
                    state = 'WAITING_TOPIC_AFTER_PAGE'
                    logger.info(f"[STATE] 첫 번째 텍스트 건너뜀: {line}")

            i += 1

        logger.info(f"✅ PDF 3페이지 토픽 추출 완료: {len(result)}개 카테고리")
        for category, topics in result.items():
            logger.info(f"  [{category}] {len(topics)}개 주제")
            for idx, topic in enumerate(topics, 1):
                logger.info(f"    {idx}. {topic}")

        return result

    except Exception as e:
        logger.warning(f"PDF 3페이지 토픽 추출 실패: {e}")
        return {}


def extract_topics_from_chapters(pdf_path: str) -> Dict[str, List[str]]:
    """
    PDF 전체 본문에서 Chapter 패턴으로 토픽 추출

    PDF 구조:
        토픽 제목 (여러 줄 가능)
        - 부제 (대시 감싸인 텍스트) -
        Chapter
        01

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        카테고리별 토픽 딕셔너리
        예: {"기획시리즈": ["주제1", "주제2"], "ICT 신기술": ["주제3"]}

    토픽 분류 규칙:
    - 2개 토픽: 첫 번째는 "기획시리즈", 두 번째는 "ICT 신기술"
    - 3개 토픽: 첫 두 개는 "기획시리즈", 세 번째는 "ICT 신기술" (2203호 특례)
    - 4개 이상: 절반(반올림)은 "기획시리즈", 나머지는 "ICT 신기술"
    """
    try:
        # PyMuPDF (fitz) import
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF (fitz)를 사용할 수 없어 토픽 추출을 건너뜁니다")
            return {}

        logger.info(f"PDF 전체 본문에서 Chapter 패턴 기반 토픽 추출 (역방향): {pdf_path}")

        # PDF 파일 유효성 검증
        if not os.path.exists(pdf_path):
            logger.error(f"PDF 파일이 존재하지 않습니다: {pdf_path}")
            raise FileNotFoundError(f"PDF 파일이 존재하지 않습니다: {pdf_path}")

        doc = fitz.open(pdf_path)

        # PDF 형식 검증
        if doc.is_encrypted:
            logger.warning(f"PDF가 암호화되어 있습니다: {pdf_path}")
            doc.close()
            return {}

        # 전체 PDF 텍스트 추출
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        # 라인 단위 분리
        lines = full_text.split('\n')

        # Chapter 패턴 찾기 (정확히 "Chapter"만)
        chapter_topics = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # "Chapter" 패턴 탐지
            if line_stripped == "Chapter":
                # 다음 라인에 숫자가 있는지 확인
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if re.match(r'^\d+$', next_line):
                        # 역방향으로 토픽 찾기
                        topic_parts = []
                        j = i - 1

                        while j >= max(0, i - 20):
                            prev_line = lines[j].strip()

                            if not prev_line:
                                j -= 1
                                continue

                            # 대시 라인(- xxx -) 건너뛰기
                            if re.match(r'^\s*-\s*.+\s*-\s*$', prev_line):
                                j -= 1
                                continue

                            # 숫자만 있는 라인 - 중단
                            if re.match(r'^\d+$', prev_line):
                                break

                            # 매우 짧은 라인(2자 이하) - 중단
                            if len(prev_line) <= 2:
                                break

                            # 본문 패턴(매우 긴 라인) - 중단
                            if len(prev_line) > 150:
                                break

                            # 각주 패턴 - 중단
                            if '본 내용은' in prev_line and '문의하시기 바랍니다' in prev_line:
                                break

                            topic_parts.insert(0, prev_line)
                            j -= 1

                            # 충분한 길이면 중단
                            combined = ' '.join(topic_parts)
                            if len(combined) > 20:
                                break

                        if topic_parts:
                            topic = ' '.join(topic_parts)

                            # 정제: 카테고리 접두사 제거
                            topic = re.sub(r'^기획시리즈[-\s]*', '', topic)
                            topic = re.sub(r'^ICT신기술\s*', '', topic)
                            topic = re.sub(r'^인공지능\(AI\)\s*', '', topic)

                            # 정제: 면책 조항 제거
                            topic = re.sub(r'\*\*\s*본 내용은 필자의 주관적인 의견.*?\.', '', topic)
                            topic = re.sub(r'\*\s*본 내용은.*?문의하시기 바랍니다\.', '', topic)

                            topic = topic.strip()

                            if topic and 10 < len(topic) < 150:
                                chapter_topics.append(topic)
                                logger.info(f"  토픽 추출: {topic}")

        if not chapter_topics:
            logger.warning(f"Chapter 패턴을 찾을 수 없습니다: {pdf_path}")
            return {}

        logger.info(f"감지된 Chapter 수: {len(chapter_topics)}개")

        # 중복 토픽 제거
        unique_topics = []
        seen = set()
        for topic in chapter_topics:
            if topic not in seen:
                seen.add(topic)
                unique_topics.append(topic)

        topics = unique_topics

        logger.info(f"추출된 토픽 (중복 제거 후): {len(topics)}개")

        # 카테고리 매핑
        result = _map_topics_to_categories(topics)

        # 결과 로깅
        logger.info(f"✅ Chapter 기반 토픽 추출 완료: {len(result)}개 카테고리")
        for category, category_topics in result.items():
            logger.info(f"  [{category}] {len(category_topics)}개 주제")
            for idx, topic in enumerate(category_topics, 1):
                logger.info(f"    {idx}. {topic}")

        return result

    except FileNotFoundError:
        logger.warning(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        return {}
    except Exception as e:
        logger.warning(f"Chapter 기반 토픽 추출 실패: {e}")
        return {}


def _map_topics_to_categories(topics: List[str]) -> Dict[str, List[str]]:
    """
    추출된 토픽을 카테고리로 매핑

    Args:
        topics: 토픽 리스트

    Returns:
        카테고리별 토픽 딕셔너리
    """
    result = {
        "기획시리즈": [],
        "ICT 신기술": []
    }

    if not topics:
        return result

    topic_count = len(topics)

    # 토픽 분류 규칙
    if topic_count == 1:
        # 1개만 있는 경우: 기획시리즈로 분류
        result["기획시리즈"] = topics
    elif topic_count == 2:
        # 2개인 경우: 첫 번째는 기획시리즈, 두 번째는 ICT 신기술
        result["기획시리즈"] = [topics[0]]
        result["ICT 신기술"] = [topics[1]]
    elif topic_count == 3:
        # 3개인 경우 (2203호 특례): 첫 두 개는 기획시리즈, 세 번째는 ICT 신기술
        result["기획시리즈"] = topics[:2]
        result["ICT 신기술"] = topics[2:]
    else:
        # 4개 이상인 경우: 절반(반올림)은 기획시리즈, 나머지는 ICT 신기술
        split_point = (topic_count + 1) // 2  # 반올림
        result["기획시리즈"] = topics[:split_point]
        result["ICT 신기술"] = topics[split_point:]

    return result


def extract_topics_from_detail_page(detail_id: str) -> List[str]:
    """
    ITFIND 상세 페이지에서 토픽 목차 추출 (브라우저 불필요)

    Args:
        detail_id: TVOL을 제외한 ID (예: "1388")

    Returns:
        토픽 리스트 (로마자 번호 포함)
    """
    try:
        detail_url = f"https://www.itfind.or.kr/trend/weekly/weeklyDetail.do?id={detail_id}"
        logger.info(f"ITFIND 상세 페이지에서 토픽 추출: {detail_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.itfind.or.kr/",
        }

        response = requests.get(detail_url, headers=headers, timeout=30)
        response.raise_for_status()

        # HTML에서 dd 요소 추출 (목차 포맷)
        # 패턴: <dd class="line-to-br">I. 개요 II. ...</dd>
        dd_pattern = r'<dd[^>]*class="[^"]*line-to-br[^"]*"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)?[^<]*)</dd>'
        matches = re.findall(dd_pattern, response.text, re.IGNORECASE | re.DOTALL)

        topics = []

        for match in matches:
            # HTML 태그 제거
            text = re.sub(r'<[^>]+>', ' ', match)
            # HTML 엔티티 디코딩
            import html as html_lib
            text = html_lib.unescape(text)
            # 공백 정리
            text = re.sub(r'\s+', ' ', text).strip()

            if not text or len(text) < 10:
                continue

            # 로마자 번호 패턴으로 분리 (I. II. III. IV. V. VI. VII. VIII. IX. X. 등)
            # 공백이 없는 경우(예: "VII.결론")도 처리하기 위해 마침표 뒤에 공백을 추가
            text = re.sub(r'([IVX]+)\.([가-힣A-Z])', r'\1. \2', text)
            # 단어 문자가 아닌 문자 경계 다음의 로마자 번호를 기준으로 분리
            parts = re.split(r'(?<!\w)([IVX]+)\.\s+', text)

            current_roman = ''
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue

                # 로마자 번호인지 확인
                if re.match(r'^[IVX]+$', part):
                    current_roman = part
                elif current_roman:
                    # 로마자 번호 다음 내용
                    topic = f'{current_roman}. {part}'
                    # '결론', '개요' 등 필수 키워드 포함 또는 충분한 길이
                    if (len(topic) > 8 and
                        not topic.endswith('. .') and
                        not topic.startswith('X. X.')):
                        topics.append(topic)
                    current_roman = ''
                elif len(part) > 10:
                    # 로마자 번호 없이 토픽 추가
                    topics.append(part)

        # 중복 제거하고 순서 유지
        seen = set()
        unique_topics = []
        for topic in topics:
            # 정규화: 공백 정리
            normalized = re.sub(r'\s+', ' ', topic).strip()

            # 필터링:
            # 1. 로마자 번호로 시작하는 항목만 (I., II., III. 등)
            # 2. 너무 긴 항목 제외 (100자 초과는 설명 텍스트로 간주)
            # 3. 너무 짧은 항목 제외 (10자 미만)
            if (not normalized or
                len(normalized) > 100 or  # 설명 텍스트 제외
                len(normalized) < 10 or   # 너무 짧은 항목 제외
                not re.match(r'^[IVX]+\.\s+', normalized)):  # 로마자 번호로 시작
                continue

            if normalized not in seen:
                seen.add(normalized)
                unique_topics.append(normalized)

        logger.info(f"✅ 토픽 추출 성공: {len(unique_topics)}개 토픽")
        for i, topic in enumerate(unique_topics[:10], 1):
            logger.info(f"   {i}. {topic}")

        return unique_topics

    except Exception as e:
        logger.warning(f"토픽 추출 실패: {e}")
        return []


def extract_streamdocs_id_from_detail_page(detail_id: str) -> Optional[str]:
    """
    getStreamDocsRegi.htm에서 StreamDocs 뷰어 URL을 따라가 StreamDocs ID 추출

    Args:
        detail_id: TVOL을 제외한 ID (예: "1388")

    Returns:
        StreamDocs ID 또는 None
    """
    try:
        # 1단계: getStreamDocsRegi.htm 페이지 접근
        streamdocs_regi_url = f"https://www.itfind.or.kr/admin/getStreamDocsRegi.htm?identifier=TVOL_{detail_id}"
        logger.info(f"StreamDocs Regi 페이지 접근: {streamdocs_regi_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "*/*",
            "Referer": "https://www.itfind.or.kr/",
        }

        session = requests.Session()
        response = session.get(streamdocs_regi_url, headers=headers, timeout=30, allow_redirects=True)

        # JavaScript 리다이렉트 URL 추출
        # 패턴: top.location.href="https://www.itfind.or.kr/publication/.../view.do?..."
        js_redirect_match = re.search(r'location\.href\s*=\s*["\']([^"\']+)["\']', response.text)

        if js_redirect_match:
            redirect_url = js_redirect_match.group(1)
            logger.info(f"JavaScript 리다이렉트 URL 발견: {redirect_url}")

            # 2단계: 리다이렉트된 페이지 접근 (자동으로 StreamDocs 뷰어로 redirect됨)
            if not redirect_url.startswith('http'):
                redirect_url = f"https://www.itfind.or.kr{redirect_url}"

            response2 = session.get(redirect_url, headers=headers, timeout=30, allow_redirects=True)

            logger.info(f"최종 URL: {response2.url}")

            # 3단계: 최종 URL에서 StreamDocs ID 추출
            # 패턴: https://www.itfind.or.kr/streamdocs/view/sd;streamdocsId=RtkNUpG5UfML1iXVCbU0-QqbinAUTQxwz58xRm02GRs
            if 'streamdocsId=' in response2.url:
                match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.url)
                if match:
                    streamdocs_id = match.group(1)
                    logger.info(f"✅ StreamDocs ID 추출 성공 (최종 URL): {streamdocs_id}")
                    return streamdocs_id

            # 4단계: HTML에서도 검색
            match = re.search(r'streamdocsId=([A-Za-z0-9_-]+)', response2.text)
            if match:
                streamdocs_id = match.group(1)
                logger.info(f"✅ StreamDocs ID 추출 성공 (HTML): {streamdocs_id}")
                return streamdocs_id

        logger.warning("StreamDocs ID를 찾을 수 없습니다")
        return None

    except Exception as e:
        logger.error(f"StreamDocs ID 추출 실패: {e}", exc_info=True)
        return None


def download_pdf_direct(streamdocs_id: str, save_path: str) -> bool:
    """
    StreamDocs API를 직접 호출하여 PDF 다운로드 (브라우저 불필요)

    Args:
        streamdocs_id: StreamDocs 문서 ID
        save_path: 저장할 파일 경로

    Returns:
        성공 여부
    """
    try:
        # StreamDocs v4 API 직접 호출
        api_url = f"https://www.itfind.or.kr/streamdocs/v4/documents/{streamdocs_id}"
        logger.info(f"StreamDocs API 직접 호출: {api_url}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
            'Referer': 'https://www.itfind.or.kr/'
        }

        response = requests.get(api_url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()

        # PDF인지 확인 (Content-Type은 application/octet-stream일 수 있음)
        content_type = response.headers.get('content-type', '').lower()
        logger.info(f"Content-Type: {content_type}")

        # PDF 시그니처로 확인 (가장 확실함)
        first_chunk = next(response.iter_content(5), b'')
        if first_chunk[:5] != b'%PDF-':
            logger.error(f"응답이 PDF가 아닙니다: content-type={content_type}, 시그니처={first_chunk[:5]}")
            return False

        logger.info(f"✅ PDF 시그니처 확인됨: {first_chunk[:5]}")

        # 파일 저장
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else '.', exist_ok=True)

        with open(save_path, 'wb') as f:
            # 이미 읽은 첫 청크가 있다면 먼저 쓰기
            if 'first_chunk' in locals():
                f.write(first_chunk)

            # 나머지 다운로드
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(save_path)
        logger.info(f"✅ PDF 다운로드 완료: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        return True

    except Exception as e:
        logger.error(f"PDF 다운로드 실패: {e}")
        return False


async def download_itfind_pdf() -> Optional[Dict[str, Any]]:
    """
    ITFIND 주간기술동향 PDF 다운로드 (브라우저 없이!)

    Returns:
        Dict: {
            'title': str,
            'issue_number': str,
            'publish_date': str,
            'filename': str,
            'file_size': int,
            'streamdocs_id': str,
            'pdf_base64': str  # base64 인코딩된 PDF 데이터
        } or None
    """
    try:
        logger.info("=" * 60)
        logger.info("ITFIND 주간기술동향 PDF 다운로드 시작 (브라우저 없이)")
        logger.info("=" * 60)

        # 1. RSS에서 최신 주간기술동향 정보 조회
        logger.info("1단계: RSS 피드에서 최신 주간기술동향 조회")
        trend = get_latest_weekly_trend_from_rss()

        if not trend:
            logger.warning("주간기술동향을 찾을 수 없습니다")
            return None

        logger.info(f"✅ 주간기술동향 발견: {trend['title']} ({trend['issue_number']}호)")
        logger.info(f"   발행일: {trend['publish_date']}")
        logger.info(f"   Detail ID: {trend['detail_id']}")

        # 1.5단계: 컨텐츠 신선도 확인 (REQ-1)
        logger.info("1.5단계: 컨텐츠 신선도 확인")

        # Config에서 신선도 임계값 가져오기
        try:
            from src.config import Config
            staleness_days = Config.ITFIND_STALENESS_DAYS
        except Exception:
            # Fallback to default value if config loading fails
            staleness_days = 6
            logger.warning("Config 로드 실패, 기본값 6일 사용")

        if not is_content_fresh(trend['publish_date'], staleness_days):
            skip_reason = f"ITFIND skipped: stale content (publish_date={trend['publish_date']}, today={datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')}, staleness_threshold={staleness_days}days)"
            logger.warning(f"⚠️  {skip_reason}")
            return None

        # 2. 상세 페이지에서 StreamDocs ID 추출
        logger.info("2단계: 상세 페이지에서 StreamDocs ID 추출")
        streamdocs_id = extract_streamdocs_id_from_detail_page(trend['detail_id'])

        if not streamdocs_id:
            logger.error("StreamDocs ID를 추출할 수 없습니다")
            return None

        # 3. StreamDocs API로 PDF 직접 다운로드
        logger.info("3단계: StreamDocs API로 PDF 다운로드")
        kst = timezone(timedelta(hours=9))
        today_str = datetime.now(kst).strftime("%Y%m%d")
        local_path = f"/tmp/itfind_weekly_{today_str}.pdf"

        if not download_pdf_direct(streamdocs_id, local_path):
            logger.error("PDF 다운로드 실패")
            return None

        file_size = os.path.getsize(local_path)

        # 3.5단계: PDF 전체 본문에서 Chapter 패턴 기반 카테고리별 토픽 추출
        logger.info("3.5단계: PDF 전체 본문에서 Chapter 패턴 기반 카테고리별 토픽 추출")
        categorized_topics = extract_topics_from_chapters(local_path)

        # 카테고리별 토픽이 추출되지 않으면 빈 딕셔너리 사용
        if not categorized_topics:
            categorized_topics = {}
            logger.warning("카테고리별 토픽 추출 실패, 빈 결과 반환")

        # 3.6단계: PDF 메타데이터에 카테고리별 토픽 저장
        logger.info("3.6단계: PDF 메타데이터에 카테고리별 토픽 저장")

        try:
            import fitz  # PyMuPDF
            doc = fitz.open(local_path)

            # 메타데이터 형식: JSON string
            import json
            metadata_description = json.dumps(categorized_topics, ensure_ascii=False)

            # 메타데이터 설정 (PyMuPDF는 'subject' 키 사용)
            doc.set_metadata({"subject": metadata_description})
            doc.saveIncr()  # 증분 저장 (빠름)
            doc.close()

            logger.info(f"✅ PDF 메타데이터 저장 완료: {len(metadata_description)} chars")

        except Exception as e:
            logger.warning(f"PDF 메타데이터 저장 실패 (무시): {e}")

        # 4. PDF를 base64로 인코딩하여 반환 (S3 불필요!)
        logger.info("4단계: PDF base64 인코딩")
        with open(local_path, 'rb') as f:
            pdf_data = f.read()
            pdf_base64 = base64.b64encode(pdf_data).decode('utf-8')

        logger.info("=" * 60)
        logger.info("✅ ITFIND PDF 다운로드 성공")
        logger.info("=" * 60)

        return {
            'title': trend['title'],
            'issue_number': trend['issue_number'],
            'publish_date': trend['publish_date'],
            'filename': f"ITFIND_주간기술동향_{trend['issue_number']}호_{today_str}.pdf",
            'file_size': file_size,
            'streamdocs_id': streamdocs_id,
            'pdf_base64': pdf_base64,  # base64 인코딩된 PDF
            'topics': trend.get('topics', []),  # RSS 토픽 리스트 (목차 항목)
            'categorized_topics': categorized_topics  # 카테고리별 토픽 딕셔너리
        }

    except Exception as e:
        logger.error(f"ITFIND PDF 다운로드 실패: {e}", exc_info=True)
        logger.warning("=" * 60)
        logger.warning("⚠️ ITFIND PDF 다운로드 실패")
        logger.warning("=" * 60)
        return None


def handler(event, context):
    """
    Lambda 핸들러

    Args:
        event: EventBridge 이벤트 또는 테스트 이벤트
        context: Lambda 컨텍스트

    Returns:
        dict: 성공 여부 및 메타데이터
    """
    try:
        logger.info(f"Lambda 시작: {context.aws_request_id}")
        logger.info(f"이벤트: {event}")

        # 비동기 함수 실행
        result = asyncio.run(download_itfind_pdf())

        if result:
            return {
                'statusCode': 200,
                'body': {
                    'success': True,
                    'message': 'ITFIND PDF downloaded successfully',
                    'data': result
                }
            }
        else:
            return {
                'statusCode': 404,
                'body': {
                    'success': False,
                    'message': 'Failed to download ITFIND PDF',
                    'data': None
                }
            }

    except Exception as e:
        logger.error(f"Lambda 실행 실패: {e}", exc_info=True)

        return {
            'statusCode': 500,
            'body': {
                'success': False,
                'message': f'Lambda execution failed: {str(e)}',
                'data': None
            }
        }


if __name__ == '__main__':
    # 로컬 테스트
    class MockContext:
        request_id = 'local-test-123'
        invoked_function_arn = 'arn:aws:lambda:local'

    result = handler({}, MockContext())
    print(f"\n결과: {result}")
