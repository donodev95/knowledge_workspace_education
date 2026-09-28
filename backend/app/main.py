from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import Database
def create_app(settings_override: Optional[Settings] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = settings_override or get_settings()
        configure_logging(settings.log_level)
        app.state.settings = settings
        app.state.database = Database(settings.database_url)
        try:
            # async with create_checkpointer(settings) as checkpointer:
            #     app.state.checkpointer = checkpointer
                yield
        finally:
            await app.state.database.close()
    app = FastAPI(title="My FastAPI Application")
    
    @app.get("/")
    async def read_root():
        return {"message": "Welcome to My FastAPI Application!"}

    return app

app = create_app()