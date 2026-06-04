"""
Link rewriter — turns every outbound HTTP(S) link into a signed, tracked URL
that routes through the /r redirect endpoint so clicks get logged before the
recipient lands on the real destination.

Also handles the pitch-page CTA: when a campaign has pitch_page_url set, the
rewriter appends a clean call-to-action at the end of the body, with the link
itself already tracked. Both responsibilities live in one place because they
share the same URL-signing primitive.

Pure module — no DB, no network. Safe to call from any send path.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
from typing import Optional
from urllib.parse import urlencode

from backend.config import Config

logger = logging.getLogger(__name__)

# Schemes we WILL rewrite. Everything else (mailto:, tel:, javascript:, anchor
# links, relative URLs without a scheme) stays untouched — those have different
# semantics that would break if we wrapped them.
_TRACKABLE_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)

# Match <a ... href="..."> across attribute ordering and quoting. Captures
# (everything before the href value, the value, everything after).
_HREF_RE = re.compile(
    r'(<a\b[^>]*?\bhref\s*=\s*")([^"]+)("[^>]*>)',
    re.IGNORECASE,
)


def _b64url(s: str) -> str:
    """URL-safe base64 without padding, suitable for query-string values."""
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> str:
    """Reverse of _b64url. Pads back to a multiple of 4 before decoding."""
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad).decode("utf-8")


def _sign(payload: str) -> str:
    """HMAC-SHA256 of payload using LINK_TRACKING_SECRET, hex-encoded."""
    secret = (Config.LINK_TRACKING_SECRET or "").encode("utf-8")
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_signature_payload(eid: str, encoded_url: str, bjid: str = "0") -> str:
    """
    Canonical payload the signature covers: eid|encoded_url|bjid.

    bjid is "0" when there's no batch attribution — same convention as eid.
    Including it in the signature stops tampering (e.g. swapping someone else's
    bjid to take credit for a click).
    """
    return f"{eid}|{encoded_url}|{bjid}"


def verify_signature(eid: str, encoded_url: str, supplied_sig: str, bjid: str = "0") -> bool:
    """Constant-time HMAC comparison for the /r endpoint."""
    expected = _sign(make_signature_payload(eid, encoded_url, bjid))
    return hmac.compare_digest(expected, supplied_sig or "")


def tracked_url(
    enrollment_id: Optional[int],
    original_url: str,
    batch_job_id: Optional[int] = None,
) -> str:
    """
    Build the signed redirect URL for a single original link.

    Both enrollment_id and batch_job_id are optional — sequences pass the
    enrollment_id (clicks attribute to a specific enrollment/contact); batch
    jobs pass batch_job_id (clicks attribute to the job + can be linked to
    the contact via recipient email if needed). A given send carries one or
    the other, not both.
    """
    if not original_url or not _TRACKABLE_SCHEME_RE.match(original_url):
        return original_url  # not trackable; hand back unchanged
    eid = str(enrollment_id) if enrollment_id is not None else "0"
    bjid = str(batch_job_id) if batch_job_id is not None else "0"
    encoded = _b64url(original_url)
    sig = _sign(make_signature_payload(eid, encoded, bjid))
    params: dict[str, str] = {"eid": eid, "u": encoded, "s": sig}
    if bjid != "0":
        params["bjid"] = bjid
    qs = urlencode(params)
    base = (Config.LINK_TRACKING_BASE_URL or "").rstrip("/")
    return f"{base}/r?{qs}"


def decode_tracked_url(encoded_url_param: str) -> Optional[str]:
    """Reverse the base64 URL parameter back to the original destination."""
    try:
        decoded = _b64url_decode(encoded_url_param)
        # Sanity check — we should never have signed a non-http URL.
        if not _TRACKABLE_SCHEME_RE.match(decoded):
            return None
        return decoded
    except Exception:
        return None


def rewrite_links_in_body(
    html_body: str,
    enrollment_id: Optional[int],
    batch_job_id: Optional[int] = None,
) -> str:
    """
    Walk every <a href="..."> in the body and replace HTTP(S) hrefs with their
    tracked equivalents. Non-http schemes pass through untouched.

    Idempotent on our own tracked URLs (they're already https://, so they get
    re-wrapped — but a second wrap would double-encode and the /r endpoint
    would reject it). To prevent this, we skip rewriting any URL that already
    points at our LINK_TRACKING_BASE_URL/r endpoint.
    """
    if not html_body:
        return html_body
    base = (Config.LINK_TRACKING_BASE_URL or "").rstrip("/")
    self_redirect_prefix = f"{base}/r?" if base else None

    def _sub(m: re.Match[str]) -> str:
        prefix, href, suffix = m.group(1), m.group(2), m.group(3)
        if self_redirect_prefix and href.startswith(self_redirect_prefix):
            return m.group(0)  # already tracked — leave alone
        return f"{prefix}{tracked_url(enrollment_id, href, batch_job_id)}{suffix}"

    return _HREF_RE.sub(_sub, html_body)


# ── Pitch-page CTA appending ─────────────────────────────────────────────────

# Tasteful CTA block. Inline styles only so it renders consistently across
# Gmail / Outlook / Apple Mail without depending on a stylesheet.
_CTA_TEMPLATE = (
    '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">'
    '<a href="{url}" '
    'style="display:inline-block;padding:10px 18px;'
    'background:#0f172a;color:#ffffff;text-decoration:none;'
    'border-radius:6px;font-family:Arial,Helvetica,sans-serif;'
    'font-size:14px;font-weight:600;">'
    '{label}'
    '</a></div>'
)


def append_pitch_page_cta(
    html_body: str,
    pitch_page_url: Optional[str],
    pitch_page_label: Optional[str],
    enrollment_id: Optional[int],
    batch_job_id: Optional[int] = None,
) -> str:
    """
    Append a tracked CTA at the very end of the email body if the campaign has
    a pitch page configured. Returns the body unchanged when there's no pitch
    page URL — opt-in feature.
    """
    if not pitch_page_url or not _TRACKABLE_SCHEME_RE.match(pitch_page_url):
        return html_body
    label = (pitch_page_label or "Learn more").strip() or "Learn more"
    tracked = tracked_url(enrollment_id, pitch_page_url, batch_job_id)
    cta = _CTA_TEMPLATE.format(url=tracked, label=label)
    return (html_body or "") + cta


def render_with_tracking(
    html_body: str,
    enrollment_id: Optional[int],
    pitch_page_url: Optional[str] = None,
    pitch_page_label: Optional[str] = None,
    batch_job_id: Optional[int] = None,
) -> str:
    """
    Single entry point used by the send paths. Rewrites in-body links first,
    then appends the pitch-page CTA. Order matters: doing it this way means
    the appended CTA is already a tracked URL and doesn't get wrapped twice.

    Send paths pass exactly one attribution id: sequences pass enrollment_id;
    batch jobs pass batch_job_id. Both end up in email_events on click.
    """
    body = rewrite_links_in_body(html_body or "", enrollment_id, batch_job_id)
    body = append_pitch_page_cta(body, pitch_page_url, pitch_page_label, enrollment_id, batch_job_id)
    return body
