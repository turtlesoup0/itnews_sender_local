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

            # 각 수신자에게 개별 전송
            success_emails = []
            fail_count = 0

            for recipient in recipients:
                try:
                    # 개인화된 이메일 메시지 생성
                    msg = self._create_message(
                        pdf_path,
                        [recipient.email],
                        subject,
                        use_bcc=False,
                        recipient_email=recipient.email,
                        itfind_pdf_path=itfind_pdf_path,
                        itfind_info=itfind_info
                    )

                    # SMTP 서버 연결 및 전송
                    self._send_via_smtp(msg, [recipient.email])

                    success_emails.append(recipient.email)
                    logger.info(f"이메일 전송 완료: {recipient.email} ({len(success_emails)}/{len(recipients)})")

                except Exception as e:
                    fail_count += 1
                    logger.error(f"이메일 전송 실패: {recipient.email} - {e}")

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

        # 전자신문 1페이지 이미지 첨부 (inline, CID 참조)
        if etnews_image_bytes:
            try:
                etnews_image = MIMEImage(etnews_image_bytes, _subtype='png')
                etnews_image.add_header('Content-ID', '<etnews_first_page>')
                etnews_image.add_header('Content-Disposition', 'inline', filename='etnews_p1.png')
                msg.attach(etnews_image)
                logger.info("✅ 전자신문 1페이지 이미지 첨부 완료 (CID: etnews_first_page)")
            except Exception as e:
                logger.warning(f"전자신문 이미지 첨부 실패: {e}")

        # ITFIND 목차 이미지 첨부 (inline, CID 참조)
        if toc_image_bytes:
            try:
                toc_image = MIMEImage(toc_image_bytes, _subtype='png')
                toc_image.add_header('Content-ID', '<toc_image>')
                toc_image.add_header('Content-Disposition', 'inline', filename='toc.png')
                msg.attach(toc_image)
                logger.info("✅ ITFIND 목차 이미지 첨부 완료 (CID: toc_image)")
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
        """PDF 파일을 이메일에 첨부

        Args:
            msg: 이메일 메시지 객체
            pdf_path: PDF 파일 경로
            pdf_type: PDF 타입 ("etnews" 또는 "itfind")
            itfind_info: ITFIND 정보 (한국어 파일명 생성용)
        """
        try:
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()

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
                filename = os.path.basename(pdf_path)
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

    def _send_via_smtp(self, msg: MIMEMultipart, to_emails: List[str]):
        """SMTP 서버를 통해 이메일 전송"""
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
