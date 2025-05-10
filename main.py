from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
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
from datetime import datetime, timedelta
import re
from fastapi.responses import JSONResponse
from fastapi import Cookie
from typing import Optional, List
from starlette.middleware.sessions import SessionMiddleware
import uuid
from fastapi import Body

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

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    surname = Column(String, nullable=True)
    requests = relationship("EmergencyRequest", back_populates="user")

class RequestType(Base):
    __tablename__ = "request_types"
    type_code = Column(String, primary_key=True)
    type_name = Column(String, nullable=False)
    subtypes = relationship("RequestSubType", back_populates="type")

class RequestSubType(Base):
    __tablename__ = "request_subtypes"
    subtype_code = Column(String, primary_key=True)
    subtype_name = Column(String, nullable=False)
    type_code = Column(String, ForeignKey("request_types.type_code"), nullable=False)
    type = relationship("RequestType", back_populates="subtypes")

class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"
    request_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)  # Encrypted
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    type_code = Column(String, ForeignKey("request_types.type_code"), nullable=True)
    subtype_code = Column(String, ForeignKey("request_subtypes.subtype_code"), nullable=True)
    user = relationship("User", back_populates="requests")

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
async def submit(request: Request,
    type_code: str = Form(...),
    subtype_code: str = Form(None),
    details: str = Form(None),
    latitude: float = Form(...),
    longitude: float = Form(...)):
    phone = request.session.get("phone")
    user_id = request.session.get("user_id")
    if not phone or not user_id:
        return JSONResponse({"success": False, "message": "Not authenticated."}, status_code=401)
    # Find user and get name
    async with SessionLocal() as session:
        result = await session.execute(User.__table__.select().where(User.user_id == user_id))
        user = result.fetchone()
        if not user or not user.name:
            return JSONResponse({"success": False, "message": "Profile incomplete."}, status_code=400)
        # Rate limit: 3 requests/hour except for 'MEDICAL'
        if type_code != "MEDICAL":
            now = datetime.utcnow()
            one_hour_ago = now - timedelta(hours=1)
            count_result = await session.execute(
                EmergencyRequest.__table__.select()
                .where(EmergencyRequest.user_id == user_id)
                .where(EmergencyRequest.timestamp >= one_hour_ago)
            )
            recent_requests = count_result.fetchall()
            if len(recent_requests) >= 3:
                return JSONResponse({"success": False, "message": "Request limit reached: Only 3 requests allowed per hour."}, status_code=429)
        encrypted_name = fernet.encrypt(user.name.encode()).decode()
        # For Call helpline, log minimal entry
        if type_code == "HELPLINE":
            emergency = EmergencyRequest(user_id=user_id, name=encrypted_name, latitude=latitude, longitude=longitude, type_code=type_code, subtype_code=None, details=None)
            session.add(emergency)
            await session.commit()
            return JSONResponse({"success": True, "message": "Your request to call the helpline has been logged."})
        # For Find medical services
        if type_code == "MEDICAL":
            emergency = EmergencyRequest(user_id=user_id, name=encrypted_name, latitude=latitude, longitude=longitude, type_code=type_code, subtype_code=None, details=None)
            session.add(emergency)
            await session.commit()
            return JSONResponse({"success": True, "message": "We are connecting you to the nearest medical services. (This is a mock confirmation.)"})
        # For Report attack or Report injury/casualty
        emergency = EmergencyRequest(
            user_id=user_id,
            name=encrypted_name,
            latitude=latitude,
            longitude=longitude,
            type_code=type_code,
            subtype_code=subtype_code,
            details=details
        )
        session.add(emergency)
        await session.commit()
        return JSONResponse({"success": True, "message": "Your request has been received."})

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
    check_rate_limit(request.client.host)
    check_ip_whitelist(request)
    async with SessionLocal() as session:
        result = await session.execute(
            EmergencyRequest.__table__.select().order_by(EmergencyRequest.timestamp.desc())
        )
        requests = result.fetchall()
        decrypted_requests = []
        # Mapping dicts for display
        TYPE_CODES = {
            "ATTACK": "Report attack",
            "INJURY": "Report injury/casualty",
            "MEDICAL": "Find medical services",
            "HELPLINE": "Call helpline"
        }
        SUBTYPE_CODES = {
            "BULLETS": "Bullets",
            "DRONES": "Enemy drones",
            "ARTILLERY": "Heavy artillery / Bomblasts / Missiles",
            "LIFE_THREAT": "Life threatening injury",
            "DEATH": "Death",
            "MINOR": "Minor injuries"
        }
        for row in requests:
            decrypted_name = fernet.decrypt(row.name.encode()).decode()
            formatted_ts = row.timestamp.strftime('%d %b %Y, %I:%M %p') if row.timestamp else ''
            decrypted_requests.append({
                "id": row.request_id,
                "name": decrypted_name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "type_code": row.type_code,
                "type_name": TYPE_CODES.get(row.type_code, row.type_code),
                "subtype_code": row.subtype_code,
                "subtype_name": SUBTYPE_CODES.get(row.subtype_code, row.subtype_code) if row.subtype_code else None,
                "details": row.details,
                "timestamp": formatted_ts
            })
    maptiler_key = os.environ.get("MAPTILER_API_KEY", "")
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "requests": decrypted_requests, "maptiler_key": maptiler_key}
    )

def is_valid_indian_mobile(number: str) -> bool:
    return re.fullmatch(r"[6-9]\d{9}", number) is not None

@app.post("/login")
async def login(request: Request, phone: str = Form(...), name: str = Form(None), surname: str = Form(None)):
    if not is_valid_indian_mobile(phone):
        return JSONResponse({"success": False, "message": "Invalid Indian mobile number."}, status_code=400)
    # Find or create user
    async with SessionLocal() as session:
        result = await session.execute(User.__table__.select().where(User.phone == phone))
        user = result.fetchone()
        if user:
            user_id = user.user_id
            # If name is provided and not set, update profile
            if name and (not user.name or user.name != name or (surname and user.surname != surname)):
                await session.execute(User.__table__.update().where(User.user_id == user_id).values(name=name, surname=surname))
                await session.commit()
        else:
            if not name:
                return JSONResponse({"success": False, "message": "Name is required for new users."}, status_code=400)
            new_user = User(phone=phone, name=name, surname=surname)
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            user_id = new_user.user_id
    request.session["phone"] = phone
    request.session["user_id"] = user_id
    return JSONResponse({"success": True, "message": "Authenticated."})

@app.post("/logout")
async def logout(request: Request):
    request.session.pop("phone", None)
    return JSONResponse({"success": True, "message": "Logged out."})

@app.get("/auth-status")
async def auth_status(request: Request):
    phone = request.session.get("phone")
    user_id = request.session.get("user_id")
    name = None
    surname = None
    if user_id:
        async with SessionLocal() as session:
            result = await session.execute(User.__table__.select().where(User.user_id == user_id))
            user = result.fetchone()
            if user:
                name = user.name
                surname = user.surname
    return JSONResponse({"authenticated": bool(phone), "phone": phone, "name": name, "surname": surname})

@app.get("/admin/api/requests")
async def api_requests(
    type_code: str = Query(None),
    subtype_code: str = Query(None),
    start: str = Query(None),
    end: str = Query(None)
):
    import logging
    def parse_dt(val):
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%dT%H:%M")
        except Exception as e:
            logging.warning(f"Invalid date filter value: {val} ({e})")
            return None
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    logging.info(f"/admin/api/requests filters: type_code={type_code}, subtype_code={subtype_code}, start={start}, end={end}, start_dt={start_dt}, end_dt={end_dt}")
    async with SessionLocal() as session:
        q = EmergencyRequest.__table__.select()
        if type_code:
            q = q.where(EmergencyRequest.type_code == type_code)
        if subtype_code:
            q = q.where(EmergencyRequest.subtype_code == subtype_code)
        if start_dt:
            q = q.where(EmergencyRequest.timestamp >= start_dt)
        if end_dt:
            q = q.where(EmergencyRequest.timestamp <= end_dt)
        q = q.order_by(EmergencyRequest.timestamp.desc())
        result = await session.execute(q)
        requests = result.fetchall()
        TYPE_CODES = {
            "ATTACK": "Report attack",
            "INJURY": "Report injury/casualty",
            "MEDICAL": "Find medical services",
            "HELPLINE": "Call helpline"
        }
        SUBTYPE_CODES = {
            "BULLETS": "Bullets",
            "DRONES": "Enemy drones",
            "ARTILLERY": "Heavy artillery / Bomblasts / Missiles",
            "LIFE_THREAT": "Life threatening injury",
            "DEATH": "Death",
            "MINOR": "Minor injuries"
        }
        data = []
        for row in requests:
            data.append({
                "request_id": row.request_id,
                "user_id": row.user_id,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "type_code": row.type_code,
                "type_name": TYPE_CODES.get(row.type_code, row.type_code),
                "subtype_code": row.subtype_code,
                "subtype_name": SUBTYPE_CODES.get(row.subtype_code, row.subtype_code) if row.subtype_code else None,
                "details": row.details,
                "timestamp": row.timestamp.strftime('%d %b %Y, %I:%M %p') if row.timestamp else ''
            })
    return JSONResponse(data)

@app.get("/admin/api/users")
async def api_users():
    async with SessionLocal() as session:
        result = await session.execute(User.__table__.select())
        users = result.fetchall()
        data = []
        for row in users:
            data.append({
                "user_id": row.user_id,
                "phone": row.phone,
                "name": row.name
            })
    return JSONResponse(data)

@app.post("/profile")
async def update_profile(request: Request, data: dict = Body(...)):
    phone = request.session.get("phone")
    user_id = request.session.get("user_id")
    if not phone or not user_id:
        return JSONResponse({"success": False, "message": "Not authenticated."}, status_code=401)
    name = data.get("name", "").strip()
    surname = data.get("surname", "").strip() or None
    if not name:
        return JSONResponse({"success": False, "message": "Name is required."}, status_code=400)
    async with SessionLocal() as session:
        result = await session.execute(User.__table__.select().where(User.user_id == user_id))
        user = result.fetchone()
        if not user:
            return JSONResponse({"success": False, "message": "User not found."}, status_code=404)
        await session.execute(User.__table__.update().where(User.user_id == user_id).values(name=name, surname=surname))
        await session.commit()
    return JSONResponse({"success": True, "message": "Profile updated."})

@app.get("/admin/api/types")
async def api_types():
    async with SessionLocal() as session:
        result = await session.execute(RequestType.__table__.select())
        types = result.fetchall()
        data = []
        for t in types:
            sub_result = await session.execute(RequestSubType.__table__.select().where(RequestSubType.type_code == t.type_code))
            subtypes = sub_result.fetchall()
            data.append({
                "type_code": t.type_code,
                "type_name": t.type_name,
                "subtypes": [
                    {"subtype_code": s.subtype_code, "subtype_name": s.subtype_name} for s in subtypes
                ]
            })
    return JSONResponse(data) 