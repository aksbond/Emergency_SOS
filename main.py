from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime
import uvicorn
import os
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED
from fastapi import Depends
import secrets
from dotenv import load_dotenv
import logging
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi import status
from starlette.requests import Request as StarletteRequest
import time
from datetime import datetime
import re
from fastapi.responses import JSONResponse
from fastapi import Cookie
from typing import Optional
from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# Load environment variables from .env file
load_dotenv()

# Set up logging for security events
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# --- Advanced Security Features ---

# 1. Enforce HTTPS in production (uncomment in production)
# app.add_middleware(HTTPSRedirectMiddleware)

# 2. Store database outside web root
DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", "../data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "emergency.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=True)

# 3. Encrypt sensitive fields (name) using Fernet
FERNET_KEY = os.environ.get("FERNET_KEY")
if not FERNET_KEY:
    FERNET_KEY = Fernet.generate_key().decode()
    print(f"[SECURITY] Generated new FERNET_KEY: {FERNET_KEY}")
fernet = Fernet(FERNET_KEY.encode())

# 4. Rate limiting for admin route
RATE_LIMIT = int(os.environ.get("ADMIN_RATE_LIMIT", 5))  # requests
RATE_PERIOD = int(os.environ.get("ADMIN_RATE_PERIOD", 60))  # seconds
rate_limit_cache = {}

def check_rate_limit(ip: str):
    now = time.time()
    window = rate_limit_cache.get(ip, [])
    window = [t for t in window if now - t < RATE_PERIOD]
    if len(window) >= RATE_LIMIT:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Try again later.")
    window.append(now)
    rate_limit_cache[ip] = window

# 5. IP Whitelisting for admin route
ADMIN_ALLOWED_IPS = os.environ.get("ADMIN_ALLOWED_IPS", "127.0.0.1").split(",")

def check_ip_whitelist(request: StarletteRequest):
    client_ip = request.client.host
    if client_ip not in ADMIN_ALLOWED_IPS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied from this IP.")

# --- End Advanced Security Features ---

# Database setup
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Encrypted
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    request_type = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

# Create DB tables
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Static and templates
if not os.path.exists("static"):
    os.mkdir("static")
if not os.path.exists("templates"):
    os.mkdir("templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY", "supersecret"))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    phone = request.session.get("phone")
    return templates.TemplateResponse("index.html", {"request": request, "authenticated": bool(phone), "phone": phone})

@app.post("/submit", response_class=HTMLResponse)
async def submit(request: Request, name: str = Form(...), latitude: float = Form(...), longitude: float = Form(...), request_type: str = Form(...)):
    phone = request.session.get("phone")
    if not phone:
        return RedirectResponse("/", status_code=303)
    encrypted_name = fernet.encrypt(name.encode()).decode()
    async with SessionLocal() as session:
        emergency = EmergencyRequest(name=encrypted_name, latitude=latitude, longitude=longitude, request_type=request_type)
        session.add(emergency)
        await session.commit()
    return RedirectResponse("/", status_code=303)

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        logging.warning(f"Failed admin login attempt: username={credentials.username}")
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True

@app.get("/supersecretadmin", response_class=HTMLResponse)
async def admin_view(request: Request, authorized: bool = Depends(verify_admin)):
    # Advanced security: rate limiting and IP whitelist
    check_rate_limit(request.client.host)
    check_ip_whitelist(request)
    async with SessionLocal() as session:
        result = await session.execute(
            EmergencyRequest.__table__.select().order_by(EmergencyRequest.id.desc())
        )
        requests = result.fetchall()
        # Decrypt names for display
        decrypted_requests = []
        for row in requests:
            decrypted_name = fernet.decrypt(row.name.encode()).decode()
            decrypted_requests.append({
                "id": row.id,
                "name": decrypted_name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "request_type": row.request_type
            })
    maptiler_key = os.environ.get("MAPTILER_API_KEY", "")
    print("-------maptiler_key-------", maptiler_key)
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "requests": decrypted_requests, "maptiler_key": maptiler_key}
    )

def is_valid_indian_mobile(number: str) -> bool:
    return re.fullmatch(r"[6-9]\d{9}", number) is not None

@app.post("/login")
async def login(request: Request, phone: str = Form(...)):
    if not is_valid_indian_mobile(phone):
        return JSONResponse({"success": False, "message": "Invalid Indian mobile number."}, status_code=400)
    request.session["phone"] = phone
    return JSONResponse({"success": True, "message": "Authenticated."})

@app.post("/logout")
async def logout(request: Request):
    request.session.pop("phone", None)
    return JSONResponse({"success": True, "message": "Logged out."})

@app.get("/auth-status")
async def auth_status(request: Request):
    phone = request.session.get("phone")
    return JSONResponse({"authenticated": bool(phone), "phone": phone}) 