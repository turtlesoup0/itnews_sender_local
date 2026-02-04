# IT 뉴스 PDF 자동 배송 시스템 (로컬 실행 환경)

IT 뉴스 PDF를 매일 자동으로 다운로드하고, 광고 페이지를 제거한 후 이메일로 전송하는 자동화 시스템.
Mac Mini에서 로컬 실행을 주 환경으로, AWS Lambda를 백업으로 운영하는 듀얼 환경 구조.

## 주요 기능

- **전자신문 자동 발송**: 매일 06:00 KST에 PDF 다운로드, 광고 제거 후 이메일 전송
- **ITFIND 주간기술동향**: 수요일에 RSS 피드에서 최신호를 자동 조회하여 함께 첨부
  - 컨텐츠 신선도 검증 (7일 이내 발행된 콘텐츠만 발송)
  - 한국어 첨부파일명 (예: `주기동260204-2203호.pdf`)
  - PDF 목차 페이지 이미지를 이메일 본문에 표시
- **iCloud Drive 자동 업로드**: 처리된 PDF를 iCloud Drive에 연/월별 폴더 구조로 자동 복사 (로컬 전용)
- **듀얼 스토리지**: SQLite (로컬) / DynamoDB (AWS) 자동 전환
- **수신인 관리**: 활성 수신인 목록 관리, 개인화된 수신거부 링크 포함
- **신문 미발행일 감지**: 발행되지 않은 날에는 자동으로 스킵
- **구독 만료 알림**: PDF 서비스 구독 종료일 7일 전 관리자 알림

## 시스템 아키텍처

```
Mac Mini (Primary)                    AWS Lambda (Backup)
┌─────────────────────┐               ┌─────────────────────┐
│ launchd (06:00 KST) │               │ EventBridge (비활성) │
│        ↓            │               │        ↓            │
│  run_daily.py       │               │  lambda_handler.py  │
│        ↓            │               │        ↓            │
│  lambda_handler.py  │               │  StorageBackend     │
│        ↓            │               │  (DynamoDB)         │
│  StorageBackend     │               └─────────────────────┘
│  (SQLite)           │
│        ↓            │
│  iCloud Drive 복사  │
└─────────────────────┘
         │
         ↓
  ┌──────────────┐
  │  공통 로직    │
  │ • Playwright  │  →  PDF 다운로드
  │ • pypdf       │  →  광고 제거
  │ • Gmail SMTP  │  →  이메일 전송
  └──────────────┘
```

## 프로젝트 구조

```
itnews_sender/
├── run_daily.py                       # 로컬 실행 엔트리포인트
├── lambda_handler.py                  # Lambda/로컬 공용 핸들러
├── lambda_itfind_downloader.py        # ITFIND 다운로더
├── com.itnews.sender.plist            # launchd 스케줄 정의
├── Dockerfile                         # Lambda 컨테이너 이미지
├── requirements.txt                   # 공통 의존성
├── requirements-aws.txt               # AWS Lambda 추가 의존성
├── src/
│   ├── config.py                      # 설정 관리 (환경변수/.env)
│   ├── scraper.py                     # Playwright PDF 다운로드
│   ├── pdf_processor.py               # PDF 광고 제거
│   ├── pdf_image_extractor.py         # PDF 페이지 이미지 추출 (PyMuPDF)
│   ├── email_sender.py                # Gmail SMTP 전송
│   ├── itfind_scraper.py              # ITFIND RSS/PDF 스크래퍼
│   ├── structured_logging.py          # 로깅 (콘솔+파일 로테이션)
│   ├── delivery_tracker.py            # 수신인별 발송 이력
│   ├── execution_tracker.py           # 멱등성 보장 (일 1회)
│   ├── failure_tracker.py             # 실패 추적 (3회 초과 시 스킵)
│   ├── storage/
│   │   ├── base.py                    # StorageBackend 추상 인터페이스
│   │   ├── sqlite_backend.py          # SQLite 구현 (로컬)
│   │   ├── dynamodb_backend.py        # NoSQL 구현 (클라우드)
│   │   └── factory.py                 # 환경별 백엔드 팩토리
│   ├── recipients/
│   │   ├── dynamodb_client.py         # StorageBackend 호환 래퍼
│   │   ├── models.py                  # 수신인 데이터 모델
│   │   └── recipient_manager.py       # 수신인 관리 로직
│   ├── workflow/
│   │   ├── execution.py               # 멱등성/실패 제한 체크
│   │   ├── pdf_workflow.py            # PDF 다운로드+처리 워크플로우
│   │   ├── email_workflow.py          # 이메일 전송 워크플로우
│   │   └── icloud_workflow.py         # iCloud Drive 복사 (로컬 전용)
│   ├── utils/
│   │   └── notification.py            # 관리자 알림
│   └── api/
│       └── unsubscribe_handler.py     # 수신거부 (Lambda Function URL)
├── scripts/
│   ├── setup_launchd.sh               # launchd 등록/해제/상태
│   ├── manage_recipients.py           # 수신인 관리 CLI
│   └── ...                            # AWS 설정 스크립트
├── tests/                             # 단위 테스트 및 통합 테스트
│   ├── test_content_freshness.py      # 컨텐츠 신선도 검증 테스트
│   ├── test_attachment_filename.py    # 첨부파일명 생성 테스트
│   ├── test_pdf_image_extractor.py    # PDF 이미지 추출 테스트
│   └── test_email_body.py             # 이메일 본문 생성 테스트
├── docs/                              # 프로젝트 문서
│   ├── ITFIND_WEEKLY_TRENDS_API.md    # ITFIND API 문서
│   ├── IAM_POLICY_REVIEW.md           # IAM 정책 검토
│   ├── LAMBDA_TEST_EVENTS.md          # Lambda 테스트 이벤트
│   └── PARAMETER_STORE_SETUP.md       # Parameter Store 설정 가이드
├── data/                              # SQLite DB (gitignore)
└── logs/                              # 로그 파일 (gitignore)
```

## 설치 및 설정

### 로컬 환경 (Mac Mini)

```bash
# 1. 가상환경 생성 및 의존성 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Playwright 브라우저 설치
playwright install chromium

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에 credential 입력:
#   ETNEWS_USER_ID, ETNEWS_PASSWORD
#   GMAIL_USER, GMAIL_APP_PASSWORD

# 4. 테스트 실행
python run_daily.py --mode test --skip-idempotency
```

### launchd 스케줄러 등록 (매일 06:00 자동 실행)

```bash
./scripts/setup_launchd.sh install     # 등록
./scripts/setup_launchd.sh status      # 상태 확인
./scripts/setup_launchd.sh logs        # 로그 확인
./scripts/setup_launchd.sh uninstall   # 해제
```

### 수신인 관리

```bash
python scripts/manage_recipients.py add user@example.com "사용자 이름"
python scripts/manage_recipients.py list-active
python scripts/manage_recipients.py remove user@example.com
```

## 실행 모드

| 모드 | 명령어 | 수신인 | 발송 이력 |
|------|--------|--------|-----------|
| **TEST** | `python run_daily.py` | 관리자만 | 기록 안 함 |
| **OPR** | `python run_daily.py --mode opr` | 전체 활성 수신인 | 기록 |

```bash
# 같은 날 재실행 (멱등성 체크 스킵)
python run_daily.py --mode test --skip-idempotency
```

## iCloud Drive 업로드

로컬 실행 시 처리된 PDF가 자동으로 iCloud Drive에 복사됩니다.

- 경로: `~/Library/Mobile Documents/com~apple~CloudDocs/전자신문/YY/YYMM/`
- 예: `전자신문/26/2602/etnews_20260202_processed.pdf`
- Lambda 환경에서는 자동 스킵
- 실패해도 메인 플로우에 영향 없음

## 기술 스택

- **언어**: Python 3.11+
- **웹 스크래핑**: Playwright (헤드리스 Chromium)
- **PDF 처리**: pypdf, PyMuPDF (페이지 이미지 추출)
- **이메일**: Gmail SMTP (smtplib)
- **스토리지**: SQLite (로컬) / DynamoDB (Lambda)
- **스케줄러**: launchd (로컬) / EventBridge (Lambda)
- **보안**: HMAC-SHA256 (수신거부 토큰), Parameter Store (Lambda)
- **로깅**: RotatingFileHandler (로컬) / CloudWatch (Lambda)

## AWS 백업 실행

Mac Mini 장애 시 AWS Lambda로 전환:

```bash
# EventBridge 재활성화
aws events enable-rule --name etnews-daily-trigger --region ap-northeast-2

# 또는 수동 Lambda 호출
aws lambda invoke --function-name etnews-pdf-sender \
  --payload '{"mode":"opr","skip_idempotency":true}' \
  --region ap-northeast-2 /tmp/result.json
```

복구 후:

```bash
# EventBridge 다시 비활성화
aws events disable-rule --name etnews-daily-trigger --region ap-northeast-2
```

## 문제 해결

### Gmail SMTP 인증 실패
1. Google 계정 > 보안 > 2단계 인증 활성화
2. 앱 비밀번호 생성 (16자리)
3. `.env`의 `GMAIL_APP_PASSWORD`에 설정

### launchd 작업 미실행
```bash
plutil -lint com.itnews.sender.plist     # plist 문법 검증
launchctl start com.itnews.sender        # 수동 실행
cat logs/launchd_stderr.log              # 에러 확인
```

### Playwright 브라우저 실행 실패
```bash
playwright install chromium              # Chromium 재설치
```

## 라이선스

MIT License

## 면책 조항

이 프로젝트는 개인적인 자동화 목적으로 제작되었습니다. 사용자는 해당 뉴스 서비스의 이용 약관을 준수할 책임이 있습니다.
