"""Test-only entry point. Never copied into either release image."""

from app.config import Settings
from app.gateway import Gateway
from app.main import create_app


def app():
    settings = Settings.load()
    return create_app(
        settings,
        Gateway(settings.model, settings.keys, api_base="http://provider:9000"),
    )
