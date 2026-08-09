import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bot_data.db")

# Fix Heroku/Railway legacy postgres:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"

    chat_id = Column(Integer, primary_key=True, index=True)
    role = Column(String(100), nullable=True)
    watchlist = Column(Text, nullable=True)
    onboarding_step = Column(Integer, default=0)

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, index=True)
    user_query = Column(Text)
    bot_response = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_user_profile_db(chat_id: int):
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.chat_id == chat_id).first()
    if not user:
        user = UserProfile(chat_id=chat_id, onboarding_step=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    
    role = user.role
    watchlist = [item.strip() for item in user.watchlist.split(",")] if user.watchlist else []
    step = user.onboarding_step
    db.close()
    return {"step": step, "role": role, "watchlist": watchlist}

def update_user_profile_db(chat_id: int, step: int = None, role: str = None, watchlist: list = None):
    db = SessionLocal()
    user = db.query(UserProfile).filter(UserProfile.chat_id == chat_id).first()
    if not user:
        user = UserProfile(chat_id=chat_id)
        db.add(user)

    if step is not None:
        user.onboarding_step = step
    if role is not None:
        user.role = role
    if watchlist is not None:
        user.watchlist = ",".join(watchlist)

    db.commit()
    db.close()

def log_chat_history(chat_id: int, user_query: str, bot_response: str):
    db = SessionLocal()
    history = ChatHistory(chat_id=chat_id, user_query=user_query, bot_response=bot_response)
    db.add(history)
    db.commit()
    db.close()
