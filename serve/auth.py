"""
API-key authentication for the public endpoints (plan sections 11a and 19b).

Clients send `Authorization: Bearer <key>`. Keys come from the environment:

    API_KEY_PROD   required
    API_KEY_NEW    optional: accept both keys while rotating (plan 19b, step 3)

`/health`, `/ready` and `/metrics` stay open for Kubernetes probes and Prometheus.

`require_api_key` returns an opaque owner id (a hash of the key). The chat route uses it to
keep each key's conversation history and rate-limit state separate from every other key's, so
one client cannot read another's history by guessing a session id.
"""

import hashlib
import hmac
import os

from fastapi import Header, HTTPException

MIN_PRODUCTION_KEY_LENGTH = 24

_owners: dict[str, str] = {}      # accepted key -> owner id


def owner_id(key: str) -> str:
    """Stable, non-reversible identifier for an API key."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def load_api_keys() -> int:
    """Read the accepted keys from the environment. Raises if none is configured."""
    primary = os.environ.get('API_KEY_PROD', '').strip()
    if not primary:
        raise RuntimeError("API_KEY_PROD is not set: check the K8s secret or your .env")
    keys = [primary]
    rotating = os.environ.get('API_KEY_NEW', '').strip()
    if rotating and rotating != primary:
        keys.append(rotating)

    if os.getenv('ENV') == 'production':
        weak = [k for k in keys if len(k) < MIN_PRODUCTION_KEY_LENGTH]
        if weak:
            raise RuntimeError(
                f"API keys must be at least {MIN_PRODUCTION_KEY_LENGTH} characters in production "
                f"(generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
            )

    _owners.clear()
    _owners.update({key: owner_id(key) for key in keys})
    return len(keys)


async def require_api_key(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: returns the caller's owner id or raises 401."""
    if not _owners:
        raise HTTPException(status_code=503, detail="authentication is not configured")
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header",
                            headers={'WWW-Authenticate': 'Bearer'})
    token = authorization[len('Bearer '):].strip().encode()

    matched = None
    for key, owner in _owners.items():      # compare against every key: no early exit
        if hmac.compare_digest(token, key.encode()):
            matched = owner
    if matched is None:
        raise HTTPException(status_code=401, detail="Invalid API key",
                            headers={'WWW-Authenticate': 'Bearer'})
    return matched
