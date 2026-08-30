#!/usr/bin/env python3
"""Bootstrap-safe dev storage attestation; independent of the deployed app revision."""
from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        tokens = list(lexer)
        values[key.strip().upper()] = " ".join(tokens)
    return values


def lexical(path: Path, backend: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = backend / expanded
    return Path(os.path.abspath(expanded))


def has_symlink_component(path: Path, boundary: Path) -> bool:
    absolute = path.expanduser().absolute()
    floor = boundary.expanduser().absolute().parent
    return any(
        component.is_symlink()
        for component in (absolute, *absolute.parents)
        if component.is_relative_to(floor)
    )


def isolated(path: Path, backend: Path) -> bool:
    backend = lexical(backend, Path.cwd())
    expected = backend / "data"
    candidate = lexical(path, backend)
    if any(has_symlink_component(item, backend.parent) for item in (backend, expected, candidate)):
        return False
    return candidate.is_relative_to(expected) and candidate.resolve().is_relative_to(expected.resolve())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        values = read_env(args.env_file)
        database_url = values.get("DATABASE_URL", "sqlite:///data/prep.db")
        prefix = "sqlite:///"
        database = Path(database_url[len(prefix):]) if database_url.startswith(prefix) else None
        books = Path(values.get("BOOK_STORAGE_DIR", "data/books"))
        if database is None or not str(database) or str(database) == ":memory:":
            raise ValueError("unsafe database")
        if not isolated(database, args.backend) or not isolated(books, args.backend):
            raise ValueError("unsafe storage")
    except (OSError, ValueError):
        print("development storage isolation check failed", file=__import__("sys").stderr)
        return 1
    print("development storage isolation attested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
