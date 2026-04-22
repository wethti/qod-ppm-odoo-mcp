"""Thin Odoo JSON-RPC client.

Wraps /jsonrpc endpoints for `common.authenticate` and `object.execute_kw`.
Cached uid; credentials read from env.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class OdooError(RuntimeError):
    """Raised for Odoo-side errors (auth failure, access denied, validation, ...)."""


class OdooClient:
    def __init__(
        self,
        url: str,
        db: str,
        username: str,
        secret: str,
        timeout: float = 30.0,
    ) -> None:
        if not url or not db or not username or not secret:
            raise OdooError(
                "Missing Odoo credentials. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, "
                "and ODOO_API_KEY (or ODOO_PASSWORD)."
            )
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.secret = secret
        self.timeout = timeout
        self._uid: int | None = None
        self._http = httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls) -> OdooClient:
        secret = os.environ.get("ODOO_API_KEY") or os.environ.get("ODOO_PASSWORD") or ""
        return cls(
            url=os.environ.get("ODOO_URL", ""),
            db=os.environ.get("ODOO_DB", ""),
            username=os.environ.get("ODOO_USERNAME", ""),
            secret=secret,
            timeout=float(os.environ.get("ODOO_TIMEOUT", "30")),
        )

    def _call(self, service: str, method: str, args: list[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
        }
        resp = self._http.post(f"{self.url}/jsonrpc", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            err = data["error"]
            message = err.get("data", {}).get("message") or err.get("message") or str(err)
            raise OdooError(message)
        return data.get("result")

    def authenticate(self) -> int:
        uid = self._call("common", "authenticate", [self.db, self.username, self.secret, {}])
        if not uid:
            raise OdooError("Authentication failed — check ODOO_USERNAME and ODOO_API_KEY.")
        self._uid = uid
        return uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            self.authenticate()
        return self._uid  # type: ignore[return-value]

    def execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        return self._call(
            "object",
            "execute_kw",
            [self.db, self.uid, self.secret, model, method, args or [], kwargs or {}],
        )

    def search_read(
        self,
        model: str,
        domain: list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if offset is not None:
            kwargs["offset"] = offset
        if order is not None:
            kwargs["order"] = order
        return self.execute_kw(model, "search_read", [domain or []], kwargs)

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kwargs = {"fields": fields} if fields else {}
        return self.execute_kw(model, "read", [ids], kwargs)

    def call_action(self, model: str, method: str, ids: list[int]) -> Any:
        """Invoke an `action_*` button method on the given record ids."""
        return self.execute_kw(model, method, [ids])

    def close(self) -> None:
        self._http.close()
