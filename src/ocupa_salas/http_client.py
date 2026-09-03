"""
Cliente HTTP autenticado (Seam 2) — fluxo encadeado calendário → faixas → capacidade.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
Domínio : CONTEXT.md · docs/adr/ADR-0001 · docs/mapeamento_fonte.md
Dados   : 100% fictícios — a fonte é simulada em mock_server/
Dúvidas : github.com/jlfig13/ocupa-salas/issues

Runtime é HTTP puro (ADR-0001 D2): cookie de sessão vindo da Connection + token CSRF
raspado do ``<meta>`` a cada execução. As manias da fonte são tratadas explicitamente:
``200`` com corpo vazio (falta ``X-Requested-With``) → :class:`EmptyBodyError`; ``401``
→ :class:`SessionExpiredError` ("refazer bootstrap"); ``5xx``/timeout → retry com
backoff, e :class:`UpstreamError` só depois de esgotar as tentativas.

Contexto de sessão (ADR-0001 D7): contas com acesso a mais de um local caem em
``/escolher-contexto`` no ``GET /`` e precisam fixar local (``id_local`` da Connection)
via ``POST /set-contexto`` antes do calendário responder. O passo é condicional — conta
de local único cai direto no calendário e ele é pulado.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from requests import Session
from requests import exceptions as rexc

from ocupa_salas.canary import CanaryResult, check_bloco_integrity
from ocupa_salas.errors import EmptyBodyError, SessionExpiredError, UpstreamError
from ocupa_salas.parser import extract_csrf, extract_faixa_ids, parse_page

_log = logging.getLogger(__name__)

_TRANSIENT_EXC = (rexc.Timeout, rexc.ConnectionError)
# ``X-Requested-With`` só nos POST; o backend checa ``isAjax`` neles e, sem o header,
# responde ``200`` com corpo vazio (mapeamento_fonte.md §6.1).
_POST_XHR_HEADER = {"X-Requested-With": "XMLHttpRequest"}
# Marcas de que a resposta de ``GET /`` é mesmo a tela de calendário autenticada, e não
# um redirect de login SSO devolvido com ``200``.
_AUTH_MARKERS = ('name="csrf-token"', "calendarioReservas")
# Tela "Selecione um Local / Empresa": ``GET /`` cai aqui quando a sessão não tem
# contexto fixado (ADR-0001 D7). Conta com acesso a um único local cai direto no
# calendário e o passo de seleção é pulado.
_PERFIL_SCREEN_MARKER = 'id="escolheLocal"'
# Corpo de sucesso de ``POST /set-contexto`` (``text/plain`` — só o dígito ``1``).
_SET_CONTEXTO_OK = "1"


@dataclass
class Connection:
    """Dados de conexão — espelha o campo ``Extra`` da Airflow Connection."""

    base_url: str
    cookie: str
    id_local: str
    # Filtro opcional de empresa na tela ``/escolher-contexto`` (ADR-0001 D7). O BI de
    # ocupação é por local e o local sozinho já libera o calendário; só preencher se um
    # recorte por empresa for necessário. Vazio → passo de empresa não é executado.
    id_empresa: str = ""
    timeout: float = 30.0
    max_attempts: int = 4
    backoff_base: float = 0.5

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Connection:
        try:
            base_url = data.get("base_url") or data["host"]
            return cls(
                base_url=str(base_url).rstrip("/"),
                cookie=str(data["cookie"]),
                id_local=str(data["id_local"]),
                id_empresa=str(data.get("id_empresa", "") or ""),
                timeout=float(data.get("timeout", 30.0)),
                max_attempts=int(data.get("max_attempts", 4)),
                backoff_base=float(data.get("backoff_base", 0.5)),
            )
        except KeyError as exc:
            raise KeyError(f"Connection sem chave obrigatória: {exc}") from exc


@dataclass
class CollectResult:
    """Saída de :meth:`ReservaSpaceClient.collect`."""

    reservas: list[dict[str, Any]] = field(default_factory=list)
    blocos: list[dict[str, Any]] = field(default_factory=list)
    capacidade: list[dict[str, Any]] = field(default_factory=list)
    canarios: list[CanaryResult] = field(default_factory=list)


class ReservaSpaceClient:
    """Encapsula o fluxo HTTP. ``http`` e ``sleep`` são injetáveis para teste sem rede."""

    def __init__(
        self,
        conn: Connection,
        *,
        http: Any | None = None,
        sleep: Callable[[float], None] | None = None,
        on_alert: Callable[[str], None] | None = None,
    ) -> None:
        self._conn = conn
        self._http = http if http is not None else Session()
        self._sleep = sleep if sleep is not None else time.sleep
        self._on_alert = on_alert if on_alert is not None else (lambda m: _log.warning(m))
        # HTML de ``/escolher-contexto`` da última seleção de contexto, exposto em
        # ``fetch_raw`` para o bootstrap gravar/scrubar. ``None`` se o passo foi pulado.
        self._last_escolher_contexto: str | None = None

    # -- transporte -----------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self._conn.base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        hdrs = {"Cookie": self._conn.cookie, **(headers or {})}
        last_exc: Exception | None = None
        for attempt in range(1, self._conn.max_attempts + 1):
            try:
                resp = self._http.request(
                    method,
                    self._url(path),
                    params=dict(params) if params else None,
                    data=dict(data) if data else None,
                    headers=hdrs,
                    timeout=self._conn.timeout,
                )
            except _TRANSIENT_EXC as exc:
                last_exc = exc
            else:
                status = resp.status_code
                if status == 401:
                    raise SessionExpiredError(f"{method} {path}")
                if status < 500:
                    return resp
                last_exc = UpstreamError(f"{method} {path} → HTTP {status}")

            if attempt < self._conn.max_attempts:
                delay = self._conn.backoff_base * (2 ** (attempt - 1))
                _log.info(
                    "tentativa %d/%d falhou (%s); backoff %.2fs",
                    attempt,
                    self._conn.max_attempts,
                    last_exc,
                    delay,
                )
                self._sleep(delay)

        msg = f"fonte não respondeu após {self._conn.max_attempts} tentativas: {last_exc}"
        self._on_alert(msg)
        raise UpstreamError(msg) from last_exc

    @staticmethod
    def _text_or_empty_error(resp: Any, path: str) -> str:
        text = resp.text or ""
        if resp.status_code == 200 and not text.strip():
            raise EmptyBodyError(
                f"{path}: 200 OK com corpo vazio — provável falta de 'X-Requested-With'"
            )
        return text

    @staticmethod
    def _require_authenticated_page(html: str) -> str:
        """Levanta :class:`SessionExpiredError` se ``html`` não for a tela autenticada."""
        if not all(marker in html for marker in _AUTH_MARKERS):
            raise SessionExpiredError("GET / não devolveu a tela de calendário (login SSO?)")
        return html

    def _perfis(self) -> list[tuple[str, str]]:
        """Perfis a fixar na sessão: sempre ``local``; ``empresa`` só se configurada."""
        perfis = [("local", self._conn.id_local)]
        if self._conn.id_empresa:
            perfis.append(("empresa", self._conn.id_empresa))
        return perfis

    def _select_contexto(self) -> None:
        """Fixa local (e empresa, se houver) na sessão via ``POST /set-contexto`` (D7).

        A tela ``/escolher-contexto`` carrega o par CSRF nas ``<meta>`` como qualquer
        página; é de lá que o token é raspado. O contexto fica gravado server-side
        contra o cookie de sessão — a resposta não traz ``Set-Cookie``. Sucesso é o
        corpo ``"1"`` (``text/plain``). Cada perfil é um POST próprio, com ``parametros``
        = ``{"perfil": "local"|"empresa", "id": <id>}`` JSON.
        """
        view = self._text_or_empty_error(
            self._request("GET", "/escolher-contexto"), "GET /escolher-contexto"
        )
        self._last_escolher_contexto = view
        csrf = extract_csrf(view)
        for perfil, ident in self._perfis():
            body = {"parametros": json.dumps({"perfil": perfil, "id": ident})}
            text = self._text_or_empty_error(
                self._request(
                    "POST",
                    "/set-contexto",
                    data=body,
                    headers={**_POST_XHR_HEADER, "X-CSRF-Token": csrf.token},
                ),
                "POST /set-contexto",
            ).strip()
            if text != _SET_CONTEXTO_OK:
                raise UpstreamError(
                    f"POST /set-contexto (perfil={perfil}, id={ident}) devolveu "
                    f"{text[:40]!r}, esperado {_SET_CONTEXTO_OK!r}"
                )

    def _get_calendar_html(self) -> str:
        """``GET /`` com seleção de contexto sob demanda (ADR-0001 D7).

        Sessão sem local fixado → ``GET /`` cai em ``/escolher-contexto`` (marcador
        ``_PERFIL_SCREEN_MARKER``); nesse caso roda :meth:`_select_contexto` e repete o
        ``GET /``. Conta com acesso a um único local já cai no calendário e o passo
        extra é pulado.
        """
        html = self._text_or_empty_error(self._request("GET", "/"), "GET /")
        if _PERFIL_SCREEN_MARKER in html:
            self._select_contexto()
            html = self._text_or_empty_error(self._request("GET", "/"), "GET /")
        return self._require_authenticated_page(html)

    def _fetch_pages(self) -> tuple[str, str, dict[str, str]]:
        """Roda o encadeamento HTTP; devolve ``(calendario, local, {faixa: capacidade})`` crus."""
        html = self._get_calendar_html()
        csrf = extract_csrf(html)
        loc_html = self._text_or_empty_error(
            self._request(
                "GET", "/painel-config/local", params={"idLocal": self._conn.id_local}
            ),
            "GET /painel-config/local",
        )
        caps: dict[str, str] = {}
        for faixa_id in extract_faixa_ids(loc_html):
            body = {
                "parametros": json.dumps({"idFaixaHorario": faixa_id}),
                csrf.param: csrf.token,
            }
            # mapeamento_fonte.md §6.1: o POST exige o token CSRF no corpo (campo
            # ``csrf-param``) E no header ``X-CSRF-Token``, além do ``X-Requested-With``.
            caps[faixa_id] = self._text_or_empty_error(
                self._request(
                    "POST",
                    "/painel-config/get-salas",
                    data=body,
                    headers={**_POST_XHR_HEADER, "X-CSRF-Token": csrf.token},
                ),
                "POST /painel-config/get-salas",
            )
        return html, loc_html, caps

    # -- passos do fluxo ----------------------------------------------------

    def fetch_raw(self) -> dict[str, str]:
        """Corpos crus do ciclo, nomeados para gravação em ``.captures/`` (bootstrap)."""
        html, loc_html, caps = self._fetch_pages()
        raw = {"calendar.html": html, "local.html": loc_html}
        if self._last_escolher_contexto is not None:
            raw["escolher-contexto.html"] = self._last_escolher_contexto
        raw.update({f"get-salas_{fid}.json": text for fid, text in caps.items()})
        return raw

    def check_session(self, *, raise_on_invalid: bool = True) -> bool:
        """Health check do cookie — primeira task da DAG (spec, user story 11).

        Sucesso → ``True``. Sessão inválida (``401`` **ou** ``200`` com página de login)
        → :class:`SessionExpiredError` (falha alta) por padrão; com
        ``raise_on_invalid=False`` devolve ``False``.

        Prova "calendário alcançável", não só "cookie vivo": se a sessão cair em
        ``/escolher-contexto``, seleciona o contexto (D7) antes de validar.
        """
        try:
            self._get_calendar_html()
        except SessionExpiredError:
            if raise_on_invalid:
                raise
            return False
        return True

    def collect(self) -> CollectResult:
        """Executa ``GET /`` → ``GET /painel-config/local`` → ``POST get-salas``."""
        html, _, caps = self._fetch_pages()
        parsed = parse_page(html)

        result = CollectResult()
        for bloco in parsed.blocos:
            canario = check_bloco_integrity(bloco, on_alert=lambda r: self._on_alert(r.detail))
            result.canarios.append(canario)
            result.blocos.append(
                {
                    "id": bloco.id,
                    "title": bloco.title,
                    "start": bloco.start,
                    "end": bloco.end,
                    "count_por_status": bloco.count_por_status,
                    "canario_falhou": canario.canario_falhou,
                }
            )
            for rec in bloco.reservas:
                result.reservas.append(
                    {
                        "payload": rec.payload,
                        "hash_linha": rec.hash_linha,
                        "bloco_title": bloco.title,
                        "canario_falhou": canario.canario_falhou,
                    }
                )

        for faixa_id, text in caps.items():
            for sala in json.loads(text):
                sala.setdefault("idFaixaHorario", faixa_id)
                result.capacidade.append(sala)

        return result


def _as_connection(conn: Connection | Mapping[str, Any]) -> Connection:
    return conn if isinstance(conn, Connection) else Connection.from_mapping(conn)


def collect(conn: Connection | Mapping[str, Any], **kwargs: Any) -> CollectResult:
    """Atalho de módulo: constrói o cliente e roda :meth:`ReservaSpaceClient.collect`."""
    return ReservaSpaceClient(_as_connection(conn), **kwargs).collect()


def check_session(conn: Connection | Mapping[str, Any], **kwargs: Any) -> bool:
    """Atalho de módulo para o health check (primeira task da DAG)."""
    raise_on_invalid = kwargs.pop("raise_on_invalid", True)
    return ReservaSpaceClient(_as_connection(conn), **kwargs).check_session(
        raise_on_invalid=raise_on_invalid
    )
