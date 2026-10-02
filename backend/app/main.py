from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import JSONResponse
from backend.app.auth.dependencies import get_current_user

from backend.app.api import auth, documents, papers, source_item_links, threads
from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.db.session import Database

API_PREFIX = "/api/v1"
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
    application = FastAPI(
        title="Agentic RAG Knowledge Assistant",
        description="Source-grounded paper question answering API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(documents.router, prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
    application.include_router(papers.router, prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
    application.include_router(source_item_links.router, prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
    application.include_router(threads.router, prefix=API_PREFIX, dependencies=[Depends(get_current_user)])
    
    @application.get(f"{API_PREFIX}/openapi.json", include_in_schema=False, dependencies=[Depends(get_current_user)])
    async def protected_openapi():
        return JSONResponse(application.openapi())

    @application.get(f"{API_PREFIX}/docs", include_in_schema=False, dependencies=[Depends(get_current_user)])
    async def protected_docs():
        return get_swagger_ui_html(openapi_url=f"{API_PREFIX}/openapi.json", title="API documentation")

    @application.get(f"{API_PREFIX}/redoc", include_in_schema=False, dependencies=[Depends(get_current_user)])
    async def protected_redoc():
        return get_redoc_html(openapi_url=f"{API_PREFIX}/openapi.json", title="API documentation")

    @application.get("/", dependencies=[Depends(get_current_user)])
    async def read_root():
        return {"message": "Welcome to My FastAPI Application!"}

    return application

app = create_app()