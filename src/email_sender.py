"""
이메일 전송 모듈
Gmail SMTP를 사용하여 처리된 PDF 파일 전송
"""
import os
import smtplib
import logging
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from urllib.parse import quote
import email.utils

from .config import Config
from .recipients import get_active_recipients
from .unsubscribe_token import generate_token
import email.utils

if TYPE_CHECKING:
    from .itfind_scraper import WeeklyTrend

logger = logging.getLogger(__name__)


def _detect_image_subtype(image_bytes: bytes) -> tuple[str, str]:
    """[S3] 이미지 바이트의 매직 번호로 포맷 감지.

    Returns:
        (mime_subtype, file_extension) 튜플 — 예: ("jpeg", "jpg"), ("png", "png")
    """
    if not image_bytes:
        return ("png", "png")
    # JPEG: FF D8 FF
    if image_bytes[:3] == b'\xff\xd8\xff':
        return ("jpeg", "jpg")
    # PNG: 89 50 4E 47
    if image_bytes[:4] == b'\x89PNG':
        return ("png", "png")
    # 알 수 없는 포맷은 PNG로 간주 (안전한 기본값)
    return ("png", "png")


def generate_korean_filename(itfind_info: Optional["WeeklyTrend"] = None) -> tuple[str, str]:
    """
    ITFIND PDF용 한국어 첨부파일명 생성

    Args:
        itfind_info: ITFIND 정보 (optional)

    Returns:
        (korean_filename, ascii_filename) 튜플
        - korean_filename: 주기동YYMMDD-xxxx호.pdf
        - ascii_filename: itfind_YYMMDD-xxxx.pdf (fallback)
    """
    if itfind_info is None:
        # ITFIND 정보 없으면 기본 형식 사용
        today = datetime.now().strftime("%Y%m%d")
        return f"itfind_{today}.pdf", f"itfind_{today}.pdf"

    # 발행일 파싱 (YYYY-MM-DD -> YYMMDD)
    try:
        pub_date = datetime.strptime(itfind_info.publish_date, "%Y-%m-%d")
        yymmdd = pub_date.strftime("%y%m%d")
    except Exception:
        # 파싱 실패시 오늘 날짜 사용
        yymmdd = datetime.now().strftime("%y%m%d")

    # 호수에서 '호' 제거
    issue_number = str(itfind_info.issue_number).replace("호", "")

    # 한국어 파일명: 주기동YYMMDD-xxxx호.pdf
    korean_filename = f"주기동{yymmdd}-{issue_number}호.pdf"

    # ASCII fallback: itfind_YYMMDD-xxxx.pdf
    ascii_filename = f"itfind_{yymmdd}-{issue_number}.pdf"

    return korean_filename, ascii_filename


class EmailSender:
    """Gmail SMTP 이메일 전송"""

    def __init__(self):
        self.config = Config
        # 수신거부 토큰 생성을 위한 시크릿 키 (Config에서 로드)
        self.unsubscribe_secret = self.config.UNSUBSCRIBE_SECRET
        # Lambda Function URL for unsubscribe (Config에서 로드)
        self.unsubscribe_url_base = self.config.UNSUBSCRIBE_FUNCTION_URL

    def send_email(
        self,
        pdf_path: str,
        recipient: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> bool:
        """
        PDF 파일을 첨부하여 이메일 전송 (단일 수신자)

        Args:
            pdf_path: 전송할 PDF 파일 경로
            recipient: 수신자 이메일 (None이면 기본 수신자 사용)
            subject: 이메일 제목 (None이면 자동 생성)

        Returns:
            전송 성공 여부
        """
        try:
            # 수신자 설정
            to_email = recipient or self.config.RECIPIENT_EMAIL

            # 제목 설정
            if not subject:
                today = datetime.now().strftime("%Y-%m-%d")
                subject = f"IT뉴스 [{today}]"

            # 이메일 메시지 생성
            msg = self._create_message(pdf_path, [to_email], subject)

            # SMTP 서버 연결 및 전송
            self._send_via_smtp(msg, [to_email])

            logger.info(f"이메일 전송 성공: {to_email}")
            return True

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False

    def send_bulk_email(
        self,
        pdf_path: str,
        subject: Optional[str] = None,
        test_mode: bool = False,
        itfind_pdf_path: Optional[str] = None,
        itfind_info: Optional["WeeklyTrend"] = None,
    ) -> tuple[bool, List[str]]:
        """
        PDF 파일을 다중 수신자에게 개별 전송 (개인화된 수신거부 링크 포함)

        Args:
            pdf_path: 전송할 PDF 파일 경로 (전자신문)
            subject: 이메일 제목 (None이면 자동 생성)
            test_mode: True면 admin@example.com에게만 발송 (테스트용)
            itfind_pdf_path: ITFIND 주간기술동향 PDF 경로 (수요일만, Optional)
            itfind_info: ITFIND 주간기술동향 정보 (Optional)

        Returns:
            (전송 성공 여부, 성공한 수신인 이메일 리스트)
        """
        try:
            # 테스트 모드: 관리자 이메일로 고정
            if test_mode:
                from .recipients.models import Recipient, RecipientStatus
                test_recipient = Recipient(
                    email=self.config.ADMIN_EMAIL,
                    name="관리자 (테스트)",
                    status=RecipientStatus.ACTIVE,
                    created_at=datetime.now().isoformat()
                )
                recipients = [test_recipient]
                logger.info(f"🧪 TEST 모드: {self.config.ADMIN_EMAIL}에게만 발송")
            else:
                # OPR 모드: DynamoDB 활성 수신인
                recipients = get_active_recipients()
                logger.info(f"🚀 OPR 모드: {len(recipients)}명 활성 수신인에게 발송")

            if not recipients:
                logger.warning("활성 수신인이 없습니다")
                return False, []

            logger.info(f"이메일 전송 대상: {len(recipients)}명")

            # 제목 설정
            if not subject:
                today = datetime.now().strftime("%Y-%m-%d")
                subject = f"IT뉴스 [{today}]"

            # [S1 최적화] 수신자와 무관한 공통 자산(이미지·PDF 바이트)을 1회만 준비
            shared = self._prepare_shared_assets(
                pdf_path=pdf_path,
                subject=subject,
                itfind_pdf_path=itfind_pdf_path,
                itfind_info=itfind_info,
            )

            # 각 수신자에게 개별 전송
            success_emails = []
            fail_count = 0
            consecutive_fail = 0  # [S2] 연속 실패 카운터 (회로 차단용)
            fail_limit = getattr(self.config, "SMTP_CONSECUTIVE_FAIL_LIMIT", 5)
            reconnect_every = getattr(self.config, "SMTP_RECONNECT_EVERY", 50)

            # [S2 최적화] SMTP 연결을 1회만 수립하고 루프 전체에서 재사용
            server = self._open_smtp_connection()
            sent_since_connect = 0
            try:
                for recipient in recipients:
                    # Gmail 단일 연결 한도 대비: reconnect_every마다 재연결
                    if sent_since_connect >= reconnect_every:
                        logger.info(f"SMTP 재연결 (연속 {sent_since_connect}통 발송 후)")
                        try:
                            server.quit()
                        except Exception:
                            pass
                        server = self._open_smtp_connection()
                        sent_since_connect = 0

                    try:
                        # 개인화된 메시지 조립 (공유 자산 재사용)
                        msg = self._assemble_message(recipient.email, shared)

                        # 기존 SMTP 연결로 전송 (끊어진 경우 1회 재연결)
                        server = self._send_on_server(server, msg, [recipient.email])

                        success_emails.append(recipient.email)
                        sent_since_connect += 1
                        consecutive_fail = 0
                        logger.info(
                            f"이메일 전송 완료: {recipient.email} ({len(success_emails)}/{len(recipients)})"
                        )

                    except Exception as e:
                        fail_count += 1
                        consecutive_fail += 1
                        logger.error(f"이메일 전송 실패: {recipient.email} - {e}")
                        if consecutive_fail >= fail_limit:
                            logger.error(
                                f"🛑 연속 {consecutive_fail}회 실패 — 벌크 전송 조기 중단 "
                                f"(남은 수신자 {len(recipients) - len(success_emails) - fail_count}명)"
                            )
                            break
            finally:
                try:
                    server.quit()
                except Exception:
                    pass

            logger.info(f"이메일 전송 완료: 성공 {len(success_emails)}명, 실패 {fail_count}명")
            return len(success_emails) > 0, success_emails

        except Exception as e:
            logger.error(f"이메일 전송 실패: {e}")
            return False, []

    def _create_message(
        self,
        pdf_path: str,
        to_emails: List[str],
        subject: str,
        use_bcc: bool = False,
        recipient_email: Optional[str] = None,
        itfind_pdf_path: Optional[str] = None,
        itfind_info: Optional["WeeklyTrend"] = None
    ) -> MIMEMultipart:
        """이메일 메시지 생성"""

        # 메시지 객체 생성 (inline image를 위한 'related' 타입)
        msg = MIMEMultipart('related')
        msg["From"] = self.config.GMAIL_USER
        msg["Subject"] = subject

        if use_bcc:
            # BCC로 전송 (수신자 숨김)
            msg["To"] = self.config.GMAIL_USER  # 발신자 자신에게
            msg["Bcc"] = ", ".join(to_emails)
        else:
            # 일반 전송
            msg["To"] = ", ".join(to_emails)

        # ITFIND 목차 이미지 추출 (있는 경우)
        toc_image_bytes = None
        if itfind_pdf_path and os.path.exists(itfind_pdf_path):
            try:
                from .pdf_image_extractor import extract_toc_page_for_email
                toc_image_bytes = extract_toc_page_for_email(itfind_pdf_path)
                if toc_image_bytes:
                    logger.info("✅ ITFIND 목차 이미지 추출 성공")
                else:
                    logger.info("ITFIND 목차 이미지 추출 실패 (텍스트만 발송)")
            except Exception as e:
                logger.warning(f"목차 이미지 추출 중 오류: {e} (텍스트만 발송)")

        # 전자신문 1페이지 이미지 추출 (전자신문 이메일인 경우만)
        etnews_image_bytes = None
        is_itfind_only = (itfind_pdf_path is not None and
                          itfind_info is not None and
                          os.path.exists(itfind_pdf_path))

        if not is_itfind_only and os.path.exists(pdf_path):
            try:
                from .pdf_image_extractor import extract_first_page_for_email
                etnews_image_bytes = extract_first_page_for_email(pdf_path)
                if etnews_image_bytes:
                    logger.info("✅ 전자신문 1페이지 이미지 추출 성공")
                else:
                    logger.info("전자신문 1페이지 이미지 추출 실패 (텍스트만 발송)")
            except Exception as e:
                logger.warning(f"전자신문 이미지 추출 중 오류: {e} (텍스트만 발송)")

        # 이메일 본문 생성 (개인화된 수신거부 링크, TOC 이미지, 전자신문 이미지 포함 여부 전달)
        body = self._create_email_body(
            recipient_email,
            itfind_info,
            has_toc_image=(toc_image_bytes is not None),
            has_etnews_image=(etnews_image_bytes is not None)
        )
        msg.attach(MIMEText(body, "html", "utf-8"))

        # 전자신문 1페이지 이미지 첨부 (inline, CID 참조) — [S3] 포맷 자동 감지
        if etnews_image_bytes:
            try:
                subtype, ext = _detect_image_subtype(etnews_image_bytes)
                etnews_image = MIMEImage(etnews_image_bytes, _subtype=subtype)
                etnews_image.add_header('Content-ID', '<etnews_first_page>')
                etnews_image.add_header(
                    'Content-Disposition', 'inline', filename=f'etnews_p1.{ext}'
                )
                msg.attach(etnews_image)
                logger.info(
                    f"✅ 전자신문 1페이지 이미지 첨부 완료 (CID: etnews_first_page, fmt={subtype})"
                )
            except Exception as e:
                logger.warning(f"전자신문 이미지 첨부 실패: {e}")

        # ITFIND 목차 이미지 첨부 (inline, CID 참조)
        if toc_image_bytes:
            try:
                subtype, ext = _detect_image_subtype(toc_image_bytes)
                toc_image = MIMEImage(toc_image_bytes, _subtype=subtype)
                toc_image.add_header('Content-ID', '<toc_image>')
                toc_image.add_header(
                    'Content-Disposition', 'inline', filename=f'toc.{ext}'
                )
                msg.attach(toc_image)
                logger.info(
                    f"✅ ITFIND 목차 이미지 첨부 완료 (CID: toc_image, fmt={subtype})"
                )
            except Exception as e:
                logger.warning(f"목차 이미지 첨부 실패: {e}")

        # PDF 첨부: ITFIND 단독 이메일인지 여부 확인
        is_itfind_only = (itfind_pdf_path is not None and
                          itfind_info is not None and
                          os.path.exists(itfind_pdf_path))

        if is_itfind_only:
            # ITFIND 단독 이메일: ITFIND PDF만 첨부
            self._attach_pdf(msg, pdf_path, "itfind", itfind_info)
        else:
            # 전자신문 이메일: 전자신문 PDF 첨부 (+ ITFIND가 있으면 추가 첨부)
            self._attach_pdf(msg, pdf_path, "etnews")

            # ITFIND PDF 파일 첨부 (수요일만)
            if itfind_pdf_path and os.path.exists(itfind_pdf_path):
                self._attach_pdf(msg, itfind_pdf_path, "itfind", itfind_info)

        return msg

    def _generate_unsubscribe_token(self, email: str) -> str:
        """
        수신거부 토큰 생성 (HMAC 기반)

        Args:
            email: 이메일 주소

        Returns:
            Base64 인코딩된 토큰
        """
        return generate_token(email, self.unsubscribe_secret)

    def _create_email_body(self, recipient_email: Optional[str] = None, itfind_info: Optional["WeeklyTrend"] = None, has_toc_image: bool = False, has_etnews_image: bool = False) -> str:
        """이메일 본문 HTML 생성

        Args:
            recipient_email: 수신자 이메일 (수신거부 링크 생성용)
            itfind_info: ITFIND 정보 (dict 또는 WeeklyTrend 객체)
            has_toc_image: 목차 이미지 포함 여부
            has_etnews_image: 전자신문 1페이지 이미지 포함 여부
        """
        today = datetime.now().strftime("%Y년 %m월 %d일")

        # 수신거부 URL 생성
        unsubscribe_url = "#"
        if recipient_email:
            token = self._generate_unsubscribe_token(recipient_email)
            unsubscribe_url = f"{self.unsubscribe_url_base}/?token={token}"

        # ITFIND 단독 발송인 경우
        if itfind_info:
            # dict 타입인지 확인하고 topics/categorized_topics 추출
            if isinstance(itfind_info, dict):
                topics_list = itfind_info.get('topics', [])
                categorized_topics = itfind_info.get('categorized_topics', {})
                issue_number = itfind_info.get('issue_number', '')
                title = itfind_info.get('title', '')
                logger.info(f"ITFIND info (dict): issue={issue_number}, categorized_topics={categorized_topics}")
            else:
                # WeeklyTrend 객체인 경우
                topics_list = itfind_info.topics if hasattr(itfind_info, 'topics') else []
                categorized_topics = itfind_info.categorized_topics if hasattr(itfind_info, 'categorized_topics') else {}
                issue_number = itfind_info.issue_number if hasattr(itfind_info, 'issue_number') else ''
                title = itfind_info.title if hasattr(itfind_info, 'title') else ''
                logger.info(f"ITFIND info (object): issue={issue_number}, categorized_topics={categorized_topics}")

            # 목차 이미지 HTML (있는 경우)
            toc_image_html = ""
            if has_toc_image:
                toc_image_html = f"""
                    <div style="text-align: center; margin: 20px 0;">
                        <p style="font-size: 0.9em; color: #666;">📄 목차 미리보기</p>
                        <img src="cid:toc_image" alt="주간기술동향 목차" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;" />
                    </div>
                """

            # 토픽 HTML 생성 (카테고리별 또는 목록형)
            topics_html = ""
            if categorized_topics:
                # 카테고리별 토픽 HTML 생성
                category_sections = []
                for category, topics in categorized_topics.items():
                    topic_items = "<br>".join([f"  {i}. {topic}" for i, topic in enumerate(topics, 1)])
                    category_sections.append(f"""
                        <div style="margin-bottom: 15px;">
                            <strong style="color: #0066cc;">📂 {category}</strong>
                            <div style="margin-left: 10px; margin-top: 5px; line-height: 1.6;">
                                {topic_items}
                            </div>
                        </div>
                    """)
                topics_html = f"""
                    <h3>📑 이번 호 주요 주제</h3>
                    <div style="margin-left: 10px;">
                        {''.join(category_sections)}
                    </div>
                """
            elif topics_list:
                # 목차 항목 리스트 HTML 생성 (fallback)
                topic_items = "<br>".join([f"• {topic}" for topic in topics_list])
                topics_html = f"""
                    <h3>📑 이번 호 주요 토픽</h3>
                    <div style="margin-left: 20px; line-height: 1.8;">
                        {topic_items}
                    </div>
                """

            body = f"""
            <html>
                <head></head>
                <body>
                    <h2>📚 주간기술동향 {issue_number}호</h2>
                    <p>안녕하세요,</p>
                    <p>{today} 주간기술동향을 보내드립니다.</p>
                    {toc_image_html}
                    {topics_html}
                    <br>
                    <p style="color: #666; font-size: 0.9em;">
                        출처: <a href="https://www.itfind.or.kr/trend/weekly/weekly.do" style="color: #0066cc;">정보통신기획평가원 (IITP)</a>
                    </p>
                    <br>
                    <p>이 이메일은 자동으로 발송되었습니다.</p>
                    <p style="color: #666; font-size: 0.9em;">
                        이 서비스는 오픈소스 프로젝트로 운영됩니다:
                        <a href="https://github.com/your-username/your-repo" style="color: #0066cc;">GitHub 프로젝트 보기</a>
                    </p>
                    <hr>
                    <small>
                        문의사항이 있으시면 {self.config.ADMIN_EMAIL}으로 연락주세요.<br>
                        이 뉴스레터를 더 이상 받고 싶지 않으시면 <a href="{unsubscribe_url}" style="color: #666;">여기</a>를 클릭하세요.
                    </small>
                </body>
            </html>
            """
        else:
            # 전자신문 발송
            # 전자신문 1페이지 이미지 HTML (있는 경우)
            etnews_image_html = ""
            if has_etnews_image:
                etnews_image_html = f"""
                    <div style="text-align: center; margin: 20px 0;">
                        <p style="font-size: 0.9em; color: #666;">📰 오늘의 주요 기사 미리보기</p>
                        <img src="cid:etnews_first_page" alt="전자신문 1페이지" style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;" />
                    </div>
                """

            body = f"""
            <html>
                <head></head>
                <body>
                    <h2>IT뉴스 PDF 뉴스지면</h2>
                    <p>안녕하세요,</p>
                    <p>{today} IT뉴스 PDF 뉴스지면을 보내드립니다.</p>
                    {etnews_image_html}
                    <p>광고 페이지가 제거된 파일입니다.</p>
                    <br>
                    <p>이 이메일은 자동으로 발송되었습니다.</p>
                    <p style="color: #666; font-size: 0.9em;">
                        이 서비스는 오픈소스 프로젝트로 운영됩니다:
                        <a href="https://github.com/your-username/your-repo" style="color: #0066cc;">GitHub 프로젝트 보기</a>
                    </p>
                    <hr>
                    <small>
                        문의사항이 있으시면 {self.config.ADMIN_EMAIL}으로 연락주세요.<br>
                        이 뉴스레터를 더 이상 받고 싶지 않으시면 <a href="{unsubscribe_url}" style="color: #666;">여기</a>를 클릭하세요.
                    </small>
                </body>
            </html>
            """
        return body

    def _attach_pdf(self, msg: MIMEMultipart, pdf_path: str, pdf_type: str = "etnews", itfind_info: Optional["WeeklyTrend"] = None):
        """PDF 파일을 이메일에 첨부 (경로 기반, 하위호환용)

        Args:
            msg: 이메일 메시지 객체
            pdf_path: PDF 파일 경로
            pdf_type: PDF 타입 ("etnews" 또는 "itfind")
            itfind_info: ITFIND 정보 (한국어 파일명 생성용)
        """
        try:
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()
            etnews_filename = os.path.basename(pdf_path) if pdf_type == "etnews" else None
            self._attach_pdf_from_bytes(
                msg, pdf_data, pdf_type=pdf_type,
                itfind_info=itfind_info, etnews_filename=etnews_filename,
            )
        except Exception as e:
            logger.error(f"PDF 파일 첨부 실패: {e}")
            raise

    def _attach_pdf_from_bytes(
        self,
        msg: MIMEMultipart,
        pdf_data: bytes,
        pdf_type: str = "etnews",
        itfind_info: Optional["WeeklyTrend"] = None,
        etnews_filename: Optional[str] = None,
    ):
        """이미 로드된 PDF 바이트를 이메일에 첨부 (공유 자산용)

        Args:
            msg: 이메일 메시지 객체
            pdf_data: PDF 파일 바이트
            pdf_type: PDF 타입 ("etnews" 또는 "itfind")
            itfind_info: ITFIND 정보 (한국어 파일명 생성용)
            etnews_filename: 전자신문 PDF 파일명 (pdf_type="etnews"일 때 필수)
        """
        try:
            # PDF 첨부 파일 생성
            pdf_attachment = MIMEApplication(pdf_data, _subtype="pdf")

            # 파일명 결정
            if pdf_type == "itfind":
                # 한국어 파일명 생성 (RFC 2231 인코딩)
                korean_filename, ascii_filename = generate_korean_filename(itfind_info)

                # RFC 2231 인코딩: email.utils.encode_rfc2231 사용
                # 반환값 형식: "utf-8''%EC%A3%BC%EA%B8%B0%EB%8F%99..."
                params_string = email.utils.encode_rfc2231(korean_filename, charset='utf-8')

                # Content-Disposition 헤더 생성
                # format: attachment; filename*=utf-8''%EC%A3%BC...
                disposition = f"attachment; filename*={params_string}"
                pdf_attachment.add_header('Content-Disposition', disposition)

                filename_display = f"{korean_filename} ({ascii_filename})"
            else:
                # 전자신문: 기존 방식 사용
                filename = etnews_filename or "etnews.pdf"
                pdf_attachment.add_header('Content-Transfer-Encoding', 'base64')
                pdf_attachment.add_header(
                    "Content-Disposition",
                    f"attachment; filename=\"{filename}\""
                )
                filename_display = filename

            msg.attach(pdf_attachment)
            logger.info(f"PDF 파일 첨부 완료: {filename_display} ({len(pdf_data):,} bytes)")

        except Exception as e:
            logger.error(f"PDF 파일 첨부 실패: {e}")
            raise

    def _prepare_shared_assets(
        self,
        pdf_path: str,
        subject: str,
        itfind_pdf_path: Optional[str] = None,
        itfind_info: Optional["WeeklyTrend"] = None,
    ) -> dict:
        """[S1] 수신자와 무관한 공통 자산을 1회만 준비.

        수신자가 N명이어도 이미지 추출·PDF 디스크 I/O는 각 1회만 수행됩니다.

        Returns:
            dict — 아래 키 포함:
                subject, itfind_info, is_itfind_only,
                toc_image_bytes, etnews_image_bytes,
                etnews_pdf_data, itfind_pdf_data,
                etnews_filename
        """
        # ITFIND 단독 이메일 판정 (email_workflow.py에서 pdf_path == itfind_pdf_path로 호출)
        is_itfind_only = (
            itfind_pdf_path is not None
            and itfind_info is not None
            and os.path.exists(itfind_pdf_path)
        )

        # ITFIND 목차 이미지 (수요일/단독 모두 해당)
        toc_image_bytes: Optional[bytes] = None
        if itfind_pdf_path and os.path.exists(itfind_pdf_path):
            try:
                from .pdf_image_extractor import extract_toc_page_for_email
                toc_image_bytes = extract_toc_page_for_email(itfind_pdf_path)
                if toc_image_bytes:
                    logger.info("✅ ITFIND 목차 이미지 추출 성공 (1회, 공유)")
                else:
                    logger.info("ITFIND 목차 이미지 추출 실패 (텍스트만 발송)")
            except Exception as e:
                logger.warning(f"목차 이미지 추출 중 오류: {e} (텍스트만 발송)")

        # 전자신문 1페이지 이미지 (전자신문 이메일만)
        etnews_image_bytes: Optional[bytes] = None
        if not is_itfind_only and os.path.exists(pdf_path):
            try:
                from .pdf_image_extractor import extract_first_page_for_email
                etnews_image_bytes = extract_first_page_for_email(pdf_path)
                if etnews_image_bytes:
                    logger.info("✅ 전자신문 1페이지 이미지 추출 성공 (1회, 공유)")
                else:
                    logger.info("전자신문 1페이지 이미지 추출 실패 (텍스트만 발송)")
            except Exception as e:
                logger.warning(f"전자신문 이미지 추출 중 오류: {e} (텍스트만 발송)")

        # PDF 바이트 로딩
        etnews_pdf_data: Optional[bytes] = None
        itfind_pdf_data: Optional[bytes] = None
        etnews_filename: Optional[str] = None

        if is_itfind_only:
            # 단독 모드: pdf_path와 itfind_pdf_path가 동일 경로이므로 1회만 읽음
            with open(itfind_pdf_path, "rb") as f:
                itfind_pdf_data = f.read()
            logger.info(f"ITFIND PDF 로드(단독): {len(itfind_pdf_data):,} bytes")
        else:
            # 전자신문 모드: 전자신문 PDF는 반드시, ITFIND PDF는 수요일만
            if os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    etnews_pdf_data = f.read()
                etnews_filename = os.path.basename(pdf_path)
                logger.info(f"전자신문 PDF 로드: {len(etnews_pdf_data):,} bytes")
            if itfind_pdf_path and os.path.exists(itfind_pdf_path):
                with open(itfind_pdf_path, "rb") as f:
                    itfind_pdf_data = f.read()
                logger.info(f"ITFIND PDF 로드: {len(itfind_pdf_data):,} bytes")

        return {
            "subject": subject,
            "itfind_info": itfind_info,
            "is_itfind_only": is_itfind_only,
            "toc_image_bytes": toc_image_bytes,
            "etnews_image_bytes": etnews_image_bytes,
            "etnews_pdf_data": etnews_pdf_data,
            "itfind_pdf_data": itfind_pdf_data,
            "etnews_filename": etnews_filename,
        }

    def _assemble_message(self, recipient_email: str, shared: dict) -> MIMEMultipart:
        """[S1] 공유 자산을 이용해 수신자별 메시지를 조립.

        수신자별로 달라지는 부분: To 헤더, 본문 내 수신거부 URL.
        나머지는 shared에서 재사용.
        """
        msg = MIMEMultipart('related')
        msg["From"] = self.config.GMAIL_USER
        msg["Subject"] = shared["subject"]
        msg["To"] = recipient_email

        itfind_info = shared["itfind_info"]
        toc_image_bytes = shared["toc_image_bytes"]
        etnews_image_bytes = shared["etnews_image_bytes"]

        # 본문 HTML (수신자별 — 수신거부 토큰 포함)
        body = self._create_email_body(
            recipient_email,
            itfind_info,
            has_toc_image=(toc_image_bytes is not None),
            has_etnews_image=(etnews_image_bytes is not None),
        )
        msg.attach(MIMEText(body, "html", "utf-8"))

        # 전자신문 1페이지 이미지 (inline, CID 참조) — [S3] 포맷 자동 감지 (JPEG 또는 PNG)
        if etnews_image_bytes:
            try:
                subtype, ext = _detect_image_subtype(etnews_image_bytes)
                etnews_image = MIMEImage(etnews_image_bytes, _subtype=subtype)
                etnews_image.add_header('Content-ID', '<etnews_first_page>')
                etnews_image.add_header(
                    'Content-Disposition', 'inline', filename=f'etnews_p1.{ext}'
                )
                msg.attach(etnews_image)
            except Exception as e:
                logger.warning(f"전자신문 이미지 첨부 실패: {e}")

        # ITFIND 목차 이미지 (inline, CID 참조)
        if toc_image_bytes:
            try:
                subtype, ext = _detect_image_subtype(toc_image_bytes)
                toc_image = MIMEImage(toc_image_bytes, _subtype=subtype)
                toc_image.add_header('Content-ID', '<toc_image>')
                toc_image.add_header(
                    'Content-Disposition', 'inline', filename=f'toc.{ext}'
                )
                msg.attach(toc_image)
            except Exception as e:
                logger.warning(f"목차 이미지 첨부 실패: {e}")

        # PDF 첨부 (공유 bytes 재사용)
        if shared["is_itfind_only"]:
            self._attach_pdf_from_bytes(
                msg, shared["itfind_pdf_data"],
                pdf_type="itfind", itfind_info=itfind_info,
            )
        else:
            if shared["etnews_pdf_data"] is not None:
                self._attach_pdf_from_bytes(
                    msg, shared["etnews_pdf_data"],
                    pdf_type="etnews",
                    etnews_filename=shared["etnews_filename"],
                )
            if shared["itfind_pdf_data"] is not None:
                self._attach_pdf_from_bytes(
                    msg, shared["itfind_pdf_data"],
                    pdf_type="itfind", itfind_info=itfind_info,
                )

        return msg

    def _open_smtp_connection(self) -> smtplib.SMTP:
        """[S2] SMTP 연결 수립 (TLS + LOGIN). 초기 실패 시 SMTP_MAX_RETRIES만큼 재시도.

        Returns:
            로그인까지 완료된 smtplib.SMTP 객체
        Raises:
            Exception — 최대 재시도 초과 시
        """
        import time as _time
        max_retries = self.config.SMTP_MAX_RETRIES
        last_err: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                server = smtplib.SMTP(self.config.GMAIL_SMTP_SERVER, self.config.GMAIL_SMTP_PORT)
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.config.GMAIL_USER, self.config.GMAIL_APP_PASSWORD)
                logger.info(f"SMTP 연결 수립 성공 (시도 {attempt}/{max_retries})")
                return server
            except Exception as e:
                last_err = e
                logger.warning(f"SMTP 연결 실패 (시도 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    _time.sleep(self.config.SMTP_RETRY_DELAY)
        raise Exception(f"SMTP 연결 최대 재시도 초과: {last_err}")

    def _send_on_server(
        self,
        server: smtplib.SMTP,
        msg: MIMEMultipart,
        to_emails: List[str],
    ) -> smtplib.SMTP:
        """[S2] 기존 SMTP 연결로 전송. 연결이 끊어졌으면 1회 재연결 후 재전송.

        Returns:
            사용(또는 교체)된 SMTP 객체 — 호출자가 이후 재사용
        Raises:
            Exception — 재연결·재전송 모두 실패 시
        """
        try:
            server.send_message(msg, to_addrs=to_emails)
            return server
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ConnectionResetError) as e:
            logger.warning(f"SMTP 연결 끊김 감지 ({e.__class__.__name__}), 재연결 후 재시도")
            try:
                server.close()
            except Exception:
                pass
            server = self._open_smtp_connection()
            server.send_message(msg, to_addrs=to_emails)
            return server

    def _send_via_smtp(self, msg: MIMEMultipart, to_emails: List[str]):
        """SMTP 서버를 통해 이메일 전송 (단일 수신자 경로 호환용)"""
        max_retries = self.config.SMTP_MAX_RETRIES
        retry_count = 0

        while retry_count < max_retries:
            try:
                # SMTP 서버 연결
                server = smtplib.SMTP(
                    self.config.GMAIL_SMTP_SERVER, self.config.GMAIL_SMTP_PORT
                )
                server.ehlo()

                # TLS 보안 연결
                server.starttls()
                server.ehlo()

                # 로그인
                server.login(self.config.GMAIL_USER, self.config.GMAIL_APP_PASSWORD)

                # 이메일 전송
                server.send_message(msg)

                # 연결 종료
                server.quit()

                logger.info(f"SMTP 전송 성공 (시도 {retry_count + 1}/{max_retries})")
                return

            except smtplib.SMTPException as e:
                retry_count += 1
                logger.warning(
                    f"SMTP 전송 실패 (시도 {retry_count}/{max_retries}): {e}"
                )

                if retry_count >= max_retries:
                    raise Exception(f"SMTP 전송 최대 재시도 초과: {e}")

                # 재시도 대기
                import time
                time.sleep(self.config.SMTP_RETRY_DELAY)

            except Exception as e:
                logger.error(f"SMTP 연결 중 예상치 못한 오류: {e}")
                raise


def send_pdf_email(
    pdf_path: str, recipient: Optional[str] = None, subject: Optional[str] = None
) -> bool:
    """
    PDF 이메일 전송 메인 함수 (단일 수신자)

    Args:
        pdf_path: 전송할 PDF 파일 경로
        recipient: 수신자 이메일
        subject: 이메일 제목

    Returns:
        전송 성공 여부
    """
    sender = EmailSender()
    return sender.send_email(pdf_path, recipient, subject)


def send_pdf_bulk_email(
    pdf_path: str,
    subject: Optional[str] = None,
    test_mode: bool = False,
    itfind_pdf_path: Optional[str] = None,
    itfind_info: Optional["WeeklyTrend"] = None
) -> tuple[bool, List[str]]:
    """
    PDF 이메일 전송 메인 함수 (다중 수신자 개별 전송)

    Args:
        pdf_path: 전송할 PDF 파일 경로 (전자신문)
        subject: 이메일 제목
        test_mode: True면 테스트 모드 (admin@example.com에게만 발송)
        itfind_pdf_path: ITFIND 주간기술동향 PDF 경로 (수요일만, Optional)
        itfind_info: ITFIND 주간기술동향 정보 (Optional)

    Returns:
        (전송 성공 여부, 성공한 수신인 이메일 리스트)
    """
    sender = EmailSender()
    return sender.send_bulk_email(pdf_path, subject, test_mode, itfind_pdf_path, itfind_info)


if __name__ == "__main__":
    # 테스트
    import sys

    if len(sys.argv) > 1:
        test_pdf_path = sys.argv[1]
        success = send_pdf_email(test_pdf_path)
        if success:
            print("이메일 전송 성공")
        else:
            print("이메일 전송 실패")
    else:
        print("사용법: python email_sender.py <pdf_path>")
