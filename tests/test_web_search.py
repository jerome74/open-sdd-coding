"""C-26: provider Tavily, normalizzazione, retry, errori espliciti (spec 06)."""

from __future__ import annotations

import logging

import pytest

from agente.config import SearchConfig
from agente.errors import SearchError
from agente.web_search import (
    DEFAULT_RESULTS,
    MAX_RESULTS,
    Result,
    WebSearchAdapter,
    format_results,
)

API_KEY = "tavily-secret-key"


class FakeResponse:
    def __init__(self, payload=None, *, status_code: int = 200, invalid_json: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("json non valido")
        return self._payload


class FakeClient:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, *, json):
        self.calls.append({"url": url, "json": json})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def config(provider: str = "tavily", api_key: str = API_KEY) -> SearchConfig:
    return SearchConfig(provider=provider, api_key=api_key)


def adapter(client: FakeClient, **kwargs) -> WebSearchAdapter:
    kwargs.setdefault("retry_attempts", 1)
    kwargs.setdefault("sleep", lambda _: None)
    return WebSearchAdapter(config(), http_client=client, **kwargs)


def test_search_returns_normalized_results() -> None:
    client = FakeClient(
        [
            FakeResponse(
                {
                    "results": [
                        {
                            "title": "Titolo",
                            "url": "https://example.test/a",
                            "content": "Estratto",
                        }
                    ]
                }
            )
        ]
    )

    results = adapter(client).search("meteo", 3)

    assert results == [Result("Titolo", "https://example.test/a", "Estratto")]
    assert client.calls[0]["url"] == "https://api.tavily.com/search"
    assert client.calls[0]["json"] == {
        "api_key": API_KEY,
        "query": "meteo",
        "max_results": 3,
    }


def test_empty_result_list_is_not_an_error() -> None:
    client = FakeClient([FakeResponse({"results": []})])

    assert adapter(client).search("meteo") == []


def test_malformed_payload_is_an_explicit_error() -> None:
    client = FakeClient([FakeResponse({"boh": []})])

    with pytest.raises(SearchError, match="malformata"):
        adapter(client).search("meteo")


def test_malformed_json_is_an_explicit_error() -> None:
    client = FakeClient([FakeResponse(invalid_json=True)])

    with pytest.raises(SearchError, match="malformata"):
        adapter(client).search("meteo")


def test_retryable_error_is_retried() -> None:
    client = FakeClient(
        [
            FakeResponse(status_code=503),
            FakeResponse({"results": [{"title": "t", "url": "u", "content": "c"}]}),
        ]
    )
    search = adapter(client, retry_attempts=2)

    assert search.search("meteo") == [Result("t", "u", "c")]
    assert len(client.calls) == 2


def test_retry_exhaustion_is_an_explicit_error() -> None:
    client = FakeClient([FakeResponse(status_code=500), FakeResponse(status_code=500)])

    with pytest.raises(SearchError, match="non raggiungibile"):
        adapter(client, retry_attempts=2).search("meteo")


def test_permanent_error_is_not_retried() -> None:
    client = FakeClient([FakeResponse(status_code=401)])

    with pytest.raises(SearchError, match="credenziali"):
        adapter(client, retry_attempts=3).search("meteo")
    assert len(client.calls) == 1


def test_unconfigured_provider_raises_an_explicit_error() -> None:
    client = FakeClient([])
    search = WebSearchAdapter(config(provider=""), http_client=client)

    assert search.available is False
    with pytest.raises(SearchError, match="non configurata"):
        search.search("meteo")
    assert client.calls == []


def test_unsupported_provider_raises_an_explicit_error() -> None:
    search = WebSearchAdapter(config(provider="brave"), http_client=FakeClient([]))

    with pytest.raises(SearchError, match="non supportato"):
        search.search("meteo")


def test_missing_key_raises_an_explicit_error() -> None:
    search = WebSearchAdapter(config(api_key=""), http_client=FakeClient([]))

    with pytest.raises(SearchError, match="SEARCH_API_KEY"):
        search.search("meteo")


def test_missing_query_is_an_explicit_error() -> None:
    with pytest.raises(SearchError, match="mancante"):
        adapter(FakeClient([])).search("   ")


def test_k_is_clamped_and_defaulted() -> None:
    client = FakeClient([FakeResponse({"results": []}) for _ in range(2)])

    adapter(client).search("meteo", 99)
    adapter(client).search("meteo")

    assert client.calls[0]["json"]["max_results"] == MAX_RESULTS
    assert client.calls[1]["json"]["max_results"] == DEFAULT_RESULTS


def test_api_key_is_never_logged(caplog) -> None:
    client = FakeClient(
        [
            FakeResponse(
                {"results": [{"title": "t", "url": "u", "content": "c"}]}
            )
        ]
    )
    with caplog.at_level(logging.INFO, logger="agente.web_search"):
        adapter(client).search("meteo")

    assert API_KEY not in caplog.text


def test_query_and_latency_are_logged(caplog) -> None:
    client = FakeClient([FakeResponse({"results": []})])
    with caplog.at_level(logging.INFO, logger="agente.web_search"):
        adapter(client).search("meteo domani")

    record = next(r for r in caplog.records if r.message == "ricerca web completata")
    assert record.query == "meteo domani"
    assert isinstance(record.duration_ms, int)


def test_unavailable_provider_logs_a_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="agente.web_search"):
        WebSearchAdapter(config(provider=""), http_client=FakeClient([]))

    record = next(r for r in caplog.records if r.message == "ricerca web non disponibile")
    assert record.reason == "search.provider vuoto"


def test_format_results_includes_title_url_and_snippet() -> None:
    text = format_results([Result("Titolo", "https://example.test", "Estratto")])

    assert "1. Titolo — https://example.test" in text
    assert "Estratto" in text
    assert format_results([]) == "Nessun risultato."
