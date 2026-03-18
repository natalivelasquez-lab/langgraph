from __future__ import annotations

import csv
import json
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

logger = logging.getLogger("langgraph-demo.tool.sql")

FORBIDDEN_SQL_PATTERNS = (
    r"\binsert\b",
    r"\bupdate\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\balter\b",
    r"\btruncate\b",
    r"\bgrant\b",
    r"\brevoke\b",
    r"\bcreate\b",
    r"\bmerge\b",
    r"\bcall\b",
    r"\bexec\b",
)

CSV_ALIASES = {
    "schema_name": ("schema_name", "schema", "esquema"),
    "table_name": ("table_name", "table", "tabla"),
    "column_name": ("column_name", "column", "columna"),
    "column_description": (
        "column_description",
        "description",
        "descripcion",
        "column_desc",
    ),
    "data_type": ("data_type", "type", "tipo_dato", "tipo"),
    "data_format": ("data_format", "format", "formato_dato", "formato"),
    "related_table": (
        "related_table",
        "join_table",
        "tabla_relacionada",
        "foreign_table",
    ),
    "related_column": (
        "related_column",
        "join_column",
        "columna_relacionada",
        "foreign_column",
    ),
}


class SQLQueryInput(BaseModel):
    question: str = Field(
        ...,
        description="Pregunta de negocio en lenguaje natural sobre los datos SQL.",
    )
    database_url: str | None = Field(
        default=None,
        description=(
            "Cadena de conexión compatible con SQLAlchemy. "
            "Si no se envía, se usa SQL_DATABASE_URL."
        ),
    )
    schema_csv_path: str | None = Field(
        default=None,
        description=(
            "Ruta local al CSV con metadata del esquema. "
            "Si no se envía, se usa SQL_SCHEMA_CSV_PATH."
        ),
    )
    sql_query: str | None = Field(
        default=None,
        description=(
            "Consulta SQL opcional. Si no se envía, la tool la generará "
            "a partir de la pregunta y el esquema."
        ),
    )
    max_rows: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Máximo de filas a devolver.",
    )


def _get_sql_llm() -> AzureChatOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = os.getenv(
        "AZURE_OPENAI_SQL_DEPLOYMENT",
        os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
    )

    if not endpoint:
        raise RuntimeError("Falta AZURE_OPENAI_ENDPOINT.")
    if not api_key:
        raise RuntimeError("Falta AZURE_OPENAI_API_KEY.")
    if not deployment:
        raise RuntimeError(
            "Falta AZURE_OPENAI_SQL_DEPLOYMENT o AZURE_OPENAI_CHAT_DEPLOYMENT."
        )

    return AzureChatOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
        azure_deployment=deployment,
        temperature=0,
    )


def _resolve_repo_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path

    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / path


def _normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def _pick_value(row: dict[str, str], logical_name: str) -> str:
    for alias in CSV_ALIASES[logical_name]:
        value = row.get(alias)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _load_schema_metadata(schema_csv_path: str) -> list[dict[str, str]]:
    path = _resolve_repo_path(schema_csv_path)
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de esquema: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("El CSV de esquema no tiene encabezados.")

        normalized_rows: list[dict[str, str]] = []
        for raw_row in reader:
            row = {_normalize_header(k): (v or "").strip() for k, v in raw_row.items() if k}
            normalized_rows.append(
                {
                    "schema_name": _pick_value(row, "schema_name"),
                    "table_name": _pick_value(row, "table_name"),
                    "column_name": _pick_value(row, "column_name"),
                    "column_description": _pick_value(row, "column_description"),
                    "data_type": _pick_value(row, "data_type"),
                    "data_format": _pick_value(row, "data_format"),
                    "related_table": _pick_value(row, "related_table"),
                    "related_column": _pick_value(row, "related_column"),
                }
            )

    rows = [row for row in normalized_rows if row["table_name"] and row["column_name"]]
    if not rows:
        raise ValueError(
            "El CSV de esquema no contiene filas válidas con table_name y column_name."
        )
    return rows


def _build_schema_summary(rows: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    relations: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        schema = row["schema_name"] or "default"
        table_key = f"{schema}.{row['table_name']}"
        grouped[table_key].append(row)

        if row["related_table"] and row["related_column"]:
            relation = (
                f"{row['column_name']} -> "
                f"{row['related_table']}.{row['related_column']}"
            )
            relations[table_key].append(relation)

    parts: list[str] = []
    for table_name in sorted(grouped):
        parts.append(f"Tabla {table_name}:")
        for column in grouped[table_name]:
            detail = f"- {column['column_name']} ({column['data_type'] or 'tipo no informado'})"
            extras: list[str] = []
            if column["column_description"]:
                extras.append(column["column_description"])
            if column["data_format"]:
                extras.append(f"formato: {column['data_format']}")
            if extras:
                detail += f" | {' | '.join(extras)}"
            parts.append(detail)

        if relations[table_name]:
            parts.append("Relaciones sugeridas:")
            for relation in relations[table_name]:
                parts.append(f"- {relation}")

        parts.append("")

    return "\n".join(parts).strip()


def _sanitize_sql(sql_query: str) -> str:
    sql = sql_query.strip()
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = sql.strip().rstrip(";").strip()
    return sql


def _validate_read_only_query(sql_query: str) -> None:
    sql = _sanitize_sql(sql_query)
    lowered = sql.lower()

    if not sql:
        raise ValueError("La consulta SQL quedó vacía.")

    if ";" in sql:
        raise ValueError("Solo se permite una consulta SQL por ejecución.")

    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("Solo se permiten consultas de lectura que inicien con SELECT o WITH.")

    for pattern in FORBIDDEN_SQL_PATTERNS:
        if re.search(pattern, lowered):
            raise ValueError(
                "La consulta contiene una operación no permitida para este workshop."
            )


def _detect_dialect(database_url: str) -> str:
    try:
        return create_engine(database_url).dialect.name
    except Exception:
        return "sql"


def _generate_sql_from_question(
    *,
    question: str,
    schema_summary: str,
    database_url: str,
    max_rows: int,
) -> str:
    dialect = _detect_dialect(database_url)
    llm = _get_sql_llm()

    prompt = f"""
Eres un generador de SQL para un workshop de LangGraph.
Debes responder SOLO con una consulta SQL de lectura.

Reglas:
- Dialecto objetivo: {dialect}
- Usa exclusivamente tablas y columnas del esquema entregado.
- Si la pregunta requiere joins, usa las relaciones sugeridas.
- Devuelve como máximo {max_rows} filas.
- No escribas markdown, explicaciones ni comentarios.
- No uses INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC.

Esquema disponible:
{schema_summary}

Pregunta:
{question}
""".strip()

    response = llm.invoke(prompt)
    sql_query = getattr(response, "content", str(response))
    return _sanitize_sql(sql_query)


def _serialize_rows(columns: list[str], rows: list[Any]) -> str:
    payload = [dict(zip(columns, row, strict=False)) for row in rows]
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


@tool(
    "query_sql_database",
    args_schema=SQLQueryInput,
    description=(
        "Consulta una base de datos SQL estructurada usando metadata de esquema en CSV. "
        "Úsala para responder preguntas analíticas o de negocio sobre tablas relacionales. "
        "Acepta una pregunta natural, la conexión a base de datos y el CSV de esquema; "
        "puede generar el SQL automáticamente o ejecutar un SQL de solo lectura provisto."
    ),
)
def query_sql_database(
    question: str,
    database_url: str | None = None,
    schema_csv_path: str | None = None,
    sql_query: str | None = None,
    max_rows: int = 20,
) -> str:
    logger.info("🗄️ [TOOL sql] Ejecutando query_sql_database")

    database_url = (database_url or os.getenv("SQL_DATABASE_URL", "")).strip()
    schema_csv_path = (schema_csv_path or os.getenv("SQL_SCHEMA_CSV_PATH", "")).strip()

    if not database_url:
        return (
            "No recibí `database_url` y tampoco existe `SQL_DATABASE_URL` en el entorno."
        )
    if not schema_csv_path:
        return (
            "No recibí `schema_csv_path` y tampoco existe `SQL_SCHEMA_CSV_PATH` en el entorno."
        )

    try:
        schema_rows = _load_schema_metadata(schema_csv_path)
        schema_summary = _build_schema_summary(schema_rows)

        final_sql = _sanitize_sql(sql_query) if sql_query else _generate_sql_from_question(
            question=question,
            schema_summary=schema_summary,
            database_url=database_url,
            max_rows=max_rows,
        )

        _validate_read_only_query(final_sql)
        logger.info("🗄️ [TOOL sql] SQL final: %s", final_sql)

        engine = create_engine(database_url)
        with engine.connect() as connection:
            result = connection.execute(text(final_sql))
            columns = list(result.keys())
            rows = result.fetchmany(max_rows)

        if not columns:
            return (
                "La consulta se ejecutó, pero no devolvió columnas. "
                f"SQL usado:\n{final_sql}"
            )

        if not rows:
            return (
                "La consulta no devolvió filas.\n"
                f"SQL usado:\n{final_sql}\n"
                "Puedes reformular la pregunta si necesitas otro filtro."
            )

        serialized_rows = _serialize_rows(columns, rows)
        return (
            f"SQL usado:\n{final_sql}\n\n"
            f"Columnas: {', '.join(columns)}\n"
            f"Filas devueltas (máximo {max_rows}):\n{serialized_rows}"
        )

    except Exception as exc:
        logger.error("❌ [TOOL sql] Error consultando base de datos", exc_info=True)
        return (
            "Ocurrió un error consultando la base de datos.\n"
            f"Detalle técnico: {type(exc).__name__}: {exc}"
        )
