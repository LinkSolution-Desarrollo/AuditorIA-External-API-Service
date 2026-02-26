"""
OAuth 2.0 Authorization Server endpoints.

Implementa el flujo Authorization Code (con PKCE opcional) y Client Credentials
para que clientes MCP como Claude Code puedan autenticarse usando API Keys.
"""
import hashlib
import secrets
from base64 import urlsafe_b64decode
from datetime import datetime, timedelta

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import jwt

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import GlobalApiKey

router = APIRouter(tags=["OAuth"])

# Almacenamiento en memoria para authorization codes (TTL 10 min)
# En producción se debería usar Redis u otro store distribuido
_auth_codes: dict[str, dict] = {}


def _cleanup_expired_codes() -> None:
    now = datetime.utcnow()
    expired = [code for code, data in _auth_codes.items() if data["expires_at"] < now]
    for code in expired:
        _auth_codes.pop(code, None)


def _validate_api_key_in_db(api_key: str) -> int:
    """Valida el API key contra la DB y retorna el ID del registro."""
    hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
    db = SessionLocal()
    try:
        key_record = db.query(GlobalApiKey).filter(
            GlobalApiKey.hashed_key == hashed_key,
            GlobalApiKey.is_active == True,
        ).first()
        if not key_record:
            return 0
        return key_record.id
    finally:
        db.close()


def _issue_jwt(key_id: int) -> dict:
    """Genera un JWT Bearer token para el API key dado."""
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(key_id),
        "exp": expire,
        "iat": datetime.utcnow(),
        "iss": settings.OAUTH_ISSUER,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRE_MINUTES * 60,
    }


# ---------------------------------------------------------------------------
# OAuth Discovery
# ---------------------------------------------------------------------------

@router.get("/.well-known/oauth-authorization-server", include_in_schema=False)
def oauth_metadata() -> JSONResponse:
    """RFC 8414 — OAuth 2.0 Authorization Server Metadata."""
    settings = get_settings()
    base = settings.OAUTH_ISSUER
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": ["mcp"],
    })


# ---------------------------------------------------------------------------
# Dynamic Client Registration (RFC 7591) — sin persistencia
# ---------------------------------------------------------------------------

@router.post("/oauth/register", include_in_schema=False)
def oauth_register(body: dict) -> JSONResponse:
    """Acepta cualquier cliente sin persistir — el client_id enviado es retornado tal cual."""
    client_id = body.get("client_id") or secrets.token_urlsafe(16)
    return JSONResponse({
        "client_id": client_id,
        "client_secret_expires_at": 0,
        "grant_types": body.get("grant_types", ["authorization_code"]),
        "redirect_uris": body.get("redirect_uris", []),
        "token_endpoint_auth_method": "none",
    }, status_code=201)


# ---------------------------------------------------------------------------
# Authorization Endpoint
# ---------------------------------------------------------------------------

_AUTHORIZE_FORM = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AuditorIA — Autorizar acceso MCP</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 420px; margin: 60px auto; padding: 0 1rem; }}
    h2 {{ margin-bottom: 0.25rem; }}
    p {{ color: #555; font-size: 0.9rem; margin-top: 0; }}
    label {{ display: block; margin-top: 1rem; font-weight: 600; }}
    input[type=password] {{ width: 100%; padding: 0.5rem; margin-top: 0.25rem; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
    button {{ margin-top: 1.25rem; width: 100%; padding: 0.6rem; background: #0066cc; color: #fff; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #0052a3; }}
    .error {{ color: #c00; margin-top: 0.75rem; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h2>AuditorIA</h2>
  <p>Una aplicación solicita acceso MCP a tu cuenta. Ingresá tu API Key para continuar.</p>
  <form method="POST" action="/oauth/authorize">
    <input type="hidden" name="client_id" value="{client_id}">
    <input type="hidden" name="redirect_uri" value="{redirect_uri}">
    <input type="hidden" name="state" value="{state}">
    <input type="hidden" name="code_challenge" value="{code_challenge}">
    <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
    <label for="api_key">API Key</label>
    <input type="password" id="api_key" name="api_key" placeholder="sk-..." required autofocus>
    {error_html}
    <button type="submit">Autorizar</button>
  </form>
</body>
</html>"""


@router.get("/oauth/authorize", include_in_schema=False)
def authorize_get(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
) -> HTMLResponse:
    if response_type != "code":
        raise HTTPException(status_code=400, detail="unsupported_response_type")
    html = _AUTHORIZE_FORM.format(
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        error_html="",
    )
    return HTMLResponse(content=html)


@router.post("/oauth/authorize", include_in_schema=False)
def authorize_post(
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(default=""),
    code_challenge: str = Form(default=""),
    code_challenge_method: str = Form(default=""),
    api_key: str = Form(...),
) -> RedirectResponse:
    _cleanup_expired_codes()

    key_id = _validate_api_key_in_db(api_key)
    if not key_id:
        # Mostrar formulario nuevamente con error
        html = _AUTHORIZE_FORM.format(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            error_html='<p class="error">API Key inválida. Intentá nuevamente.</p>',
        )
        return HTMLResponse(content=html, status_code=401)

    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "key_id": key_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "expires_at": datetime.utcnow() + timedelta(minutes=10),
    }

    redirect_url = f"{redirect_uri}?code={code}"
    if state:
        redirect_url += f"&state={state}"
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# Token Endpoint
# ---------------------------------------------------------------------------

@router.post("/oauth/token", include_in_schema=False)
def oauth_token(
    grant_type: str = Form(...),
    # authorization_code params
    code: str = Form(default=""),
    redirect_uri: str = Form(default=""),
    code_verifier: str = Form(default=""),
    # client_credentials params
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
) -> JSONResponse:
    _cleanup_expired_codes()

    if grant_type == "authorization_code":
        code_data = _auth_codes.pop(code, None)
        if not code_data:
            raise HTTPException(status_code=400, detail="invalid_grant")
        if datetime.utcnow() > code_data["expires_at"]:
            raise HTTPException(status_code=400, detail="invalid_grant")

        # Validar PKCE si se usó
        challenge = code_data.get("code_challenge", "")
        method = code_data.get("code_challenge_method", "")
        if challenge and code_verifier:
            if method == "S256":
                import hashlib as _hl
                from base64 import urlsafe_b64encode
                digest = _hl.sha256(code_verifier.encode()).digest()
                computed = urlsafe_b64encode(digest).rstrip(b"=").decode()
                if computed != challenge:
                    raise HTTPException(status_code=400, detail="invalid_grant")
            elif method == "plain":
                if code_verifier != challenge:
                    raise HTTPException(status_code=400, detail="invalid_grant")

        key_id = code_data["key_id"]

    elif grant_type == "client_credentials":
        if not client_secret:
            raise HTTPException(status_code=400, detail="invalid_client")
        key_id = _validate_api_key_in_db(client_secret)
        if not key_id:
            raise HTTPException(status_code=401, detail="invalid_client")

    else:
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    return JSONResponse(_issue_jwt(key_id))
