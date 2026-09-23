"""
``python -m mock_server`` — sobe a fonte fictícia em http://localhost:8000.

Projeto : github.com/jlfig13/ocupa-salas  (estudo / portfólio)
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("MOCK_HOST", "127.0.0.1")
    port = int(os.environ.get("MOCK_PORT", "8000"))
    uvicorn.run("mock_server.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
