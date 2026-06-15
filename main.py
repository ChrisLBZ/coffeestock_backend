from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import models
from database import engine, get_db
import jwt
from datetime import datetime, timedelta, timezone
import hashlib
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from mangum import Mangum  # <-- NOVO: Adaptador Serverless para a Vercel

SECRET_KEY = os.getenv("SECRET_KEY", "chave-temporaria-para-testes-locais")
ALGORITHM = "HS256"

def gerar_senha_hash(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()    

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoffeeStock API")

# NOVO: Instanciação do manipulador que a Vercel chamará obrigatoriamente
handler = Mangum(app)

security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCHEMAS PYDANTIC ---
class UserLogin(BaseModel):
    username: str
    senha: str

class UserCreate(BaseModel):
    username: str
    senha: str
    cargo: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    cargo: str
    username: str

class PedidoCreate(BaseModel):
    cliente: str
    cafe_id: int
    tamanho_pacote: str
    quantidade: int
    tipo_cafe: str
    tipo_moagem: Optional[str] = None
    tipo_envio: str
    endereco: Optional[str] = None
    pago: bool

class PedidoStatusUpdate(BaseModel):
    status: str

class PedidoPagoUpdate(BaseModel):
    pago: bool

class EstoqueUpdate(BaseModel):
    nome: str
    quantidade_kg: float
    preco_250g: float
    preco_500g: float
    preco_1kg: float

# --- ROTAS DE AUTENTICAÇÃO ---
@app.post("/login", response_model=TokenResponse)
def login(dados: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.username == dados.username).first()
    if not user or user.senha_hash != gerar_senha_hash(dados.senha):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    
    tempo_expiracao = datetime.now(timezone.utc) + timedelta(hours=8)
    payload = {
        "sub": user.username,
        "cargo": user.cargo,
        "exp": tempo_expiracao
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "cargo": user.cargo,
        "username": user.username
    }

# --- ROTAS DE PEDIDOS ---
@app.get("/pedidos")
def listar_pedidos(
    skip: int = 0, 
    limit: int = 10, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
        
    total = db.query(models.Pedido).count()
    pedidos = db.query(models.Pedido).order_by(models.Pedido.id.desc()).offset(skip).limit(limit).all()
    
    return {"total": total, "pedidos": pedidos}

@app.post("/pedidos")
def criar_pedido(
    pedido: PedidoCreate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    cafe = db.query(models.EstoqueCafe).filter(models.EstoqueCafe.id == pedido.cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Tipo de café não encontrado no estoque")

    peso_por_unidade = 0.25 if pedido.tamanho_pacote == "250g" else (0.50 if pedido.tamanho_pacote == "500g" else 1.0)
    peso_total_pedido = peso_por_unidade * pedido.quantidade

    if cafe.quantidade_kg < peso_total_pedido:
        raise HTTPException(status_code=400, detail=f"Estoque insuficiente. Disponível: {cafe.quantidade_kg:.2f} kg")

    preco_unitario = cafe.preco_250g if pedido.tamanho_pacote == "250g" else (cafe.preco_500g if pedido.tamanho_pacote == "500g" else cafe.preco_1kg)
    valor_total_calculado = preco_unitario * pedido.quantidade

    cafe.quantidade_kg -= peso_total_pedido

    novo_pedido = models.Pedido(
        cliente=pedido.cliente,
        cafe_id=pedido.cafe_id,
        tamanho_pacote=pedido.tamanho_pacote,
        quantidade=pedido.quantidade,
        tipo_cafe=pedido.tipo_cafe,
        tipo_moagem=pedido.tipo_moagem,
        tipo_envio=pedido.tipo_envio,
        endereco=pedido.endereco,
        pago=pedido.pago,
        valor_total=valor_total_calculado,
        status="aguardando",
        data_pedido=datetime.now(timezone.utc)
    )

    db.add(novo_pedido)
    db.commit()
    db.refresh(novo_pedido)
    return novo_pedido

@app.put("/pedidos/{pedido_id}/status")
def atualizar_status_pedido(
    pedido_id: int, 
    dados: PedidoStatusUpdate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    pedido.status = dados.status
    db.commit()
    return {"detail": "Status updated"}

@app.put("/pedidos/{pedido_id}/pagamento")
def atualizar_pagamento_pedido(
    pedido_id: int, 
    dados: PedidoPagoUpdate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    pedido.pago = dados.pago
    db.commit()
    return {"detail": "Payment status updated"}

@app.delete("/pedidos/{pedido_id}")
def excluir_pedido(
    pedido_id: int, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("cargo") != "admin":
            raise HTTPException(status_code=403, detail="Apenas administradores podem excluir pedidos")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    db.delete(pedido)
    db.commit()
    return {"detail": "Pedido removido com sucesso"}

# --- ROTAS DE GERENCIAMENTO DE ESTOQUE ---
@app.get("/estoque")
def listar_estoque(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return db.query(models.EstoqueCafe).all()

@app.post("/estoque")
def cadastrar_novo_cafe(
    dados: EstoqueUpdate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("cargo") != "admin":
            raise HTTPException(status_code=403, detail="Apenas administradores podem cadastrar novos cafés")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    novo_cafe = models.EstoqueCafe(
        nome=dados.nome,
        quantidade_kg=dados.quantidade_kg,
        preco_250g=dados.preco_250g,
        preco_500g=dados.preco_500g,
        preco_1kg=dados.preco_1kg
    )
    db.add(novo_cafe)
    db.commit()
    db.refresh(novo_cafe)
    return novo_cafe

@app.put("/estoque/{cafe_id}")
def atualizar_estoque(
    cafe_id: int, 
    dados: EstoqueUpdate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("cargo") != "admin":
            raise HTTPException(status_code=403, detail="Apenas administradores podem modificar o estoque")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    cafe = db.query(models.EstoqueCafe).filter(models.EstoqueCafe.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Café não encontrado")

    cafe.nome = dados.nome
    cafe.quantidade_kg = dados.quantidade_kg
    cafe.preco_250g = dados.preco_250g
    cafe.preco_500g = dados.preco_500g
    cafe.preco_1kg = dados.preco_1kg

    db.commit()
    return {"detail": "Estoque atualizado com sucesso"}

# --- GERENCIAMENTO DE USUÁRIOS ---
@app.post("/usuarios/cadastrar")
def cadastrar_usuario(
    dados: UserCreate, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("cargo") != "admin":
            raise HTTPException(status_code=403, detail="Apenas administradores podem cadastrar usuários")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    existente = db.query(models.Usuario).filter(models.Usuario.username == dados.username).first()
    if existente:
        raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso")

    novo_user = models.Usuario(
        username=dados.username,
        senha_hash=gerar_senha_hash(dados.senha),
        cargo=dados.cargo
    )
    db.add(novo_user)
    db.commit()
    return {"detail": f"Usuário {dados.username} cadastrado com sucesso!"}  

@app.delete("/usuarios/{username}")
def excluir_usuario(
    username: str, 
    credentials: HTTPAuthorizationCredentials = Depends(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        admin_atual = payload.get("sub")
        if payload.get("cargo") != "admin":
            raise HTTPException(status_code=403, detail="Apenas administradores podem excluir usuários")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
        
    if username == admin_atual:
        raise HTTPException(status_code=400, detail="Você não pode excluir a si mesmo")

    user = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    db.delete(user)
    db.commit()
    return {"detail": f"Usuário {username} removido com sucesso"}