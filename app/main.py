from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import setup_logging, get_logger
from app.database.seed import seed_listings_if_empty
from app.database.session import SessionLocal
from app.routes.agents import router as agents_router
from app.routes.chat import router as chat_router
from app.routes.comparison import router as comparison_router
from app.routes.email_notifications import router as email_router
from app.routes.ingestion import router as ingestion_router
from app.routes.lifestyle import router as lifestyle_router
from app.routes.listings import router as listings_router
from app.routes.price_analysis import router as price_analysis_router
from app.routes.profile import router as profile_router
from app.routes.qa import router as qa_router
from app.routes.recommendation import router as recommendation_router
from app.routes.saved import router as saved_router

setup_logging(settings.log_level)
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, version=settings.app_version)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=settings.cors_allowed_credentials,
    allow_methods=settings.cors_allowed_methods,
    allow_headers=settings.cors_allowed_headers,
)


def _can_seed_on_startup() -> bool:
    return settings.seed_on_startup and settings.environment.lower() in {"local", "development", "dev"}


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    logger.warning(
        "Application error occurred",
        extra={
            "code": exc.code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": str(request.url),
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(x) for x in error["loc"][1:]),
            "type": error["type"],
            "message": error["msg"],
        })

    logger.warning(
        "Validation error",
        extra={
            "errors": errors,
            "path": str(request.url),
        },
    )

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    logger.error(
        "Unhandled exception",
        extra={
            "exception": str(exc),
            "path": str(request.url),
        },
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            }
        },
    )


@app.on_event("startup")
def on_startup():
    if not _can_seed_on_startup():
        return

    db = SessionLocal()
    try:
        seed_listings_if_empty(db)
    finally:
        db.close()

    logger.info("Application started", extra={"environment": settings.environment})


app.include_router(agents_router)
app.include_router(listings_router)
app.include_router(ingestion_router)
app.include_router(profile_router)
app.include_router(lifestyle_router)
app.include_router(price_analysis_router)
app.include_router(comparison_router)
app.include_router(recommendation_router)
app.include_router(qa_router)
app.include_router(chat_router)
app.include_router(saved_router)
app.include_router(email_router)


# Template Routes
@app.get("/")
def dashboard(request: Request):
    """Render dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/analyze")
def analyze(request: Request):
    """Render analyze page"""
    return templates.TemplateResponse("analyze.html", {"request": request})


@app.get("/engines")
def engines(request: Request):
    """Render engines test page"""
    return templates.TemplateResponse("engines.html", {"request": request})


@app.get("/listings")
def listings_page(request: Request):
    """Render listings page"""
    return templates.TemplateResponse("listings_emlakjet.html", {"request": request})


@app.get("/saved")
def saved_page(request: Request):
    """Render saved listings page"""
    return templates.TemplateResponse("saved.html", {"request": request})


@app.get("/health")
def health_check():
    """API health check endpoint"""
    logger.debug("Health check called")
    return {"status": "ok", "message": "EmlakAI backend is running"}
