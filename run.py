#!/usr/bin/env python3
"""
Security Camera Dashboard - Entry Point

Run with: python run.py
Or: uvicorn backend.main:app --reload
"""

import uvicorn

from backend.config import settings


def main():
    print("=" * 50)
    print("Security Camera Dashboard")
    print("=" * 50)
    print(f"Starting server at http://{settings.host}:{settings.port}")
    print(f"Data directory: {settings.data_dir}")
    print("=" * 50)

    uvicorn.run(
        "backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
