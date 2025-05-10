import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime
import asyncio
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

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

class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    request_type = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

# Dummy data: (name, latitude, longitude, request_type, timestamp)
base_date = datetime(2025, 5, 7, 8, 0, 0)
dummy_data = [
    ("Amit", 34.0837, 74.7973, "Report casualty", base_date),
    ("Priya", 32.7266, 74.8570, "Request evacuation", base_date + timedelta(hours=6)),
    ("Rahul", 31.6340, 74.8723, "Find medical services near me", base_date + timedelta(hours=12)),
    ("Sneha", 30.9000, 74.6000, "Report casualty", base_date + timedelta(hours=18)),
    ("Vikram", 29.9000, 73.9000, "Request evacuation", base_date + timedelta(days=1)),
    ("Anjali", 28.4000, 70.3000, "Find medical services near me", base_date + timedelta(days=1, hours=6)),
    ("Ravi", 24.8807, 71.7456, "Report casualty", base_date + timedelta(days=1, hours=12)),
    ("Meera", 23.7000, 68.9000, "Request evacuation", base_date + timedelta(days=1, hours=18)),
    ("Arjun", 25.0000, 71.0000, "Find medical services near me", base_date + timedelta(days=2)),
    ("Kiran", 32.3833, 75.5167, "Report casualty", base_date + timedelta(days=2, hours=6)),
    ("Deepa", 33.7782, 76.5762, "Request evacuation", base_date + timedelta(days=2, hours=12)),
    ("Suresh", 31.0200, 75.4000, "Report casualty", base_date + timedelta(days=3)),
]

async def insert_dummy():
    async with SessionLocal() as session:
        for name, lat, lon, req_type, ts in dummy_data:
            encrypted_name = fernet.encrypt(name.encode()).decode()
            req = EmergencyRequest(name=encrypted_name, latitude=lat, longitude=lon, request_type=req_type, timestamp=ts)
            session.add(req)
        await session.commit()
    print("Inserted dummy data.")

if __name__ == "__main__":
    asyncio.run(insert_dummy()) 