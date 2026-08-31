"""Opt-in storage for API keys in the operating system's own credential store.

The application still never writes a secret into its own settings, working files,
logs, reports, or session directories.  When the user asks for a key to be
remembered, it is handed to the OS keychain -- macOS Keychain, Windows Credential
Manager, or the Linux Secret Service -- which stores it encrypted under the user's
login and can be revoked there without this application's involvement.

Every call degrades quietly: if no backend is present, the key simply is not
remembered and the user re-enters it, which is the previous behaviour.
"""

from __future__ import annotations

SERVICE_NAME = "Researcheus Maximus"

TVREMIX_KEY = "tvremix_api_key"
OPENAI_KEY = "openai_api_key"


def _keyring():
    """The keyring module, or None when it is unavailable or has no real backend."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except Exception:  # noqa: BLE001 - optional dependency; absence is not an error
        return None
    try:
        if isinstance(keyring.get_keyring(), FailKeyring):
            return None
    except Exception:  # noqa: BLE001 - a broken backend is the same as no backend
        return None
    return keyring


def available() -> bool:
    """Whether this machine offers a credential store to remember keys in."""
    return _keyring() is not None


def load_secret(name: str) -> str:
    """The remembered value for ``name``, or an empty string."""
    keyring = _keyring()
    if keyring is None:
        return ""
    try:
        return (keyring.get_password(SERVICE_NAME, name) or "").strip()
    except Exception:  # noqa: BLE001 - never let a locked keychain break startup
        return ""


def save_secret(name: str, value: str) -> bool:
    """Remember ``value``; an empty value forgets it instead. True when applied."""
    keyring = _keyring()
    if keyring is None:
        return False
    try:
        if value.strip():
            keyring.set_password(SERVICE_NAME, name, value.strip())
        else:
            forget_secret(name)
        return True
    except Exception:  # noqa: BLE001 - remembering is a convenience, never a hard failure
        return False


def forget_secret(name: str) -> bool:
    """Remove a remembered value. True when it is gone afterwards."""
    keyring = _keyring()
    if keyring is None:
        return False
    try:
        keyring.delete_password(SERVICE_NAME, name)
    except Exception:  # noqa: BLE001 - already absent is success
        return True
    return True
