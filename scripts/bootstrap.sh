#!/usr/bin/env bash
set -e

python3 -m pip install -e ".[dev]"
pre-commit install