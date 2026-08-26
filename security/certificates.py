"""Build a verified CA bundle that also honors the Windows trust store."""

from __future__ import annotations

import os
import ssl
import sys
import tempfile
from pathlib import Path


_BUNDLE_NAME = "researcheus-ca-bundle.pem"


def _windows_certificates() -> tuple[str, ...]:
    """Return PEM certificates trusted by Windows, without private keys."""
    if sys.platform != "win32" or not hasattr(ssl, "enum_certificates"):
        return ()

    certificates: list[str] = []
    seen: set[bytes] = set()
    for store in ("ROOT", "CA"):
        try:
            records = ssl.enum_certificates(store)
        except OSError:
            continue
        for certificate, encoding, _trust in records:
            if encoding != "x509_asn" or certificate in seen:
                continue
            seen.add(certificate)
            certificates.append(ssl.DER_cert_to_PEM_cert(certificate))
    return tuple(certificates)


def certificate_bundle_path(cache_dir: Path | None = None) -> Path:
    """Create the CA bundle used by libcurl while keeping verification on."""
    try:
        import certifi
    except ImportError as exc:
        raise RuntimeError("Certificate support is missing. Re-run pip install -r requirements.txt.") from exc

    certifi_path = Path(certifi.where())
    windows_certificates = _windows_certificates()
    if not windows_certificates:
        return certifi_path

    destination_dir = cache_dir or Path(tempfile.gettempdir()) / "ResearcheusMaximus"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / _BUNDLE_NAME
    base_bundle = certifi_path.read_text(encoding="ascii")
    payload = base_bundle.rstrip() + "\n" + "\n".join(windows_certificates) + "\n"
    if not destination.exists() or destination.read_text(encoding="ascii") != payload:
        destination.write_text(payload, encoding="ascii")
    return destination


def configure_certificate_trust(cache_dir: Path | None = None) -> Path:
    """Configure standard Python TLS and return the libcurl CA bundle path."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except (ImportError, RuntimeError):
        # The explicit CA bundle below still covers curl_cffi/yfinance.
        pass

    bundle = certificate_bundle_path(cache_dir)
    for variable in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ.setdefault(variable, str(bundle))
    return bundle


def verified_market_session(cache_dir: Path | None = None):
    """Return a curl_cffi session verified against public and Windows CAs."""
    try:
        from curl_cffi import requests
    except ImportError as exc:
        raise RuntimeError("Live market support is missing. Re-run pip install -r requirements.txt.") from exc
    bundle = configure_certificate_trust(cache_dir)
    return requests.Session(impersonate="chrome", verify=str(bundle), trust_env=True)

