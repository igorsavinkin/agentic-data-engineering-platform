"""Entry point for ``python -m services.api``."""

from __future__ import annotations

import uvicorn

from services.api.config import APISettings


def main() -> None:
    settings = APISettings.from_env()
    uvicorn.run(
        "services.api.app:create_app",
        host=settings.host,
        port=settings.port,
        factory=True,
    )


if __name__ == "__main__":
    main()
