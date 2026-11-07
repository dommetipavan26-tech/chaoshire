"""Per-audit access tokens for published audit records.

A published upload used to be world-readable: anyone who learned or guessed
an ``AUD-…`` identifier could read the full aggregate record from
``GET /api/audits/{audit_id}``, and the shared history list exposed every
published audit to every visitor. Each published audit now receives a random
access token at creation time:

* the token is returned **once**, in the upload response that creates the
  audit (``audit_access_token``), and is never persisted or listed;
* only its SHA-256 digest is stored, in the ``access_token_hash`` column, so
  a database leak does not leak usable tokens and raw candidate rows remain
  unpersisted exactly as before;
* reading that audit requires the deployment operator key
  (``CHAOSHIRE_API_KEY``) *or* the audit's own token, presented as the
  ``X-Audit-Access-Token`` header or the ``access_token`` query parameter.

This is a per-record bearer capability, not a user account, tenant claim, or
ownership system: whoever holds the token can read that one aggregate audit.
Audits saved before this feature have no digest and are operator-only.
"""

from __future__ import annotations

import hashlib
from secrets import compare_digest, token_urlsafe

#: Header a client may use instead of the ``access_token`` query parameter.
AUDIT_ACCESS_HEADER = "X-Audit-Access-Token"


def new_audit_access_token() -> tuple[str, str]:
    """Return ``(token, digest)``; only the digest may be stored."""
    token = token_urlsafe(32)
    return token, hash_audit_access_token(token)


def hash_audit_access_token(token: str) -> str:
    """SHA-256 digest of a token, as stored in ``access_token_hash``."""
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def audit_access_token_matches(stored_digest: str | None, supplied: str | None) -> bool:
    """Constant-time check of a supplied token against a stored digest."""
    if not stored_digest or not supplied or not supplied.strip():
        return False
    return compare_digest(stored_digest, hash_audit_access_token(supplied))
