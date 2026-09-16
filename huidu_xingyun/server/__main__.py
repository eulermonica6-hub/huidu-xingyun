"""``python -m huidu_xingyun.server`` 启动入口。"""

from __future__ import annotations

import os

import uvicorn

from .app import app


def main() -> None:
    host = os.environ.get("HUIDU_HOST", "0.0.0.0")
    port = int(os.environ.get("HUIDU_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()