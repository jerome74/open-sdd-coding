"""C-26 Web Search Adapter — ricerca web read-only (spec 06).

Un solo provider attivo per configurazione; **Tavily** è il default scelto
dall'operatore (decisione D2). Il registry ``_PROVIDERS`` è il punto di
estensione: aggiungere un provider significa aggiungere una voce e il relativo
client, senza toccare C-27, C-09 o C-23.

Regole:

- read-only: nessuna conferma (BR-2, A4);
- provider assente, non supportato o senza chiave → ``SearchError`` esplicito
  al momento dell'uso, non un errore fatale all'avvio (D5);
- errori di rete, 429 e 5xx → retry BR-8; 401/403 e 4xx → errore immediato;
- la chiave del provider non compare mai nei log.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .config import SearchConfig
from .errors import SearchError
from .retry import retry_call

logger = logging.getLogger("agente.web_search")

DEFAULT_RESULTS = 5
MAX_RESULTS = 10
TAVILY_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class Result:
    """Risultato normalizzato per il modello."""

    title: str
    url: str
    snippet: str


class _RetryableSearch(Exception):
    """Errore transitorio del provider: rete, 429 o 5xx (BR-8)."""


class _Tavily:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def __call__(self, api_key: str, query: str, k: int) -> list[Result]:
        try:
            response = self._client.post(
                TAVILY_URL,
                json={"api_key": api_key, "query": query, "max_results": k},
            )
        except httpx.HTTPError as exc:
            raise _RetryableSearch(str(exc)) from exc

        status = response.status_code
        if status in (401, 403):
            raise SearchError(
                f"credenziali del provider di ricerca non valide (HTTP {status})"
            )
        if status == 429 or status >= 500:
            raise _RetryableSearch(f"HTTP {status}")
        if status >= 400:
            raise SearchError(f"ricerca web rifiutata (HTTP {status})")

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchError("risposta del provider di ricerca malformata") from exc
        if not isinstance(payload, dict) or not isinstance(
            payload.get("results"), list
        ):
            raise SearchError("risposta del provider di ricerca malformata")

        results: list[Result] = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            if not isinstance(title, str) or not isinstance(url, str):
                continue
            snippet = item.get("content")
            results.append(
                Result(
                    title=title.strip(),
                    url=url.strip(),
                    snippet=snippet.strip() if isinstance(snippet, str) else "",
                )
            )
        return results


_PROVIDERS: dict[str, Callable[[httpx.Client], Callable[[str, str, int], list[Result]]]] = {
    "tavily": _Tavily,
}


class WebSearchAdapter:
    def __init__(
        self,
        config: SearchConfig,
        *,
        http_client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        retry_attempts: int = 3,
        retry_delay_s: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider_name = (config.provider or "").strip().lower()
        self._api_key = config.api_key or ""
        self._client = http_client or httpx.Client(timeout=timeout_s)
        self._retry_attempts = retry_attempts
        self._retry_delay_s = retry_delay_s
        self._sleep = sleep
        self._unavailable = self._check_availability()
        if self._unavailable is not None:
            logger.warning(
                "ricerca web non disponibile", extra={"reason": self._unavailable}
            )

    @property
    def available(self) -> bool:
        return self._unavailable is None

    def search(self, query: str, k: int = DEFAULT_RESULTS) -> list[Result]:
        """Esegue la ricerca e normalizza i risultati (read-only)."""
        if not isinstance(query, str) or not query.strip():
            raise SearchError("query di ricerca mancante")
        if not self.available:
            raise SearchError(f"ricerca web non configurata: {self._unavailable}")
        provider = _PROVIDERS[self._provider_name](self._client)
        limit = _clamp(k)

        started = time.monotonic()
        try:
            results = retry_call(
                lambda: provider(self._api_key, query.strip(), limit),
                attempts=self._retry_attempts,
                delay_s=self._retry_delay_s,
                retry_on=(_RetryableSearch,),
                sleep=self._sleep,
            )
        except _RetryableSearch as exc:
            logger.warning(
                "ricerca web non raggiungibile",
                extra={"provider": self._provider_name, "error": str(exc)},
            )
            raise SearchError(f"provider di ricerca non raggiungibile: {exc}") from exc

        logger.info(
            "ricerca web completata",
            extra={
                "provider": self._provider_name,
                "query": query,
                "k": limit,
                "results": len(results),
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return results

    def _check_availability(self) -> str | None:
        if not self._provider_name:
            return "search.provider vuoto"
        if self._provider_name not in _PROVIDERS:
            return f"provider non supportato: {self._provider_name}"
        if not self._api_key:
            return "SEARCH_API_KEY mancante"
        return None


def _clamp(k: Any) -> int:
    try:
        value = int(k)
    except (TypeError, ValueError) as exc:
        raise SearchError(f"numero di risultati non valido: {k!r}") from exc
    return max(1, min(MAX_RESULTS, value))


def format_results(results: list[Result]) -> str:
    """Testo compatto per il modello: titolo, URL ed estratto."""
    if not results:
        return "Nessun risultato."
    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.title} — {result.url}")
        if result.snippet:
            lines.append(f"   {result.snippet}")
    return "\n".join(lines)
