"""Helpers de teste: carregador de fixtures e um transporte HTTP falso (sem rede)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
_MISSING = object()


@pytest.fixture
def fx():
    """Devolve ``load(name)`` → texto da fixture em ``tests/fixtures/``."""

    def _load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture
def fx_json(fx):
    def _load(name: str) -> Any:
        return json.loads(fx(name))

    return _load


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "", json_data: Any = _MISSING) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_data

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")

    def json(self) -> Any:
        return json.loads(self.text) if self._json is _MISSING else self._json


class FakeHTTP:
    """Roteia ``request`` por ``(method, path)``.

    Um route pode ser: :class:`FakeResponse`, uma exceção (instância ou classe) para
    levantar, ou uma ``list`` consumida em sequência (uma entrada por chamada).
    """

    def __init__(self, routes: dict[Any, Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(self, method, url, *, params=None, data=None, headers=None, timeout=None):
        path = urlsplit(url).path or "/"
        self.calls.append(
            {"method": method, "path": path, "params": params, "data": data, "headers": headers}
        )
        route = self.routes.get((method, path), self.routes.get(path, _MISSING))
        if route is _MISSING:
            raise AssertionError(f"FakeHTTP: rota não configurada para {method} {path}")
        if isinstance(route, list):
            route = route.pop(0)
        if isinstance(route, type) and issubclass(route, BaseException):
            raise route()
        if isinstance(route, BaseException):
            raise route
        return route

    def paths(self) -> list[str]:
        return [c["path"] for c in self.calls]


@pytest.fixture
def make_http():
    return FakeHTTP
