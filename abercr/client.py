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
    """Cliente HTTP para las operaciones públicas de cuenta del frontend."""

    _AUTO_MANAGED_HEADERS = frozenset(
        {
            "accept-encoding",
            "connection",
            "content-length",
            "cookie",
            "host",
            "proxy-authorization",
            "transfer-encoding",
        }
    )
    _PROTECTED_HEADERS = frozenset(
        {
            "authorization",
            "content-type",
            "origin",
            "referer",
            "user-agent",
            "x-bug-bounty",
        }
    )
    _FASTLY_CHALLENGE_MARKERS = (
        "fastly challenge",
        "/anf/auth",
        "_fs_ch_st_",
        "_fs_ch_cp_",
    )

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
        self.client_challenge_detected = False
        self._browser_header_overrides: dict[str, str] = {}
        self._ignored_browser_headers: dict[str, str] = {}
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

    def build_navigation_headers(
        self,
        overrides: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Genera headers coherentes con una navegación principal de navegador."""
        return self._merge_headers(
            self.config.navigation_headers,
            self._browser_header_overrides,
            overrides,
        )

    def build_graphql_headers(
        self,
        referer: str | None = None,
        overrides: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        """Genera headers de un fetch CORS same-origin para el POST GraphQL."""
        return self._merge_headers(
            self.config.graphql_headers(referer or self.referer_url),
            self._browser_header_overrides,
            overrides,
        )

    def set_browser_headers(
        self,
        headers: Mapping[str, Any],
        *,
        replace: bool = True,
    ) -> dict[str, dict[str, str]]:
        """
        Agrega headers capturados desde DevTools.

        Host, Cookie, Content-Length, Accept-Encoding y otros headers que debe
        administrar requests se ignoran. También se conservan el User-Agent y
        X-Bug-Bounty configurados por el investigador.
        """
        accepted, ignored = self._sanitize_browser_headers(headers)
        if replace:
            self._browser_header_overrides = accepted
            self._ignored_browser_headers = ignored
        else:
            self._browser_header_overrides = self._merge_headers(
                self._browser_header_overrides,
                accepted,
            )
            self._ignored_browser_headers.update(ignored)
        return {"applied": accepted.copy(), "ignored": ignored.copy()}

    def load_browser_headers(
        self,
        path: str | Path,
        *,
        replace: bool = True,
    ) -> dict[str, dict[str, str]]:
        """
        Carga headers desde JSON, una lista HAR o texto ``Nombre: valor``.

        El archivo debe proceder de una solicitud propia capturada en DevTools.
        No se importa el header Cookie; la sesión mantiene su propio cookie jar.
        """
        header_path = Path(path)
        raw = header_path.read_text(encoding="utf-8-sig")
        parsed = self.parse_browser_headers(raw)
        return self.set_browser_headers(parsed, replace=replace)

    @classmethod
    def parse_browser_headers(cls, raw: str) -> dict[str, str]:
        """Interpreta un objeto JSON, un arreglo HAR o líneas de headers."""
        text = raw.strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return cls._parse_header_lines(text)
        return cls._headers_from_json(payload)

    @classmethod
    def _headers_from_json(cls, payload: Any) -> dict[str, str]:
        if isinstance(payload, dict):
            if "request" in payload and isinstance(payload["request"], dict):
                return cls._headers_from_json(payload["request"])
            if "headers" in payload:
                return cls._headers_from_json(payload["headers"])
            return {
                str(name): str(value)
                for name, value in payload.items()
                if value is not None and not isinstance(value, (dict, list))
            }
        if isinstance(payload, list):
            headers: dict[str, str] = {}
            for item in payload:
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                value = item.get("value")
                if name is not None and value is not None:
                    headers[str(name)] = str(value)
            return headers
        raise ValueError("El archivo de headers no tiene un formato compatible.")

    @staticmethod
    def _parse_header_lines(text: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(":"):
                continue
            if ":" not in line:
                raise ValueError(
                    f"Header inválido en la línea {line_number}: {raw_line!r}"
                )
            name, value = line.split(":", 1)
            headers[name.strip()] = value.strip()
        return headers

    def header_report(self) -> dict[str, Any]:
        """Devuelve los headers efectivos sin realizar peticiones de red."""
        return {
            "navigation": self.build_navigation_headers(),
            "graphql": self.build_graphql_headers(),
            "captured_applied": self._browser_header_overrides.copy(),
            "captured_ignored": self._ignored_browser_headers.copy(),
            "note": (
                "Cookie, Host, Content-Length, Connection y Accept-Encoding "
                "son administrados por requests y no se importan."
            ),
        }

    def initialize_session(self) -> requests.Response:
        response = self.session.get(
            self.config.store_url,
            headers=self.build_navigation_headers(),
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
        self.client_challenge_detected = self._contains_fastly_challenge(
            response.text
        )
        if self.client_challenge_detected and self.config.verbose:
            print(
                "[!] Posible Fastly Client Challenge detectado en el HTML. "
                "requests no ejecuta el JavaScript que genera su token."
            )
        return response

    def probe(self) -> dict[str, Any]:
        response = self.initialize_session()
        return {
            "status_code": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("Content-Type"),
            "cookies": len(self.session.cookies),
            "client_challenge_detected": self.client_challenge_detected,
        }

    def _graphql_request(
        self,
        operation_name: str,
        variables: Mapping[str, Any],
        query: str,
    ) -> dict[str, Any]:
        if self.config.bootstrap_enabled and not self.initialized:
            self.initialize_session()
        payload = [
            {
                "operationName": operation_name,
                "variables": dict(variables),
                "query": query,
            }
        ]
        encoded_body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.session.post(
            self.config.api_url,
            data=encoded_body,
            headers=self.build_graphql_headers(),
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

    def _sanitize_browser_headers(
        self,
        headers: Mapping[str, Any],
    ) -> tuple[dict[str, str], dict[str, str]]:
        accepted: dict[str, str] = {}
        ignored: dict[str, str] = {}
        for raw_name, raw_value in headers.items():
            name = str(raw_name).strip()
            value = str(raw_value).strip()
            lowered = name.lower()
            if not name or not value:
                continue
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise ValueError(f"El header {name!r} contiene saltos de línea.")
            if name.startswith(":"):
                ignored[name] = value
                continue
            if lowered in self._AUTO_MANAGED_HEADERS or lowered in self._PROTECTED_HEADERS:
                ignored[name] = value
                continue
            accepted[name] = value
        return accepted, ignored

    @staticmethod
    def _merge_headers(
        *groups: Mapping[str, str] | None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        index: dict[str, str] = {}
        for group in groups:
            if not group:
                continue
            for name, value in group.items():
                lowered = name.lower()
                previous = index.get(lowered)
                if previous is not None and previous != name:
                    merged.pop(previous, None)
                merged[name] = value
                index[lowered] = name
        return merged

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
        if response.status_code == 403 and (
            self.client_challenge_detected
            or self._contains_fastly_challenge(response.text)
        ):
            parts.append(
                "Se detectaron indicios de Fastly Client Challenge. "
                "Los headers de navegador no sustituyen el token/cookie "
                "generado al ejecutar el desafío JavaScript en un navegador."
            )
        parts.append(f"Respuesta guardada en: {path}")
        raise HttpResponseError(
            "\n".join(parts),
            status_code=response.status_code,
            reference_id=reference_id,
            diagnostic_path=path,
        )

    @classmethod
    def _contains_fastly_challenge(cls, body: str) -> bool:
        lowered = body.lower()
        return any(marker in lowered for marker in cls._FASTLY_CHALLENGE_MARKERS)

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
