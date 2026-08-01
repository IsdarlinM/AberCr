from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from base_client import (
    AbercrombieClient,
    Config,
    HttpResponseError,
)


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


class ConfigTests(unittest.TestCase):
    def test_required_identification_headers_are_present(self) -> None:
        config = Config()
        self.assertEqual(config.common_headers["X-Bug-Bounty"], "HackerOne")
        self.assertEqual(
            config.common_headers["User-Agent"],
            "Browser/immroa/0.0.1 "
            "(HackerOne User, https://hackerone.com/immroa?type=user)",
        )

    def test_api_url_is_encoded(self) -> None:
        config = Config(country="EC", store="a-wd-es")
        self.assertIn("country=EC", config.api_url)
        self.assertIn("store=a-wd-es", config.api_url)

    def test_invalid_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "mayor que 0"):
            Config(timeout=0)


class ClientTests(unittest.TestCase):
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

    def test_bootstrap_403_saves_body_and_reference_id(self) -> None:
        response = make_response(
            403,
            "<p>Reference ID: abc123</p>",
            content_type="text/html",
            url=self.config.store_url,
        )
        self.session.get.return_value = response
        client = AbercrombieClient(self.config, self.session)

        with self.assertRaises(HttpResponseError) as context:
            client.initialize_session()

        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(context.exception.reference_id, "abc123")
        self.assertTrue(context.exception.diagnostic_path.exists())
        self.assertEqual(
            context.exception.diagnostic_path.read_text(encoding="utf-8"),
            "<p>Reference ID: abc123</p>",
        )

    def test_sign_in_sends_expected_graphql_payload(self) -> None:
        bootstrap = make_response(
            200,
            "ok",
            content_type="text/html",
            url="https://www.abercrombie.com/shop/wd-es",
        )
        graphql = make_response(
            200,
            json.dumps([{"data": {"login": {"success": True, "userId": "42"}}}]),
            content_type="application/json",
            url=self.config.api_url,
        )
        self.session.get.return_value = bootstrap
        self.session.post.return_value = graphql
        client = AbercrombieClient(self.config, self.session)

        result = client.sign_in("user@example.com", "secret")

        self.assertTrue(result["success"])
        call = self.session.post.call_args
        payload = json.loads(call.kwargs["data"].decode("utf-8"))
        self.assertEqual(payload[0]["operationName"], "LOGIN_MUTATION")
        self.assertEqual(payload[0]["variables"]["email"], "user@example.com")
        self.assertEqual(payload[0]["variables"]["password"], "secret")
        self.assertEqual(call.kwargs["headers"]["X-Bug-Bounty"], "HackerOne")

    def test_create_user_sends_expected_preferences(self) -> None:
        bootstrap = make_response(
            200,
            "ok",
            content_type="text/html",
            url=self.config.store_url,
        )
        graphql = make_response(
            200,
            json.dumps([{"data": {"createUser": {"success": True}}}]),
            content_type="application/json",
            url=self.config.api_url,
        )
        self.session.get.return_value = bootstrap
        self.session.post.return_value = graphql
        client = AbercrombieClient(self.config, self.session)

        result = client.create_user(
            "user@example.com",
            "secret",
            " IM ",
            " MR ",
            legal_accept=True,
            marketing_opt_in=False,
            birth_year=2000,
            birth_month=2,
            birth_day=29,
        )

        self.assertTrue(result["success"])
        payload = json.loads(
            self.session.post.call_args.kwargs["data"].decode("utf-8")
        )
        variables = payload[0]["variables"]
        self.assertEqual(variables["firstName"], "IM")
        self.assertEqual(variables["lastName"], "MR")
        self.assertTrue(variables["legalAccept"])
        self.assertFalse(variables["emailOptions"][0]["value"])
        self.assertEqual(variables["preference"]["birthDay"], 29)

    def test_create_user_validates_complete_birth_date(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        with self.assertRaisesRegex(ValueError, "deben enviarse juntos"):
            client.create_user(
                "user@example.com",
                "secret",
                "IM",
                "MR",
                birth_year=2000,
            )

    def test_invalid_calendar_date_is_rejected(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        with self.assertRaisesRegex(ValueError, "no es válida"):
            client.create_user(
                "user@example.com",
                "secret",
                "IM",
                "MR",
                birth_year=2001,
                birth_month=2,
                birth_day=29,
            )

    def test_invalid_email_is_rejected_before_network(self) -> None:
        client = AbercrombieClient(self.config, self.session)
        with self.assertRaisesRegex(ValueError, "formato válido"):
            client.sign_in("not-an-email", "secret")
        self.session.post.assert_not_called()

    def test_no_bootstrap_posts_directly(self) -> None:
        config = Config(
            diagnostics_dir=Path(self.temp_dir.name),
            bootstrap_enabled=False,
            bootstrap_retries=0,
            verbose=False,
        )
        graphql = make_response(
            200,
            json.dumps([{"data": {"login": {"success": False}}}]),
            content_type="application/json",
            url=config.api_url,
        )
        self.session.post.return_value = graphql
        client = AbercrombieClient(config, self.session)

        client.sign_in("user@example.com", "secret")

        self.session.get.assert_not_called()
        self.session.post.assert_called_once()

    def test_graphql_403_saves_diagnostic(self) -> None:
        bootstrap = make_response(
            200,
            "ok",
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

        self.assertEqual(context.exception.reference_id, "edge999")
        self.assertTrue(context.exception.diagnostic_path.exists())

    def test_context_manager_closes_session(self) -> None:
        with AbercrombieClient(self.config, self.session):
            pass
        self.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
