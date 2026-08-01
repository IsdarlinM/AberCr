from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config
from .errors import GraphQLError, HttpResponseError
from .queries import CREATE_USER_QUERY, LOGIN_QUERY
from .validation import (
    validate_birth_date,
    validate_email,
    validate_name,
    validate_password,
)


class AbercrombieClient:
    def __init__(
        self,
        config: Config | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.config = config or Config()
        self.session = session or requests.Session()
        self.session.headers.update(self.config.common_headers)
        self.referer_url = self.config.store_url
        self.initialized = False
        self.last_response: requests.Response | None = None
        self._configure_bootstrap_retries()

    def _configure_bootstrap_retries(self) -> None:
        if not hasattr(self.session, "mount"):
            return
        retries = Retry(
            total=self.config.bootstrap_retries,
            connect=self.config.bootstrap_retries,
            read=self.config.bootstrap_retries,
            status=self.config.bootstrap_retries,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            backoff_factor=0.4,
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def initialize_session(self) -> requests.Response:
        response = self.session.get(
            self.config.store_url,
            headers=self.config.navigation_headers,
            timeout=self.config.timeout,
            verify=self.config.verify_tls,
            allow_redirects=True,
        )
        self.last_response = response
        self._print_response_summary("Bootstrap", response)
        if not response.ok:
            self._raise_http_error("El bootstrap fue rechazado.", response)
        self.referer_url = response.url or self.config.store_url
        self.initialized = True
        return response

    def probe(self) -> dict[str, Any]:
        response = self.initialize_session()
        return {
            "status_code": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("Content-Type"),
            "cookies": len(self.session.cookies),
        }

    def _graphql_request(
        self,
        operation_name: str,
        variables: Mapping[str, Any],
        query: str,
    ) -> dict[str, Any]:
        if self.config.bootstrap_enabled and not self.initialized:
            self.initialize_session()
        payload = [{
            "operationName": operation_name,
            "variables": dict(variables),
            "query": query,
        }]
        encoded_body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.session.post(
            self.config.api_url,
            data=encoded_body,
            headers=self.config.graphql_headers(self.referer_url),
            timeout=self.config.timeout,
            verify=self.config.verify_tls,
            allow_redirects=False,
        )
        self.last_response = response
        self._print_response_summary("GraphQL", response)
        content_type = response.headers.get("Content-Type", "").lower()
        if not response.ok:
            self._raise_http_error(
                "La solicitud fue rechazada antes de completar GraphQL.",
                response,
            )
        if "json" not in content_type:
            path = self._save_response_body(response, "graphql_non_json")
            raise HttpResponseError(
                "El servidor respondió HTTP correctamente, pero no devolvió JSON.\n"
                f"Content-Type: {content_type or 'desconocido'}\n"
                f"Respuesta guardada en: {path}",
                status_code=response.status_code,
                diagnostic_path=path,
            )
        try:
            body = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            path = self._save_response_body(response, "graphql_invalid_json")
            raise HttpResponseError(
                "El servidor indicó JSON, pero el cuerpo no es JSON válido.\n"
                f"Respuesta guardada en: {path}",
                status_code=response.status_code,
                diagnostic_path=path,
            ) from exc
        if not isinstance(body, list) or not body or not isinstance(body[0], dict):
            raise GraphQLError(
                "Formato GraphQL inesperado:\n"
                + json.dumps(body, indent=2, ensure_ascii=False)
            )
        operation = body[0]
        if operation.get("errors"):
            raise GraphQLError(
                "Errores GraphQL generales:\n"
                + json.dumps(operation["errors"], indent=2, ensure_ascii=False)
            )
        return operation

    def sign_in(
        self,
        email: str,
        password: str,
        *,
        keep_me_signed_in: bool = False,
        merge_bag: bool = True,
        accept_loyalty_terms: bool | None = None,
        fast_enroll_campaign_id: str | None = None,
    ) -> dict[str, Any]:
        email = validate_email(email)
        validate_password(password)
        variables = {
            "email": email,
            "password": password,
            "keepMeSignedIn": keep_me_signed_in,
            "isLoyaltyConversionTermsAccepted": accept_loyalty_terms,
            "doMergeBag": merge_bag,
            "fastEnrollCampaignId": fast_enroll_campaign_id,
        }
        operation = self._graphql_request(
            "LOGIN_MUTATION", variables, LOGIN_QUERY
        )
        result = operation.get("data", {}).get("login")
        if not isinstance(result, dict):
            raise GraphQLError(
                "La respuesta no contiene data.login:\n"
                + json.dumps(operation, indent=2, ensure_ascii=False)
            )
        return result

    def create_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        *,
        primary_phone: str | None = None,
        keep_me_signed_in: bool = False,
        marketing_opt_in: bool = False,
        legal_accept: bool = False,
        age_above_or_below: bool | None = None,
        referral_code: str | None = None,
        fast_enroll_campaign_id: str | None = None,
        gender: str | None = None,
        birth_month: int | None = None,
        birth_day: int | None = None,
        birth_year: int | None = None,
    ) -> dict[str, Any]:
        email = validate_email(email)
        validate_password(password)
        first_name = validate_name("first_name", first_name)
        last_name = validate_name("last_name", last_name)
        validate_birth_date(birth_year, birth_month, birth_day)
        variables = {
            "email": email,
            "password": password,
            "keepMeSignedIn": keep_me_signed_in,
            "firstName": first_name,
            "lastName": last_name,
            "primaryPhone": primary_phone,
            "emailOptions": [{"key": "anf", "value": marketing_opt_in}],
            "ageAboveOrBelow": age_above_or_below,
            "referralCode": referral_code,
            "fastEnrollCampaignId": fast_enroll_campaign_id,
            "legalAccept": legal_accept,
            "preference": {
                "gender": gender,
                "birthMonth": birth_month,
                "birthDay": birth_day,
                "birthYear": birth_year,
            },
        }
        operation = self._graphql_request(
            "CREATE_USER_MUTATION", variables, CREATE_USER_QUERY
        )
        result = operation.get("data", {}).get("createUser")
        if not isinstance(result, dict):
            raise GraphQLError(
                "La respuesta no contiene data.createUser:\n"
                + json.dumps(operation, indent=2, ensure_ascii=False)
            )
        return result

    def _raise_http_error(
        self,
        title: str,
        response: requests.Response,
    ) -> None:
        path = self._save_response_body(response, "http_error")
        reference_id = self._extract_reference_id(response.text)
        parts = [
            f"{title} HTTP {response.status_code}.",
            f"URL: {response.url}",
        ]
        if reference_id:
            parts.append(f"Reference ID: {reference_id}")
        parts.append(f"Respuesta guardada en: {path}")
        raise HttpResponseError(
            "\n".join(parts),
            status_code=response.status_code,
            reference_id=reference_id,
            diagnostic_path=path,
        )

    @staticmethod
    def _extract_reference_id(body: str) -> str | None:
        match = re.search(
            r"Reference\s+ID:\s*([a-zA-Z0-9_-]+)",
            body,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def _save_response_body(
        self,
        response: requests.Response,
        prefix: str,
    ) -> Path:
        directory = self.config.diagnostics_dir.resolve()
        directory.mkdir(parents=True, exist_ok=True)
        content_type = response.headers.get("Content-Type", "").lower()
        if "json" in content_type:
            suffix = ".json"
        elif "html" in content_type:
            suffix = ".html"
        else:
            suffix = ".txt"
        path = directory / f"{prefix}_{response.status_code}{suffix}"
        path.write_bytes(response.content)
        return path

    def _print_response_summary(
        self,
        phase: str,
        response: requests.Response,
    ) -> None:
        if not self.config.verbose:
            return
        content_type = response.headers.get("Content-Type", "desconocido")
        print(f"[*] {phase} HTTP: {response.status_code}")
        print(f"[*] URL: {response.url}")
        print(f"[*] Content-Type: {content_type}")
        print(f"[*] Cookies: {len(self.session.cookies)}")

    def get_cookies(self) -> dict[str, str]:
        return self.session.cookies.get_dict()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "AbercrombieClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
