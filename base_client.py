#!/usr/bin/env python3
"""Compatibilidad y entrada CLI de AberCr."""

from abercr import (
    AbercrombieClient,
    AbercrombieClientError,
    Config,
    GraphQLError,
    HttpResponseError,
)
from abercr.cli import main

__all__ = [
    "AbercrombieClient",
    "AbercrombieClientError",
    "Config",
    "GraphQLError",
    "HttpResponseError",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
