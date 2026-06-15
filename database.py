import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

# 1. Lê a variável de ambiente da Vercel
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cafe.db")

# 2. TRATAMENTO INVIOLÁVEL DO DRIVER: Força o uso do pg8000 caso seja um banco Postgres
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    # Se a URL começar com postgres://, substitui pelo driver puro Python pg8000
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)
elif SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    # Se já começar com postgresql://, injeta o +pg8000 no meio
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)

# 3. Criação do Engine de acordo com o banco selecionado
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # Quando passar por aqui, o SQLAlchemy usará obrigatoriamente o pg8000
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        poolclass=NullPool,
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