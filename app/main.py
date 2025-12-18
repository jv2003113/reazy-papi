from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

from app.api.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import logging
    logging.error(f"Validation error: {exc.errors()}")
    # Also log the body if possible, but reading body inside handler might consume stream
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Welcome to Reazy API (FastAPI)"}
