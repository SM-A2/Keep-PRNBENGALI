import asyncio
import json
import logging
import os
import socket
import ssl
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import asyncpg

from logging_setup import log_event

log = logging.getLogger("database")
SCHEMA_PATH = Path(__file__).parent / "database" / "schema.sql"


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


def build_dsn(dsn: str) -> tuple[str, object]:
    """Clean a DATABASE_URL and work out the TLS mode.

    - strips quotes/spaces, accepts postgres:// and postgresql+asyncpg:// forms
    - percent-encodes user/password so special characters (@ : / #) cannot break the host
    - DB_SSL=disable|require|verify overrides; otherwise ?sslmode=... in the URL is honoured
    Returns (dsn_without_ssl_params, ssl_argument_for_asyncpg).
    """
    dsn = dsn.strip().strip("\"'")
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://", "postgres://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]
    parts = urlsplit(dsn)
    if parts.scheme != "postgresql":
        raise RuntimeError("DATABASE_URL must look like postgresql://user:password@host:port/dbname")
    host = parts.hostname or ""
    if not host or host in {"host", "hostname", "your-host", "HOST"} or "<" in dsn or "{" in dsn:
        raise RuntimeError(
            "DATABASE_URL still contains a placeholder instead of the real database host. "
            "Copy the host/port/user/password from the Database tab of your Botkeep PostgreSQL server.")
    query = dict(parse_qsl(parts.query))
    mode = (os.getenv("DB_SSL") or query.pop("sslmode", "") or query.pop("ssl", "")).strip().lower()
    query.pop("sslmode", None)
    query.pop("ssl", None)
    user = quote(unquote(parts.username or ""), safe="")
    pwd = quote(unquote(parts.password or ""), safe="")
    cred = user + (":" + pwd if parts.password is not None else "")
    netloc = (cred + "@" if cred else "") + (f"[{host}]" if ":" in host else host)
    if parts.port:
        netloc += f":{parts.port}"
    clean = urlunsplit(("postgresql", netloc, parts.path, urlencode(query), ""))
    if mode in ("", "disable", "false", "0", "off", "prefer", "allow"):
        ssl_arg: object = False if mode in ("disable", "false", "0", "off") else None
    elif mode in ("verify", "verify-full", "verify-ca"):
        ssl_arg = ssl.create_default_context()
    else:   # require / true / 1 -> encrypted, certificate not verified (typical for managed DBs)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssl_arg = ctx
    return clean, ssl_arg


class Database:
    def __init__(self, dsn: str, min_size: int, max_size: int) -> None:
        self._dsn, self._ssl = build_dsn(dsn)
        self._host = urlsplit(self._dsn).hostname or "?"
        self._min = min_size
        self._max = max(max_size, min_size)
        self.pool: asyncpg.Pool | None = None

    async def connect(self, attempts: int = 5) -> None:
        delay = 3.0
        for attempt in range(1, attempts + 1):
            try:
                kwargs = {} if self._ssl is None else {"ssl": self._ssl}
                self.pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=self._min,
                    max_size=self._max,
                    command_timeout=30,
                    timeout=20,
                    init=_init_connection,
                    **kwargs,
                )
                break
            except socket.gaierror as exc:
                # [Errno -2] Name or service not known: the host in DATABASE_URL does not resolve
                raise RuntimeError(
                    f"Cannot resolve the database host '{self._host}'. DATABASE_URL points to a "
                    "hostname that does not exist from inside Botkeep (e.g. a Railway "
                    "*.railway.internal host or a typo). Use the host/port shown in the Database "
                    "tab of your Botkeep PostgreSQL server."
                ) from exc
            except (OSError, asyncio.TimeoutError, asyncpg.CannotConnectNowError,
                    asyncpg.ConnectionDoesNotExistError) as exc:
                if attempt == attempts:
                    raise
                log_event(log, logging.WARNING, "database_retry", attempt=attempt,
                          host=self._host, error=type(exc).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
        async with self.pool.acquire() as conn:
            await conn.execute("SELECT pg_advisory_lock(7000)")
            try:
                await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            finally:
                await conn.execute("SELECT pg_advisory_unlock(7000)")
        log_event(log, logging.INFO, "database_ready")

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
