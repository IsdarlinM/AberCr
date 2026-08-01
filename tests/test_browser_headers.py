from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from base_client import AbercrombieClient, Config, HttpResponseError


def make_response(
    status: int,
    body: str,
    *,
    content_type: str,
    url: str,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body.encode("utf-8")
    response.headers["Content-Type"] = content_type
    response.url = url
    response.encoding = "utf-8"
    return response


class BrowserHeaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.session = Mock(spec=requests.Session)
        self.session.headers = {}
        self.session.cookies = requests.cookies.RequestsCookieJar()
        self.session.mount = Mock()
        self.session.close = Mock()
        self.config = Config(
            diagnostics_dir=Path(self.temp_dir.name),
            bootstrap_retries=0,
            verbose=False,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_navigation_headers_match_document_navigation(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        headers = client.build_navigation_headers()
        self.assertEqual(headers["Sec-Fetch-Site"], "none")
        self.assertEqual(headers["Sec-Fetch-Mode"], "navigate")
        self.assertEqual(headers["Sec-Fetch-Dest"], "document")
        self.assertEqual(headers["Sec-Fetch-User"], "?1")

    def test_graphql_headers_match_same_origin_fetch(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        headers = client.build_graphql_headers()
        self.assertEqual(headers["Origin"], self.config.base_url)
        self.assertEqual(headers["Referer"], self.config.store_url)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Sec-Fetch-Site"], "same-origin")
        self.assertEqual(headers["Sec-Fetch-Mode"], "cors")
        self.assertEqual(headers["Sec-Fetch-Dest"], "empty")

    def test_captured_headers_are_merged_safely(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        result = client.set_browser_headers(
            {
                "Sec-CH-UA": '"Chromium";v="138"',
                "Sec-CH-UA-Mobile": "?0",
                "DNT": "1",
                "Cookie": "secret=value",
                "Host": "invalid.example",
                "Content-Length": "999",
                "User-Agent": "captured browser",
                "X-Bug-Bounty": "other",
            }
        )
        headers = client.build_graphql_headers()
        self.assertEqual(headers["Sec-CH-UA"], '"Chromium";v="138"')
        self.assertEqual(headers["DNT"], "1")
        self.assertNotIn("Cookie", headers)
        self.assertNotIn("Host", headers)
        self.assertEqual(headers["User-Agent"], self.config.user_agent)
        self.assertEqual(headers["X-Bug-Bounty"], "HackerOne")
        self.assertIn("Cookie", result["ignored"])

    def test_browser_header_file_supports_har_list(self) -> None:
        path = Path(self.temp_dir.name) / "headers.json"
        path.write_text(
            json.dumps(
                {
                    "request": {
                        "headers": [
                            {"name": "Sec-CH-UA-Platform", "value": '"Android"'},
                            {"name": "DNT", "value": "1"},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        client = AbercrombieClient(self.config, self.session)
        client.load_browser_headers(path)
        self.assertEqual(
            client.build_graphql_headers()["Sec-CH-UA-Platform"],
            '"Android"',
        )

    def test_browser_header_file_supports_raw_lines(self) -> None:
        parsed = AbercrombieClient.parse_browser_headers(
            "Sec-CH-UA-Mobile: ?1\nSec-GPC: 1\n"
        )
        self.assertEqual(parsed["Sec-CH-UA-Mobile"], "?1")
        self.assertEqual(parsed["Sec-GPC"], "1")

    def test_header_report_does_not_send_network_request(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        report = client.header_report()
        self.assertIn("navigation", report)
        self.assertIn("graphql", report)
        self.session.get.assert_not_called()
        self.session.post.assert_not_called()

    def test_fastly_challenge_is_detected_during_bootstrap(self) -> None:
        bootstrap = make_response(
            200,
            '<a href="/anf/auth">Fastly Challenge</a>',
            content_type="text/html",
            url=self.config.store_url,
        )
        self.session.get.return_value = bootstrap
        client = AbercrombieClient(self.config, self.session)
        result = client.probe()
        self.assertTrue(result["client_challenge_detected"])

    def test_graphql_403_mentions_fastly_when_detected(self) -> None:
        bootstrap = make_response(
            200,
            '<a href="/anf/auth">Fastly Challenge</a>',
            content_type="text/html",
            url=self.config.store_url,
        )
        graphql = make_response(
            403,
            "<p>Reference ID: edge999</p>",
            content_type="text/html",
            url=self.config.api_url,
        )
        self.session.get.return_value = bootstrap
        self.session.post.return_value = graphql
        client = AbercrombieClient(self.config, self.session)

        with self.assertRaises(HttpResponseError) as context:
            client.sign_in("user@example.com", "secret")

        self.assertIn("Fastly Client Challenge", str(context.exception))


if __name__ == "__main__":
    unittest.main()
