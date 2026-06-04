"""
Gmail OAuth endpoints.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.config import Config

# Google sometimes returns MORE scopes than we requested — e.g. when a user
# already approved gmail.metadata in a previous grant and we now ask for
# gmail.readonly, the consent screen merges the two and the token comes
# back with both. oauthlib's strict scope-equality check then raises
# "Scope has changed from X to Y". This env var tells oauthlib to accept
# the superset silently, which is safe (we trust that what we got covers
# what we asked for).
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    # Read message bodies so we can:
    #   1) Detect replies on sequence threads (we only need 'From' headers,
    #      gmail.metadata would suffice for that alone)
    #   2) Parse DSN bounce messages — requires format=raw on messages.get,
    #      which Gmail explicitly forbids under gmail.metadata. So we ask
    #      for gmail.readonly (which is a superset of gmail.metadata).
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

# Temporary in-memory store: oauth_state -> code_verifier
# Google enforces PKCE for all web flows (since April 2025).
_gmail_pkce: dict[str, str] = {}


def _load_gmail_flow():
    from google_auth_oauthlib.flow import Flow
    return Flow.from_client_config(
        Config.google_client_config(),
        scopes=GMAIL_SCOPES,
        redirect_uri=Config.GMAIL_REDIRECT_URI,
    )


def _oauth_close_page(success: bool, message: str) -> str:
    color  = "#22c55e" if success else "#ef4444"
    status = "connected" if success else "error"
    return f"""<!DOCTYPE html>
<html>
<head><title>Gmail {status}</title></head>
<body style="font-family:monospace;background:#05080f;color:{color};
             display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
  <div style="text-align:center;">
    <p style="font-size:14px;margin-bottom:8px;">{'Connected' if success else 'Failed'}</p>
    <p style="font-size:11px;opacity:0.6;">{message}</p>
  </div>
  <script>
    window.opener && window.opener.postMessage(
      {{type:'gmail-oauth',success:{str(success).lower()},email:{f'"{message}"' if success else 'null'},error:{f'null' if success else f'"{message}"'}}},
      '*'
    );
    setTimeout(() => window.close(), 1200);
  </script>
</body>
</html>"""


@router.get("/gmail")
async def gmail_auth_start():
    """Redirect the browser to Google's OAuth consent screen."""
    try:
        import secrets, hashlib, base64 as _b64
        from fastapi.responses import RedirectResponse

        raw = secrets.token_bytes(32)
        code_verifier  = _b64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        digest         = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = _b64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        flow = _load_gmail_flow()
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )
        _gmail_pkce[state] = code_verifier
        return RedirectResponse(auth_url)
    except Exception as e:
        logger.error(f"Gmail auth start failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/gmail/callback")
async def gmail_auth_callback(code: str, state: str = "", error: Optional[str] = None):
    """Google redirects here after the user approves (or denies) access."""
    from fastapi.responses import HTMLResponse
    if error:
        return HTMLResponse(content=_oauth_close_page(success=False, message=error))
    try:
        from backend.infra.db.gmail_repo import upsert_gmail_token
        flow = _load_gmail_flow()
        verifier = _gmail_pkce.pop(state, None)
        flow.fetch_token(code=code, code_verifier=verifier)
        creds = flow.credentials

        import json, base64
        id_token = getattr(creds, "id_token", None)
        email = None
        if id_token:
            payload = id_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            email = json.loads(base64.urlsafe_b64decode(payload)).get("email")

        if not email:
            import requests as _req
            r = _req.get(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10,
            )
            email = r.json().get("email") if r.ok else None

        if not email:
            return HTMLResponse(content=_oauth_close_page(success=False, message="Could not determine Gmail address"))

        await upsert_gmail_token(
            email=email,
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            token_expiry=creds.expiry,
        )
        logger.info(f"Gmail token stored for {email}")
        return HTMLResponse(content=_oauth_close_page(success=True, message=email))
    except Exception as e:
        logger.error(f"Gmail auth callback failed: {e}", exc_info=True)
        return HTMLResponse(content=_oauth_close_page(success=False, message=str(e)))


@router.get("/gmail/status")
async def gmail_auth_status():
    """Return whether a Gmail account is connected."""
    try:
        from backend.infra.db.gmail_repo import get_gmail_token
        token = await get_gmail_token()
        if not token:
            return {"connected": False, "email": None}
        return {"connected": True, "email": token["email"]}
    except Exception as e:
        logger.error(f"Gmail status check failed: {e}")
        return {"connected": False, "email": None}


@router.get("/gmail/accounts")
async def gmail_list_accounts():
    """Return all connected Gmail/OAuth accounts."""
    try:
        from backend.infra.db.gmail_repo import list_gmail_tokens
        accounts = await list_gmail_tokens()
        return {"accounts": accounts}
    except Exception as e:
        logger.error(f"Gmail list accounts failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})


@router.get("/email/provider")
async def email_provider_info():
    """
    Active outbound-email provider for the send UI. No secrets returned.
    gmail   → UI shows per-account connect/select (account required to queue).
    smtp/resend → server-configured single sender; no account selection needed.
    """
    provider = (Config.EMAIL_PROVIDER or "gmail").lower()
    if provider == "resend":
        from_email = Config.RESEND_FROM_EMAIL or None
    elif provider == "smtp":
        from_email = Config.SMTP_FROM_EMAIL or None
    else:
        from_email = None
    return {
        "provider": provider,
        "from_email": from_email,
        "requires_account": provider == "gmail",
    }


@router.delete("/gmail")
async def gmail_disconnect(email: Optional[str] = None):
    """Remove stored Gmail credentials. If email is provided, removes that specific account."""
    try:
        from backend.infra.db.gmail_repo import get_gmail_token, delete_gmail_token
        if email:
            await delete_gmail_token(email)
        else:
            token = await get_gmail_token()
            if token:
                await delete_gmail_token(token["email"])
        return {"success": True}
    except Exception as e:
        logger.error(f"Gmail disconnect failed: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})
