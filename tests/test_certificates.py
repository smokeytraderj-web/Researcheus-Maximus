import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from security.certificates import certificate_bundle_path, configure_certificate_trust


class CertificateTrustTests(unittest.TestCase):
    def test_non_windows_uses_certifi_bundle(self):
        import certifi

        with patch("security.certificates.sys.platform", "linux"):
            self.assertEqual(certificate_bundle_path(), Path(certifi.where()))

    def test_windows_certificates_are_appended_to_verified_bundle(self):
        import certifi

        sample = "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----"
        with tempfile.TemporaryDirectory() as directory, patch(
            "security.certificates._windows_certificates", return_value=(sample,)
        ):
            bundle = certificate_bundle_path(Path(directory))
            contents = bundle.read_text(encoding="ascii")
            self.assertTrue(contents.startswith(Path(certifi.where()).read_text(encoding="ascii").splitlines()[0]))
            self.assertIn(sample, contents)

    def test_environment_never_disables_verification(self):
        with patch("security.certificates._windows_certificates", return_value=()):
            bundle = configure_certificate_trust()
        self.assertNotEqual(os.environ.get("CURL_CA_BUNDLE"), "")
        self.assertNotEqual(os.environ.get("CURL_CA_BUNDLE"), "false")
        self.assertTrue(bundle.exists())


if __name__ == "__main__":
    unittest.main()
