"""Where the web backend finds its API keys.

The desktop app remembers keys in the OS keychain (`security.secret_store`).
A web server run on that same machine is the same user and the same trust
boundary, so it reads the same keychain -- otherwise the app would silently
fall back to demo output even though the user had configured live research.

An environment variable always wins over the keychain, so a real deployment
(where there is no user keychain, and should not be one) is configured purely
through the environment.

Values are returned to the caller and never logged, echoed to the client, or
written to disk. Only *whether* a key was found is ever reported outward.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from security import secret_store

# Environment variable -> keychain entry it falls back to. A key with no
# keychain equivalent simply has None.
SYNTHESIS_ENV = "RESEARCHEUS_API_KEY"
TVREMIX_ENV = "RESEARCHEUS_TVREMIX_KEY"


def _resolve(env_name: str, keychain_name: str | None) -> tuple[str, str]:
    """Return (value, source). Source is 'environment', 'keychain', or 'none'."""
    value = os.environ.get(env_name, "").strip()
    if value:
        return value, "environment"
    if keychain_name:
        stored = secret_store.load_secret(keychain_name)
        if stored:
            return stored, "keychain"
    return "", "none"


@dataclass(frozen=True, slots=True)
class Credentials:
    synthesis_key: str
    synthesis_source: str
    tvremix_key: str
    tvremix_source: str
    provider: str
    model: str

    @property
    def live_research(self) -> bool:
        return bool(self.synthesis_key)

    @property
    def technical_research(self) -> bool:
        return bool(self.tvremix_key)

    def status(self) -> dict:
        """A key-free summary for the client, so the UI can explain itself.

        Reports only which credentials were found and where from -- never a
        key, a prefix, or a length.
        """
        return {
            "live_research": self.live_research,
            "technical_research": self.technical_research,
            "synthesis_key_source": self.synthesis_source,
            "tvremix_key_source": self.tvremix_source,
        }


def load() -> Credentials:
    """Resolve credentials fresh, so a key added later is picked up on reload."""
    synthesis_key, synthesis_source = _resolve(SYNTHESIS_ENV, secret_store.OPENAI_KEY)
    tvremix_key, tvremix_source = _resolve(TVREMIX_ENV, secret_store.TVREMIX_KEY)
    return Credentials(
        synthesis_key=synthesis_key,
        synthesis_source=synthesis_source,
        tvremix_key=tvremix_key,
        tvremix_source=tvremix_source,
        provider=os.environ.get("RESEARCHEUS_SYNTHESIS_PROVIDER", "Automatic"),
        model=os.environ.get("RESEARCHEUS_MODEL", "").strip(),
    )
