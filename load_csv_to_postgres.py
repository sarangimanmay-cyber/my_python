#!/usr/bin/env python3
"""Load a CSV file into a PostgreSQL table."""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import psycopg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load a CSV file into a PostgreSQL table")
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("--table", required=True, help="Target PostgreSQL table name")
    parser.add_argument("--schema", default="public", help="Target schema (default: public)")
    parser.add_argument("--create-table", action="store_true", help="Create the table automatically from the CSV headers")
    parser.add_argument("--delimiter", default=",", help="CSV delimiter (default: ,)")
    parser.add_argument("--encoding", default="utf-8", help="CSV file encoding")
    parser.add_argument("--skip-rows", type=int, default=0, help="Number of rows to skip before reading the header")
    parser.add_argument("--config", default="db_config.json", help="Path to a JSON file containing database connection settings")
    parser.add_argument("--dry-run", action="store_true", help="Validate the CSV and print what would happen without connecting to PostgreSQL")
    return parser.parse_args()


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def infer_sql_type(values: list[str]) -> str:
    non_empty = [value for value in values if value not in {"", None}]
    if not non_empty:
        return "text"

    try:
        for value in non_empty:
            int(value)
        return "integer"
    except ValueError:
        pass

    try:
        for value in non_empty:
            float(value)
        return "double precision"
    except ValueError:
        return "text"


def read_csv_rows(csv_path: Path, delimiter: str, encoding: str, skip_rows: int) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)

        for _ in range(skip_rows):
            next(reader, None)

        header = next(reader, None)
        if not header:
            raise ValueError("The CSV file is empty")

        header = [column.strip() for column in header]
        rows: list[dict[str, str]] = []

        for row in reader:
            if not row:
                continue
            row_dict = {}
            for index, column_name in enumerate(header):
                value = row[index] if index < len(row) else ""
                row_dict[column_name] = value.strip()
            rows.append(row_dict)

    return header, rows


def build_create_table_sql(schema: str, table: str, columns: list[str], inferred_types: dict[str, str]) -> str:
    column_definitions = []
    for column in columns:
        sql_type = inferred_types[column]
        column_definitions.append(f"{quote_ident(column)} {sql_type}")

    table_ref = f"{quote_ident(schema)}.{quote_ident(table)}"
    return f"CREATE TABLE IF NOT EXISTS {table_ref} ({', '.join(column_definitions)});"


def load_db_config(config_path: Path) -> dict[str, str]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("The database config file must contain a JSON object")

    aliases = {
        "DB_HOST": ("host", "DB_HOST"),
        "DB_PORT": ("port", "DB_PORT"),
        "DB_NAME": ("dbname", "DB_NAME"),
        "DB_USER": ("user", "DB_USER"),
        "DB_PASSWORD": ("password", "DB_PASSWORD"),
    }

    normalized: dict[str, str] = {}
    for key, candidates in aliases.items():
        for candidate in candidates:
            value = data.get(candidate)
            if value not in (None, ""):
                normalized[key] = str(value)
                break

    return normalized


def get_connection(config_values: dict[str, str] | None = None):
    merged = dict(os.environ)
    if config_values:
        merged.update(config_values)

    required = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    missing = [name for name in required if not merged.get(name)]
    if missing:
        raise RuntimeError(
            "Missing PostgreSQL settings: " + ", ".join(missing)
            + "\nProvide them in the config file or as environment variables."
        )

    return psycopg.connect(
        host=merged.get("DB_HOST", "localhost"),
        port=merged.get("DB_PORT", "5432"),
        dbname=merged.get("DB_NAME"),
        user=merged.get("DB_USER"),
        password=merged.get("DB_PASSWORD"),
    )


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_file).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()

    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}", file=sys.stderr)
        return 2

    try:
        columns, rows = read_csv_rows(csv_path, args.delimiter, args.encoding, args.skip_rows)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to read CSV: {exc}", file=sys.stderr)
        return 2

    config_values: dict[str, str] = {}
    if not args.dry_run:
        try:
            config_values = load_db_config(config_path)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to read database config: {exc}", file=sys.stderr)
            return 2

    if args.dry_run:
        print(f"Dry run: would load {len(rows)} rows from {csv_path} into {args.schema}.{args.table}")
        print("Columns:", ", ".join(columns))
        if config_path.exists():
            print(f"Using database config from {config_path}")
        return 0

    try:
        with get_connection(config_values) as conn:
            with conn.cursor() as cur:
                if args.create_table:
                    inferred_types = {column: infer_sql_type([row.get(column, "") for row in rows]) for column in columns}
                    create_sql = build_create_table_sql(args.schema, args.table, columns, inferred_types)
                    cur.execute(create_sql)

                table_ref = f"{quote_ident(args.schema)}.{quote_ident(args.table)}"
                column_sql = ", ".join(quote_ident(column) for column in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                insert_sql = f"INSERT INTO {table_ref} ({column_sql}) VALUES ({placeholders})"

                values = [tuple(row.get(column, "") for column in columns) for row in rows]
                if values:
                    cur.executemany(insert_sql, values)
                conn.commit()
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to load data: {exc}", file=sys.stderr)
        return 1

    print(f"Loaded {len(rows)} rows into {args.schema}.{args.table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
