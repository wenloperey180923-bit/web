"""Conexión a la base de datos.

- En tu computadora (sin variables de entorno) se usa SQLite en
  instance/awos.sqlite3, igual que antes.
- En Render se usa la base de Aiven indicada en DATABASE_URL:
    postgres://...  -> PostgreSQL (plan gratis de Aiven)
    mysql://...     -> MySQL

El resto de app.py no necesita saber cuál se está usando: estas clases imitan
la parte de sqlite3 que usa la aplicación (execute, executemany,
executescript, commit, close, filas con acceso por nombre y por posición).
"""
from __future__ import annotations

import os
import re
import sqlite3
import ssl
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
_scheme = urlparse(DATABASE_URL).scheme if DATABASE_URL else ""

if _scheme in ("postgres", "postgresql"):
    ENGINE = "postgres"
elif _scheme in ("mysql", "mysql+pymysql"):
    ENGINE = "mysql"
elif DATABASE_URL:
    raise RuntimeError("DATABASE_URL debe empezar con postgres:// o mysql://")
else:
    ENGINE = "sqlite"

if ENGINE == "postgres":
    import psycopg2

    INTEGRITY_ERRORS: tuple[type[BaseException], ...] = (
        sqlite3.IntegrityError, psycopg2.IntegrityError,
    )
elif ENGINE == "mysql":
    import pymysql

    INTEGRITY_ERRORS = (sqlite3.IntegrityError, pymysql.err.IntegrityError)
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

# Compatibilidad con app.py: verdadero cuando no es SQLite.
MYSQL = ENGINE != "sqlite"


def _plain(value: Any) -> Any:
    """Convierte los tipos del servidor a los mismos que devolvía SQLite."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return value


class Row(tuple):
    """Fila que funciona como sqlite3.Row: row[0], row["campo"] y dict(row)."""

    def __new__(cls, values, names):
        row = super().__new__(cls, (_plain(v) for v in values))
        row._names = {name: i for i, name in enumerate(names)}
        return row

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._names[key])
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._names)


class Cursor:
    def __init__(self, cursor, lastrowid=None, rows=None):
        self._cursor = cursor
        self.lastrowid = lastrowid
        self._rows = rows

    def _names(self):
        return [col[0] for col in (self._cursor.description or ())]

    def fetchone(self):
        if self._rows is not None:
            return Row(self._rows.pop(0), self._names()) if self._rows else None
        values = self._cursor.fetchone()
        return None if values is None else Row(values, self._names())

    def fetchall(self):
        names = self._names()
        if self._rows is not None:
            rows, self._rows = self._rows, []
            return [Row(v, names) for v in rows]
        return [Row(values, names) for values in self._cursor.fetchall()]


# --- Pequeñas diferencias de SQL respecto a SQLite -------------------------
_TIME_RE = re.compile(r"strftime\('%H:%M:%S',\s*([\w.]+)\)")
_IGNORE_RE = re.compile(r"INSERT OR IGNORE", re.I)


def _placeholders(sql: str, has_params: bool) -> str:
    if has_params:
        sql = sql.replace("%", "%%").replace("?", "%s")
    return sql


def _to_mysql(sql: str, has_params: bool) -> str:
    sql = _IGNORE_RE.sub("INSERT IGNORE", sql)
    sql = _TIME_RE.sub(r"DATE_FORMAT(\1,'%H:%i:%s')", sql)
    return _placeholders(sql, has_params)


def _to_postgres(sql: str, has_params: bool) -> str:
    if _IGNORE_RE.search(sql):
        sql = _IGNORE_RE.sub("INSERT", sql).rstrip() + " ON CONFLICT DO NOTHING"
    sql = _TIME_RE.sub(r"to_char(\1,'HH24:MI:SS')", sql)
    # En SQLite LIKE no distingue mayúsculas; en PostgreSQL eso es ILIKE.
    sql = re.sub(r"\bLIKE\b", "ILIKE", sql)
    return _placeholders(sql, has_params)


class ServerConnection:
    """Conexión a PostgreSQL o MySQL con la misma interfaz que sqlite3."""

    def __init__(self):
        if ENGINE == "postgres":
            self._conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
            self._translate = _to_postgres
        else:
            self._conn = _mysql_connect()
            self._translate = _to_mysql

    def _run(self, action):
        try:
            return action()
        except Exception:
            # PostgreSQL bloquea la transacción tras un error: se reinicia.
            self._conn.rollback()
            raise

    def execute(self, sql: str, params=()):
        params = tuple(params) if params else None
        query = self._translate(sql, params is not None)
        returning = (
            ENGINE == "postgres"
            and query.lstrip().upper().startswith("INSERT")
            and "ON CONFLICT" not in query.upper()
        )
        if returning:
            query = query.rstrip() + " RETURNING id"

        def action():
            cursor = self._conn.cursor()
            cursor.execute(query, params)
            if returning:
                return Cursor(cursor, lastrowid=cursor.fetchone()[0], rows=[])
            return Cursor(cursor, lastrowid=getattr(cursor, "lastrowid", None))

        return self._run(action)

    def executemany(self, sql: str, seq):
        query = self._translate(sql, True)

        def action():
            cursor = self._conn.cursor()
            cursor.executemany(query, [tuple(p) for p in seq])
            return Cursor(cursor, rows=[])

        return self._run(action)

    def executescript(self, script: str) -> None:
        def action():
            cursor = self._conn.cursor()
            for statement in script.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            self._conn.commit()

        try:
            self._run(action)
        except Exception:
            # Si dos procesos crean las tablas a la vez, el segundo reintenta.
            self._run(action)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _mysql_connect():
    parsed = urlparse(DATABASE_URL)
    query = parse_qs(parsed.query)
    use_ssl = query.get("ssl-mode", ["REQUIRED"])[0].upper() != "DISABLED"
    context = None
    if use_ssl:
        ca_file = os.environ.get("DB_SSL_CA_FILE", "/etc/secrets/ca.pem")
        if os.path.isfile(ca_file):
            context = ssl.create_default_context(cafile=ca_file)
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
    return pymysql.connect(
        host=parsed.hostname,
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/").lstrip("/") or "defaultdb",
        charset="utf8mb4",
        ssl=context,
        connect_timeout=15,
    )


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS productos (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    precio DOUBLE PRECISION NOT NULL,
    existencia BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS estudiantes (
    id SERIAL PRIMARY KEY,
    matricula TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    carrera TEXT NOT NULL,
    correo TEXT NOT NULL,
    promedio DOUBLE PRECISION NOT NULL,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS respuestas (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    carrera TEXT NOT NULL,
    factor TEXT NOT NULL,
    instalaciones TEXT NOT NULL,
    mejora TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    id SERIAL PRIMARY KEY,
    visitante_id TEXT NOT NULL,
    sesion_id TEXT NOT NULL,
    usuario_id INTEGER REFERENCES estudiantes(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('vista', 'clic', 'tiempo')),
    pagina TEXT NOT NULL,
    elemento TEXT,
    segundos INTEGER,
    creado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE INDEX IF NOT EXISTS idx_eventos_visitante ON eventos(visitante_id);
CREATE INDEX IF NOT EXISTS idx_eventos_sesion ON eventos(sesion_id);
CREATE TABLE IF NOT EXISTS productos_tienda (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    marca TEXT NOT NULL,
    categoria TEXT NOT NULL,
    precio DOUBLE PRECISION NOT NULL,
    existencia BIGINT NOT NULL,
    codigo_barras TEXT NOT NULL UNIQUE,
    promocion TEXT
);
CREATE TABLE IF NOT EXISTS chat_mensajes (
    id SERIAL PRIMARY KEY,
    autor_matricula TEXT NOT NULL,
    autor_nombre TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
)
"""

MYSQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    precio DOUBLE NOT NULL,
    existencia BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS estudiantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    matricula VARCHAR(255) NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    carrera VARCHAR(255) NOT NULL,
    correo TEXT NOT NULL,
    promedio DOUBLE NOT NULL,
    password_hash TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS respuestas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre TEXT NOT NULL,
    carrera TEXT NOT NULL,
    factor TEXT NOT NULL,
    instalaciones TEXT NOT NULL,
    mejora TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS eventos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    visitante_id VARCHAR(36) NOT NULL,
    sesion_id VARCHAR(36) NOT NULL,
    usuario_id INT NULL,
    tipo VARCHAR(10) NOT NULL CHECK (tipo IN ('vista', 'clic', 'tiempo')),
    pagina VARCHAR(255) NOT NULL,
    elemento VARCHAR(255),
    segundos INT,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_eventos_visitante (visitante_id),
    INDEX idx_eventos_sesion (sesion_id),
    CONSTRAINT fk_eventos_usuario FOREIGN KEY (usuario_id)
        REFERENCES estudiantes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS productos_tienda (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(255) NOT NULL,
    marca VARCHAR(255) NOT NULL,
    categoria VARCHAR(255) NOT NULL,
    precio DOUBLE NOT NULL,
    existencia BIGINT NOT NULL,
    codigo_barras VARCHAR(64) NOT NULL UNIQUE,
    promocion VARCHAR(255)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS chat_mensajes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    autor_matricula VARCHAR(255) NOT NULL,
    autor_nombre TEXT NOT NULL,
    mensaje TEXT NOT NULL,
    creado_en DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

SCHEMA = POSTGRES_SCHEMA if ENGINE == "postgres" else MYSQL_SCHEMA


def connect(sqlite_path) -> Any:
    """Abre la conexión que corresponda (Aiven en Render, SQLite en local)."""
    if ENGINE != "sqlite":
        return ServerConnection()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
