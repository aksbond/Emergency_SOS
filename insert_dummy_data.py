import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, select
import asyncio
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
import uuid
import random

# Load environment variables
load_dotenv()

DATA_DIR = os.path.abspath(os.environ.get("DATA_DIR", "../data"))
DB_PATH = os.path.join(DATA_DIR, "emergency.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
FERNET_KEY = os.environ.get("FERNET_KEY")
fernet = Fernet(FERNET_KEY.encode())

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# --- Normalized Tables ---
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

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    surname = Column(String, nullable=True)
    requests = relationship("EmergencyRequest", back_populates="user")

class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"
    request_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    type_code = Column(String, ForeignKey("request_types.type_code"), nullable=True)
    subtype_code = Column(String, ForeignKey("request_subtypes.subtype_code"), nullable=True)
    user = relationship("User", back_populates="requests")

# --- Code name mappings ---
TYPE_CODES = {
    "ATTACK": "Report attack",
    "INJURY": "Report injury/casualty",
    "MEDICAL": "Find medical services",
    "HELPLINE": "Call helpline"
}
SUBTYPE_CODES = {
    "BULLETS": ("Bullets", "ATTACK"),
    "DRONES": ("Enemy drones", "ATTACK"),
    "ARTILLERY": ("Heavy artillery / Bomblasts / Missiles", "ATTACK"),
    "LIFE_THREAT": ("Life threatening injury", "INJURY"),
    "DEATH": ("Death", "INJURY"),
    "MINOR": ("Minor injuries", "INJURY")
}

# Dummy users: (name, phone)
dummy_users = [
    ("Amit", "9876543210"),
    ("Priya", "9123456789"),
    ("Rahul", "9988776655"),
    ("Sneha", "9876501234"),
]

async def insert_dummy():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        # Insert request types
        for tcode, tname in TYPE_CODES.items():
            exists = await session.get(RequestType, tcode)
            if not exists:
                session.add(RequestType(type_code=tcode, type_name=tname))
        await session.commit()
        # Insert subtypes
        for scode, (sname, tcode) in SUBTYPE_CODES.items():
            exists = await session.get(RequestSubType, scode)
            if not exists:
                session.add(RequestSubType(subtype_code=scode, subtype_name=sname, type_code=tcode))
        await session.commit()
        # Create users
        user_objs = []
        for name, phone in dummy_users:
            user = User(user_id=str(uuid.uuid4()), phone=phone, name=name)
            session.add(user)
            user_objs.append(user)
        await session.commit()
        for user in user_objs:
            await session.refresh(user)
        # Insert 10,000 random requests
        all_type_codes = list(TYPE_CODES.keys())
        all_subtypes_by_type = {t: [scode for scode, (_, tcode) in SUBTYPE_CODES.items() if tcode == t] for t in TYPE_CODES}
        base_date = datetime.utcnow() - timedelta(days=90)
        for i in range(10000):
            user = random.choice(user_objs)
            type_code = random.choice(all_type_codes)
            subtypes = all_subtypes_by_type[type_code]
            subtype_code = random.choice(subtypes) if subtypes and random.random() > 0.2 else None
            lat = round(random.uniform(8.0, 37.0), 6)  # India approx
            lon = round(random.uniform(68.0, 97.0), 6)
            details = random.choice([
                "", "Severe bleeding", "Gunshot wound", "Sprained ankle", "Needs evacuation", "Minor injuries", "Unconscious", None
            ]) if type_code in ("INJURY", "ATTACK") else None
            ts = base_date + timedelta(seconds=random.randint(0, 90*24*3600))
            encrypted_name = fernet.encrypt(user.name.encode()).decode()
            req = EmergencyRequest(
                request_id=str(uuid.uuid4()),
                user_id=user.user_id,
                name=encrypted_name,
                latitude=lat,
                longitude=lon,
                type_code=type_code,
                subtype_code=subtype_code,
                details=details,
                timestamp=ts
            )
            session.add(req)
            if i % 500 == 0:
                await session.commit()
        await session.commit()
    print("Inserted dummy users, request types, subtypes, and 10,000 requests.")

if __name__ == "__main__":
    asyncio.run(insert_dummy()) 