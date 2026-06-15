import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

# Tenta ler a URL do Supabase. Se não houver (testes locais), usa o SQLite de fallback.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cafe.db")

# O SQLAlchemy exige que o prefixo do driver seja 'postgresql://' e não 'postgres://'
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)

# Configuração adaptada para o ambiente do Supabase
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=NullPool,  # Evita estouro de conexões no plano gratuito
        client_encoding='utf8'
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()