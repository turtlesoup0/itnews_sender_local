# SPEC-ITFIND-001: ITFIND Weekly Trends Email Improvements

**Status**: Draft
**Created**: 2026-02-04
**Author**: MoAI (manager-spec)
**Priority**: High (production issue)

---

## 1. Background

2026-02-04 (Wednesday), the automated ITFIND weekly tech trends email was sent with **last week's content** because the new issue had not yet been published. Additionally, two UX improvements are needed for the attachment filename and email body content.

### Current Architecture

```
lambda_handler.py (is_wednesday check)
  -> src/workflow/pdf_workflow.py (download_itfind_pdf)
    -> lambda_itfind_downloader.py (download_itfind_pdf async)
      -> get_latest_weekly_trend_from_rss() (RSS fetch)
      -> extract_streamdocs_id_from_detail_page()
      -> download_pdf_direct()
    -> src/workflow/email_workflow.py (send_emails)
      -> src/email_sender.py (EmailSender._create_message)
        -> _create_email_body() (HTML body)
        -> _attach_pdf() (PDF attachment)
```

---

## 2. Requirements (EARS Format)

### REQ-1: Content Freshness Validation

**When** the system fetches the latest ITFIND weekly trends from RSS,
**the system shall** compare the publish_date of the fetched content with the current date (KST),
**and** if the publish_date is more than 7 days old,
**the system shall** skip sending the ITFIND email and log the skip reason.

**Rationale**: RSS may still return last week's issue if the new one hasn't been published yet. On 2026-02-04, the system sent issue 2203 (published 2026-01-28) because no freshness check existed.

**Acceptance Criteria**:
- AC-1.1: If `publish_date` is within 7 days of current date (KST), proceed with sending
- AC-1.2: If `publish_date` is older than 7 days, skip sending and log: `"ITFIND skipped: stale content (publish_date={date}, today={today})"`
- AC-1.3: Previous delivery tracking (idempotency) continues to work correctly
- AC-1.4: Admin is NOT notified for skipped stale content (this is expected behavior)
- AC-1.5: The staleness threshold (7 days) should be configurable in `src/config.py`

### REQ-2: Korean Attachment Filename

**When** the system attaches an ITFIND PDF to the email,
**the system shall** use the filename format `주기동YYMMDD-xxxx호.pdf`
where `YYMMDD` is the 2-digit year + month + day and `xxxx` is the issue number.

**Rationale**: Current filename `itfind_20260204.pdf` is generic and doesn't convey content information to the recipient.

**Acceptance Criteria**:
- AC-2.1: Filename follows format `주기동YYMMDD-xxxx호.pdf` (e.g., `주기동260204-2203호.pdf`)
- AC-2.2: Korean characters are properly encoded using RFC 2231 (`filename*=UTF-8''...`) for email clients that support it
- AC-2.3: ASCII fallback filename is provided via `filename=` parameter for older clients
- AC-2.4: Gmail web UI, Apple Mail, and Outlook display the Korean filename correctly

### REQ-3: PDF Table of Contents Image and Topics in Email Body

**When** the system composes the ITFIND email body,
**the system shall** include:
1. An inline image of PDF page 3 (table of contents page)
2. Main topics extracted from the PDF content as text

**Rationale**: Recipients currently see only topic names in the email body. Including the table of contents page image provides visual context and makes the newsletter more informative.

**Acceptance Criteria**:
- AC-3.1: PDF page 3 is rendered as a PNG image (resolution: 200 DPI, width ~600px for email compatibility)
- AC-3.2: Image is embedded inline using CID (Content-ID) reference, not base64 data URI (better email client compatibility)
- AC-3.3: Topics are displayed as a bulleted list below the image
- AC-3.4: If page 3 extraction fails, the email is still sent with topics text only (graceful degradation)
- AC-3.5: Image file size is optimized to be under 500KB (JPEG quality 85 or PNG with optimization)

---

## 3. Implementation Plan

### 3.1 REQ-1: Content Freshness Validation

#### Files to Modify

| File | Change |
|------|--------|
| `src/config.py` | Add `ITFIND_STALENESS_DAYS = 7` constant |
| `lambda_itfind_downloader.py` | Add freshness validation in `download_itfind_pdf()` |
| `lambda_itfind_downloader.py` | Parse actual pubDate from RSS instead of using current date |
| `src/workflow/pdf_workflow.py` | Handle `None` return from freshness skip |

#### Implementation Detail

**Step 1: Add configuration** (`src/config.py`)

Add `ITFIND_STALENESS_DAYS = 7` constant to ConfigClass.

**Step 2: Add `is_content_fresh()` function** (`lambda_itfind_downloader.py`)

- Accepts `publish_date` (str, YYYY-MM-DD) and `staleness_days` (int)
- Compares with current KST date
- Returns `True` if content age <= staleness_days
- Handles invalid date formats gracefully (returns `False`)

**Step 3: Integrate freshness check** into `download_itfind_pdf()`:
- After RSS fetch, before StreamDocs download
- If stale, log reason and return `None`

**Step 4: Parse actual pubDate from RSS** in `get_latest_weekly_trend_from_rss()`:
- Current code uses `datetime.now()` as approximation (line 105)
- Parse RFC 822 pubDate from RSS item element instead
- This is critical for accurate freshness validation

---

### 3.2 REQ-2: Korean Attachment Filename

#### Files to Modify

| File | Change |
|------|--------|
| `src/email_sender.py` | Modify `_attach_pdf()` to accept `itfind_info` parameter |
| `src/email_sender.py` | Modify `_create_message()` to pass `itfind_info` to `_attach_pdf()` |

#### Implementation Detail

**Step 1: Update `_attach_pdf()` signature** to accept optional `itfind_info`

**Step 2: Generate Korean filename**:
- Format: `주기동{YYMMDD}-{issue_number}호.pdf`
- ASCII fallback: `itfind_{YYMMDD}-{issue_number}.pdf`
- Use `email.utils.encode_rfc2231()` or `set_param(charset='utf-8')` for proper encoding

**Step 3: Update `_create_message()`**:
- Pass `itfind_info` to `_attach_pdf()` when attaching ITFIND PDF

---

### 3.3 REQ-3: PDF TOC Image and Topics in Email Body

#### Files to Modify/Create

| File | Change |
|------|--------|
| `src/pdf_image_extractor.py` | **NEW** - Extract PDF page as image using PyMuPDF |
| `src/email_sender.py` | Modify `_create_message()` to embed TOC image via CID |
| `src/email_sender.py` | Modify `_create_email_body()` to include `<img src="cid:toc_image">` |

#### Implementation Detail

**Step 1: Create `src/pdf_image_extractor.py`**:
- `extract_page_as_image(pdf_path, page_number=2, dpi=200, max_width=600)` -> `Optional[bytes]`
- Uses PyMuPDF (`fitz`) to render page to pixmap
- Auto-resize if width > max_width
- Returns PNG bytes, graceful `None` on failure

**Step 2: Update `_create_message()`**:
- Call `extract_page_as_image()` for ITFIND PDFs
- Create `MIMEMultipart('related')` container for inline image
- Attach image as `MIMEImage` with `Content-ID: <toc_image>`

**Step 3: Update `_create_email_body()`**:
- Add `has_toc_image` parameter
- Insert `<img src="cid:toc_image">` section when image available
- Image displayed above topics list with border styling

**Step 4: Add PyMuPDF dependency**: `pip install PyMuPDF`

---

## 4. Dependency Analysis

### New Dependencies

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| PyMuPDF | >=1.24.0 | PDF page rendering to image | ~30MB |

### File Impact Matrix

| File | REQ-1 | REQ-2 | REQ-3 |
|------|-------|-------|-------|
| `src/config.py` | Modify | - | - |
| `lambda_itfind_downloader.py` | Modify | - | - |
| `src/workflow/pdf_workflow.py` | Minor | - | - |
| `src/email_sender.py` | - | Modify | Modify |
| `src/pdf_image_extractor.py` | - | - | **New** |

---

## 5. Risk Assessment

### REQ-1: Content Freshness

| Risk | Impact | Mitigation |
|------|--------|------------|
| RSS pubDate format varies | High | Parse with multiple format fallbacks |
| RSS pubDate missing | Medium | Fall back to current date (existing behavior) |
| Timezone mismatch | Low | Both RSS and local use KST explicitly |

### REQ-2: Korean Filename

| Risk | Impact | Mitigation |
|------|--------|------------|
| Email client doesn't support RFC 2231 | Medium | ASCII fallback filename provided |
| Gmail strips Korean characters | Low | Test with actual Gmail sending |
| `issue_number` format varies | Low | Strip non-numeric characters |

### REQ-3: TOC Image

| Risk | Impact | Mitigation |
|------|--------|------------|
| PyMuPDF not available | High | Graceful degradation (skip image) |
| PDF has fewer than 3 pages | Low | Check page count before extraction |
| Image too large for email | Medium | Max 500KB limit with JPEG fallback |
| CID image blocked by email client | Low | Alt text provided as fallback |

---

## 6. Test Plan

### 6.1 Unit Tests

#### T-1: Content Freshness Validation (`tests/test_content_freshness.py`)

| Test ID | Description | Input | Expected Output |
|---------|-------------|-------|-----------------|
| T-1.1 | Fresh content (today) | `publish_date="2026-02-04"` | `True` |
| T-1.2 | Fresh content (3 days old) | `publish_date="2026-02-01"` | `True` |
| T-1.3 | Fresh content (exactly 7 days) | `publish_date="2026-01-28"` | `True` |
| T-1.4 | Stale content (8 days old) | `publish_date="2026-01-27"` | `False` |
| T-1.5 | Stale content (30 days old) | `publish_date="2025-01-05"` | `False` |
| T-1.6 | Invalid date format | `publish_date="invalid"` | `False` |
| T-1.7 | Empty date string | `publish_date=""` | `False` |
| T-1.8 | Custom staleness threshold | `staleness_days=3, age=5` | `False` |

#### T-2: Korean Filename Generation (`tests/test_attachment_filename.py`)

| Test ID | Description | Input | Expected Output |
|---------|-------------|-------|-----------------|
| T-2.1 | Standard filename | `date=260204, issue=2203` | `주기동260204-2203호.pdf` |
| T-2.2 | Issue number with 호 | `issue_number="2203호"` | Strips existing 호, outputs `2203호` |
| T-2.3 | ASCII fallback | same as T-2.1 | `itfind_260204-2203.pdf` |
| T-2.4 | RFC 2231 encoding | Korean filename | `UTF-8''%EC%A3%BC%EA%B8%B0%EB%8F%99...` |
| T-2.5 | No itfind_info | `itfind_info=None` | Falls back to `itfind_YYYYMMDD.pdf` |

#### T-3: PDF Page Image Extraction (`tests/test_pdf_image_extractor.py`)

| Test ID | Description | Input | Expected Output |
|---------|-------------|-------|-----------------|
| T-3.1 | Extract page 3 as PNG | Valid PDF | PNG bytes, width <= 600px |
| T-3.2 | Extract page 3 as JPEG | Valid PDF | JPEG bytes, quality 85 |
| T-3.3 | PDF with fewer than 3 pages | 2-page PDF | `None` |
| T-3.4 | Corrupted PDF | Invalid file | `None` (no exception raised) |
| T-3.5 | Image size under 500KB | Valid PDF, DPI=200 | `len(bytes) < 512000` |
| T-3.6 | Large page auto-resize | Wide PDF | `width <= 600` |

#### T-4: Email Body Generation (`tests/test_email_body.py`)

| Test ID | Description | Input | Expected Output |
|---------|-------------|-------|-----------------|
| T-4.1 | Body with TOC image | `has_toc_image=True` | Contains `<img src="cid:toc_image">` |
| T-4.2 | Body without TOC image | `has_toc_image=False` | No `<img>` tag |
| T-4.3 | Body with topics | `topics=["AI", "Cloud"]` | Contains both topic strings |
| T-4.4 | Body with image + topics | Both present | Image section above topics |

### 6.2 Integration Tests

#### T-5: End-to-End ITFIND Workflow (`tests/test_itfind_workflow.py`)

| Test ID | Description | Expected Behavior |
|---------|-------------|-------------------|
| T-5.1 | Fresh content (happy path) | PDF downloaded, email composed with TOC image + Korean filename |
| T-5.2 | Stale content | `download_itfind_pdf()` returns `None`, no email sent |
| T-5.3 | RSS unavailable | Falls back to web scraping (existing behavior) |
| T-5.4 | PDF download fails | Graceful failure, etnews still sent (existing behavior) |
| T-5.5 | PyMuPDF not available | Email sent without TOC image, topics text included |

#### T-6: Email Client Compatibility (Manual)

| Test ID | Client | Check Items |
|---------|--------|-------------|
| T-6.1 | Gmail Web | Korean filename display, inline image render |
| T-6.2 | Apple Mail | Korean filename display, inline image render |
| T-6.3 | Outlook Web | Korean filename display, inline image render |

### 6.3 Regression Tests

| Test ID | Description | Validates |
|---------|-------------|-----------|
| T-7.1 | Etnews email unaffected | REQ-1 changes don't break etnews flow |
| T-7.2 | Idempotency still works | Skipped ITFIND doesn't affect execution tracking |
| T-7.3 | Test mode works | Test mode sends to admin only |
| T-7.4 | Failure tracking works | 3+ failures still trigger admin notification |

### 6.4 Test Execution Strategy

```
Phase 1: Unit Tests (automated)
  pytest tests/test_content_freshness.py -v
  pytest tests/test_attachment_filename.py -v
  pytest tests/test_pdf_image_extractor.py -v
  pytest tests/test_email_body.py -v

Phase 2: Integration Tests (automated)
  pytest tests/test_itfind_workflow.py -v

Phase 3: Manual Verification
  python run_daily.py --mode test
  -> Verify in Gmail: filename, TOC image, topics

Phase 4: Production Deployment
  python run_daily.py --mode opr  (next Wednesday)
```

---

## 7. Deployment Checklist

- [ ] Install PyMuPDF: `pip install PyMuPDF`
- [ ] Run unit tests: `pytest tests/ -v`
- [ ] Send test email: `python run_daily.py --mode test`
- [ ] Verify in Gmail web UI:
  - [ ] No email sent if content is stale
  - [ ] Attachment filename shows `주기동YYMMDD-xxxx호.pdf`
  - [ ] TOC image displayed inline in body
  - [ ] Topics listed as text below image
- [ ] Deploy to production (next Wednesday)
- [ ] Monitor first production execution

---

## 8. Rollback Plan

Each requirement is independently revertible:

- **REQ-1**: Remove `is_content_fresh()` call, restore original flow
- **REQ-2**: Revert `_attach_pdf()` to use `itfind_{YYYYMMDD}.pdf`
- **REQ-3**: Remove image extraction, revert `_create_message()` to text-only
