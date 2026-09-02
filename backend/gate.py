"""A soft access gate for the hosted app.

One shared code unlocks the interface. This is a curtain, not a lock: it keeps
the app from being usable by anyone who happens on the URL, and that is all it
is meant to be. A four-digit code has ten thousand values, so the only thing
standing between it and a script is the attempt limit below -- which is why the
limit exists rather than being left as an exercise.

The code is checked server-side and never reaches the page, so it cannot be
read out of the markup the way a client-side prompt can. What the browser keeps
is a signed, expiring token that says the code was entered correctly, not the
code itself.

Report links (/r/{id}) are deliberately left outside the gate: they are the
client-facing deliverable and the people opening them do not have the code.
They remain unguessable-but-unauthenticated, as documented in backend/README.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

COOKIE_NAME = "tag_access"

# Configurable so the deployment can change the code without a redeploy of the
# image; the default keeps a fresh checkout working out of the box.
ACCESS_CODE = os.environ.get("RESEARCHEUS_ACCESS_CODE", "2003").strip()

# A per-process secret unless one is supplied. Unset means every restart
# invalidates outstanding tokens, which is an acceptable trade for not shipping
# a hardcoded signing key in a public repository.
_SECRET = (os.environ.get("RESEARCHEUS_SESSION_SECRET") or secrets.token_urlsafe(32)).encode()

TOKEN_TTL = 30 * 24 * 3600  # 30 days: long enough not to nag, short enough to expire.

# Attempt limiting. Ten thousand possible codes falls in minutes to an
# unthrottled script, so failures are counted per client address and the gate
# closes for a while once there have been too many.
MAX_ATTEMPTS = 8
LOCKOUT_SECONDS = 900
_failures: dict[str, tuple[int, float]] = {}


def code_matches(candidate: str) -> bool:
    """Compare in constant time, so the check cannot be timed character by character."""
    return hmac.compare_digest(candidate.strip(), ACCESS_CODE)


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()


def issue_token() -> str:
    """A token carrying its own expiry, signed so it cannot be edited."""
    expires = str(int(time.time()) + TOKEN_TTL)
    return f"{expires}.{_sign(expires)}"


def token_valid(token: str) -> bool:
    if not token or "." not in token:
        return False
    expires, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(expires)):
        return False
    try:
        return int(expires) > time.time()
    except ValueError:
        return False


def locked_out(client: str) -> bool:
    count, until = _failures.get(client, (0, 0.0))
    if until and time.time() > until:
        _failures.pop(client, None)
        return False
    return count >= MAX_ATTEMPTS


def record_failure(client: str) -> None:
    count, _ = _failures.get(client, (0, 0.0))
    _failures[client] = (count + 1, time.time() + LOCKOUT_SECONDS)


def clear_failures(client: str) -> None:
    _failures.pop(client, None)
