"""
FixMyHyd FastAPI Application
Main entry point for the web service
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from fixmyhyd.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    print("🚀 Starting FixMyHyd FastAPI Server...")
    try:
        from fixmyhyd.database import init_db
        init_db()
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down FixMyHyd FastAPI Server...")
    try:
        from fixmyhyd.database import close_db
        close_db()
        print("✅ Database connections closed")
    except Exception as e:
        print(f"⚠️ Database shutdown warning: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="FixMyHyd API",
        description="Civic complaint reporting system for Hyderabad",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    try:
        from fixmyhyd.api.routes import api_router
        app.include_router(api_router, prefix="/api")
    except ImportError as e:
        print(f"⚠️ API router import warning: {e}")
    
    try:
        from fixmyhyd.web.routes import web_router
        app.include_router(web_router)
    except ImportError as e:
        print(f"⚠️ Web router import warning: {e}")

    # Static files
    try:
        app.mount("/static", StaticFiles(directory="static"), name="static")
    except Exception as e:
        print(f"⚠️ Static files mount warning: {e}")

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "1.0.0"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="info"
    )
