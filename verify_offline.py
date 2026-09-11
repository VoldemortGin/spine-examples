"""Verify the pinned release environment and run the example without Python networking."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys


def deny_network(event: str, args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.sendto", "socket.getaddrinfo"}:
        raise RuntimeError(f"offline verification blocked {event}")


def main() -> None:
    sys.addaudithook(deny_network)
    root = Path(__file__).resolve().parent
    env = Path(sys.prefix).resolve()
    if sys.version_info[:2] != (3, 12) or env != root / ".venv":
        raise RuntimeError("run with this repository's .venv/bin/python (Python 3.12)")
    for dist_name, module_name, expected in [
        ("pdfspine", "pdfspine", "0.8.0"),
        ("corespine", "corespine", "0.5.1"),
        ("spineagent", "spineagent", "0.3.1"),
        ("rag-spine", "ragspine", "0.13.0"),
    ]:
        dist = importlib.metadata.distribution(dist_name)
        if dist.version != expected:
            raise RuntimeError(f"{dist_name}: expected {expected}, got {dist.version}")
        direct_url = json.loads(dist.read_text("direct_url.json") or "{}")
        if direct_url:
            raise RuntimeError(
                f"{dist_name}: expected an index release, not a direct/editable install"
            )
        module = importlib.import_module(module_name)
        if not Path(module.__file__).resolve().is_relative_to(env):
            raise RuntimeError(
                f"{module_name} came from outside the isolated environment"
            )
        print(f"RELEASE {dist_name}=={expected}: isolated index install")
    runpy.run_path(str(root / "spine_family_e2e.py"), run_name="__main__")
    print("OFFLINE RELEASE VERIFICATION OK")


if __name__ == "__main__":
    main()
