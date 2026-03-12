"""Tests for NVD (National Vulnerability Database) connector."""
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.ingestion.nvd import NVDConnector
from app.models import SourceKind


# Sample NVD API response
SAMPLE_NVD_RESPONSE = {
    "resultsPerPage": 2,
    "startIndex": 0,
    "totalResults": 2,
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2026-12345",
                "published": "2026-03-11T14:00:00.000",
                "lastModified": "2026-03-11T16:00:00.000",
                "descriptions": [
                    {"lang": "en", "value": "A critical vulnerability in PyTorch allows remote code execution via crafted tensor input."},
                    {"lang": "es", "value": "Una vulnerabilidad critica..."},
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"},
                        }
                    ]
                },
            }
        },
        {
            "cve": {
                "id": "CVE-2026-12346",
                "published": "2026-03-10T10:00:00.000",
                "lastModified": "2026-03-10T12:00:00.000",
                "descriptions": [
                    {"lang": "en", "value": "Buffer overflow in TensorFlow serving module."},
                ],
                "metrics": {},
            }
        },
    ],
}

EMPTY_NVD_RESPONSE = {
    "resultsPerPage": 0,
    "startIndex": 0,
    "totalResults": 0,
    "vulnerabilities": [],
}

OLD_CVE_RESPONSE = {
    "resultsPerPage": 1,
    "startIndex": 0,
    "totalResults": 1,
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2020-00001",
                "published": "2020-01-01T00:00:00.000",
                "lastModified": "2020-01-02T00:00:00.000",
                "descriptions": [
                    {"lang": "en", "value": "Old vulnerability."},
                ],
                "metrics": {},
            }
        },
    ],
}


class TestNVDConnector(unittest.TestCase):
    """Tests for the NVD connector with mocked HTTP."""

    def setUp(self):
        self.connector = NVDConnector(source_id="test-nvd-source-id")
        self.now = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_returns_candidate_items(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        self.assertGreater(len(items), 0)
        # Should have items from sample response
        cve_ids = [item.external_id for item in items]
        self.assertIn("CVE-2026-12345", cve_ids)
        self.assertIn("CVE-2026-12346", cve_ids)

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_cve_id_as_external_id(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        for item in items:
            self.assertTrue(item.external_id.startswith("CVE-"))

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_url_points_to_nvd_detail(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        for item in items:
            self.assertTrue(
                item.url.startswith("https://nvd.nist.gov/vuln/detail/CVE-"),
                f"URL should point to NVD detail page, got: {item.url}",
            )

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_title_contains_cve_id(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        for item in items:
            self.assertIn(item.external_id, item.title)

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_published_at_parsed(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        for item in items:
            self.assertIsNotNone(item.published_at)
            self.assertIsInstance(item.published_at, datetime)

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_old_cves_skipped(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = OLD_CVE_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        # Old CVEs (published in 2020) should be skipped with default lookback
        old_ids = [item.external_id for item in items if item.external_id == "CVE-2020-00001"]
        self.assertEqual(len(old_ids), 0, "Old CVEs should be skipped")

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_empty_response_returns_empty_list(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = EMPTY_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        self.assertEqual(items, [])

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_api_error_returns_empty_list(self, mock_sleep, mock_client_cls):
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        items = self.connector.fetch_candidates(now=self.now)

        self.assertEqual(items, [])

    @patch("app.ingestion.nvd.httpx.Client")
    @patch("app.ingestion.nvd.time.sleep")
    def test_rate_limit_delay_between_requests(self, mock_sleep, mock_client_cls):
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_NVD_RESPONSE
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        self.connector.fetch_candidates(now=self.now)

        # There should be sleep calls between keyword batches
        if mock_client.get.call_count > 1:
            self.assertTrue(mock_sleep.called, "Should sleep between API requests for rate limiting")


class TestSourceKindNVD(unittest.TestCase):
    """Tests that SourceKind enum includes nvd."""

    def test_nvd_exists(self):
        self.assertEqual(SourceKind.nvd.value, "nvd")

    def test_nvd_is_string_enum(self):
        self.assertIsInstance(SourceKind.nvd, str)


class TestPipelineNVDDispatch(unittest.TestCase):
    """Test that pipeline dispatches NVD kind correctly."""

    def test_connector_for_nvd_source(self):
        from app.tasks.pipeline import _connector_for_source

        mock_source = MagicMock()
        mock_source.kind = "nvd"
        mock_source.id = "test-id"

        connector = _connector_for_source(mock_source)

        self.assertIsNotNone(connector)
        self.assertIsInstance(connector, NVDConnector)


if __name__ == "__main__":
    unittest.main()
