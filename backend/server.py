"""Thin HTTP entry point. Run: uvicorn backend.server:app"""
from backend.agent.server.app import create_app

app = create_app()
