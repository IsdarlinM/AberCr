from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode


@dataclass(slots=True)
class Config:
    brand: str = "anf"
    catalog_id: str = "10901"
    country: str = "EC"
    lang_id: str = "-1002"
    store: str = "a-wd-es"
    store_id: str = "11203"
    base_url: str = "https://www.abercrombie.com"
    store_path: str = "/shop/wd-es"
    timeout: float = 30.0
    verify_tls: bool = True
    bootstrap_enabled: bool = True
    bootstrap_retries: int = 2
    diagnostics_dir: Path = Path("diagnostics")
    verbose: bool = True
    user_agent: str = (
        "Browser/immroa/0.0.1 "
        "(HackerOne User, https://hackerone.com/immroa?type=user)"
    )
    bug_bounty_header: str = "HackerOne"
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self.diagnostics_dir = Path(self.diagnostics_dir)
        if self.timeout <= 0:
            raise ValueError("timeout debe ser mayor que 0.")
        if self.bootstrap_retries < 0:
            raise ValueError("bootstrap_retries no puede ser negativo.")

    @property
    def api_url(self) -> str:
        params = {
            "brand": self.brand,
            "catalogId": self.catalog_id,
            "country": self.country,
            "langId": self.lang_id,
            "store": self.store,
            "storeId": self.store_id,
        }
        return f"{self.base_url}/api/bff/customer?{urlencode(params)}"

    @property
    def store_url(self) -> str:
        path = self.store_path
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    @property
    def common_headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "X-Bug-Bounty": self.bug_bounty_header,
            "Accept-Language": "es-EC,es;q=0.9,en;q=0.7",
        }
        headers.update(self.extra_headers)
        return headers

    @property
    def navigation_headers(self) -> dict[str, str]:
        return {
            **self.common_headers,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
        }

    def graphql_headers(self, referer: str) -> dict[str, str]:
        return {
            **self.common_headers,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": referer,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
