"""Check pinned base dependencies without loading models or environment files."""
import importlib.metadata as metadata
from pathlib import Path
import re
import sys

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([\w-]+)(?:\[[^]]+\])?==([^\s]+)", line)
    if not match:
        continue
    try:
        if metadata.version(match[1]) != match[2]:
            sys.exit(1)
    except metadata.PackageNotFoundError:
        sys.exit(1)

import fastapi
import uvicorn
import sqlalchemy
import pydantic_settings
import jose
import passlib
import bcrypt
import multipart
import httpx
