import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Table, MetaData, select, update
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from datetime import datetime
import asyncio

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
metadata = MetaData()

# --- New Normalized Tables ---
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

# --- Existing Tables (for migration) ---
class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    surname = Column(String, nullable=True)

class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"
    request_id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    request_type = Column(String, nullable=True)  # old
    sub_type = Column(String, nullable=True)      # old
    details = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    # new columns
    type_code = Column(String, ForeignKey("request_types.type_code"), nullable=True)
    subtype_code = Column(String, ForeignKey("request_subtypes.subtype_code"), nullable=True)

# --- Code name mappings ---
TYPE_CODES = {
    "Report attack": "ATTACK",
    "Report injury/casualty": "INJURY",
    "Find medical services": "MEDICAL",
    "Call helpline": "HELPLINE"
}
SUBTYPE_CODES = {
    "Bullets": "BULLETS",
    "Enemy drones": "DRONES",
    "Heavy artillery / Bomblasts / Missiles": "ARTILLERY",
    "Life threatening injury": "LIFE_THREAT",
    "Death": "DEATH",
    "Minor injuries": "MINOR"
}
# Reverse for display
TYPE_NAMES = {v: k for k, v in TYPE_CODES.items()}
SUBTYPE_NAMES = {v: k for k, v in SUBTYPE_CODES.items()}

# --- Migration logic ---
async def migrate():
    async with engine.begin() as conn:
        # 1. Create new tables if not exist
        await conn.run_sync(Base.metadata.create_all)
        # 2. Insert request types
        async with SessionLocal() as session:
            for code, name in TYPE_NAMES.items():
                exists = await session.get(RequestType, code)
                if not exists:
                    session.add(RequestType(type_code=code, type_name=name))
            await session.commit()
            # 3. Insert subtypes
            for code, name in SUBTYPE_NAMES.items():
                # Map to type_code
                if code in ["BULLETS", "DRONES", "ARTILLERY"]:
                    type_code = "ATTACK"
                elif code in ["LIFE_THREAT", "DEATH", "MINOR"]:
                    type_code = "INJURY"
                else:
                    type_code = None
                if type_code:
                    exists = await session.get(RequestSubType, code)
                    if not exists:
                        session.add(RequestSubType(subtype_code=code, subtype_name=name, type_code=type_code))
            await session.commit()
            # 4. Add new columns to emergency_requests if not present
            await conn.execute('''
                ALTER TABLE emergency_requests ADD COLUMN type_code VARCHAR;
            ''')
            await conn.execute('''
                ALTER TABLE emergency_requests ADD COLUMN subtype_code VARCHAR;
            ''')
            # 5. Migrate data
            result = await session.execute(select(EmergencyRequest))
            requests = result.scalars().all()
            for req in requests:
                # Map old to new codes
                tcode = TYPE_CODES.get(req.request_type)
                scode = SUBTYPE_CODES.get(req.sub_type) if req.sub_type else None
                await session.execute(update(EmergencyRequest).where(EmergencyRequest.request_id == req.request_id).values(type_code=tcode, subtype_code=scode))
            await session.commit()
    print("Migration complete. Database is now normalized with code names for types and subtypes.")

if __name__ == "__main__":
    asyncio.run(migrate()) 