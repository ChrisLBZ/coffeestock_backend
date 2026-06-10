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

SECRET_KEY = os.getenv("SECRET_KEY", "chave-temporaria-para-testes-locais")
ALGORITHM = "HS256"

# Função nativa e segura para gerar os hashes de senha sem limite de bytes
def gerar_senha_hash(senha: str) -> str:
    return hashlib.sha256(senha.encode('utf-8')).hexdigest()    

# Cria as tabelas no banco de dados se elas não existirem
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoffeeStock API")

security = HTTPBearer()

# Permite que o seu site HTML acesse o backend
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
    cargo: str = "operador"

class PedidoCreate(BaseModel):
    cliente: str
    cafe_id: int
    tamanho_pacote: str
    quantidade: int
    tipo_cafe: str
    tipo_moagem: Optional[str] = None
    tipo_envio: str
    endereco: Optional[str] = None
    pago: bool = False

class PagamentoUpdate(BaseModel):
    pago: bool

class StatusUpdate(BaseModel):
    status: str

class EstoqueUpdate(BaseModel):
    quantidade_kg: float
    nome: Optional[str] = None
    preco_250g: Optional[float] = None
    preco_500g: Optional[float] = None
    preco_1kg: Optional[float] = None

class CafeEstoqueCreate(BaseModel):
    nome: str
    quantidade_kg: float
    preco_250g: float = 0.0
    preco_500g: float = 0.0
    preco_1kg: float = 0.0


# --- ROTAS DE ESTOQUE ---

@app.get("/estoque")
def listar_estoque(db: Session = Depends(get_db)):
    # 1. Criação automática do Admin usando SHA-256
    try:
        if db.query(models.Usuario).count() == 0:
            admin_padrao = models.Usuario(
                username="admin",
                senha_hash=gerar_senha_hash("admin123"),
                cargo="admin"
            )
            db.add(admin_padrao)
            db.commit()
            print("🚀 Primeiro Administrador criado com sucesso! Usuário: admin | Senha: admin123")
    except Exception as e:
        db.rollback()
        print(f"⚠️ Aviso: Não foi possível verificar/criar a tabela de usuários automaticamente: {e}")

    # 2. População inicial de cafés
    if db.query(models.CafeEstoque).count() == 0:
        cafes_iniciais = [
            models.CafeEstoque(nome="Blend da Casa", quantidade_kg=50.00, preco_250g=15.00, preco_500g=28.00, preco_1kg=50.00),
            models.CafeEstoque(nome="Bourbon Amarelo", quantidade_kg=30.00, preco_250g=18.00, preco_500g=34.00, preco_1kg=60.00),
            models.CafeEstoque(nome="Espresso Intenso", quantidade_kg=25.00, preco_250g=20.00, preco_500g=38.00, preco_1kg=70.00)
        ]
        db.add_all(cafes_iniciais)
        db.commit()
        
    return db.query(models.CafeEstoque).all()

@app.post("/estoque")
def cadastrar_novo_cafe(cafe: CafeEstoqueCreate, db: Session = Depends(get_db)):
    existe = db.query(models.CafeEstoque).filter(models.CafeEstoque.nome == cafe.nome.strip()).first()
    if existe:
        raise HTTPException(status_code=400, detail="Este café já está cadastrado no estoque.")
        
    novo_cafe = models.CafeEstoque(
        nome=cafe.nome.strip(),
        quantidade_kg=round(cafe.quantidade_kg, 2),
        preco_250g=round(cafe.preco_250g, 2),
        preco_500g=round(cafe.preco_500g, 2),
        preco_1kg=round(cafe.preco_1kg, 2)
    )
    db.add(novo_cafe)
    db.commit()
    db.refresh(novo_cafe)
    return novo_cafe

@app.put("/estoque/{cafe_id}")
def modificar_estoque_ou_nome(cafe_id: int, dados: EstoqueUpdate, db: Session = Depends(get_db)):
    cafe = db.query(models.CafeEstoque).filter(models.CafeEstoque.id == cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Café não encontrado")
    
    if dados.nome and dados.nome.strip() != "":
        cafe_duplicado = db.query(models.CafeEstoque).filter(models.CafeEstoque.nome == dados.nome.strip(), models.CafeEstoque.id != cafe_id).first()
        if cafe_duplicado:
            raise HTTPException(status_code=400, detail="Já existe outro café com esse nome.")
        cafe.nome = dados.nome.strip()

    cafe.quantidade_kg = round(dados.quantidade_kg, 2)
    
    if dados.preco_250g is not None: cafe.preco_250g = round(dados.preco_250g, 2)
    if dados.preco_500g is not None: cafe.preco_500g = round(dados.preco_500g, 2)
    if dados.preco_1kg is not None: cafe.preco_1kg = round(dados.preco_1kg, 2)
    
    db.commit()
    db.refresh(cafe)
    return cafe


# --- ROTAS DE PEDIDOS ---

@app.get("/pedidos")
def listar_pedidos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    total = db.query(models.Pedido).count()
    pedidos = db.query(models.Pedido).order_by(models.Pedido.id.desc()).offset(skip).limit(limit).all()
                
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "pedidos": pedidos
    }

@app.post("/pedidos", status_code=status.HTTP_201_CREATED)
def criar_pedido(pedido: PedidoCreate, db: Session = Depends(get_db)):
    cafe = db.query(models.CafeEstoque).filter(models.CafeEstoque.id == pedido.cafe_id).first()
    if not cafe:
        raise HTTPException(status_code=404, detail="Café selecionado não existe.")

    pesos = {"250g": 0.25, "500g": 0.50, "1kg": 1.00}
    peso_total_pedido = pesos.get(pedido.tamanho_pacote, 0.00) * pedido.quantidade

    if cafe.quantidade_kg < peso_total_pedido:
        raise HTTPException(status_code=400, detail="Estoque insuficiente para este pedido!")

    cafe.quantidade_kg = round(cafe.quantidade_kg - peso_total_pedido, 2)

    precos = {"250g": cafe.preco_250g, "500g": cafe.preco_500g, "1kg": cafe.preco_1kg}
    valor_calculado = round(precos.get(pedido.tamanho_pacote, 0.00) * pedido.quantidade, 2)

    novo_pedido = models.Pedido(
        cliente=pedido.cliente,
        cafe_id=pedido.cafe_id,
        tamanho_pacote=pedido.tamanho_pacote,
        quantidade=pedido.quantidade,
        tipo_cafe=pedido.tipo_cafe,
        tipo_moagem=pedido.tipo_moagem,
        tipo_envio=pedido.tipo_envio,
        endereco=pedido.endereco,
        status="aguardando",
        pago=pedido.pago,
        valor_total=valor_calculado
    )
    
    db.add(novo_pedido)
    db.commit() 
    db.refresh(novo_pedido)
    return novo_pedido

@app.put("/pedidos/{pedido_id}/status")
def alterar_status_pedido(pedido_id: int, dados: StatusUpdate, db: Session = Depends(get_db)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if dados.status not in ["aguardando", "separado", "entregue"]:
        raise HTTPException(status_code=400, detail="Status inválido")
        
    pedido.status = dados.status
    db.commit()
    return pedido

@app.put("/pedidos/{pedido_id}/pagamento")
def alterar_pagamento_pedido(pedido_id: int, dados: PagamentoUpdate, db: Session = Depends(get_db)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
        
    pedido.pago = dados.pago
    db.commit()
    db.refresh(pedido)
    return pedido

@app.delete("/pedidos/{pedido_id}")  
def excluir_pedido(pedido_id: int, db: Session = Depends(get_db)):
    pedido = db.query(models.Pedido).filter(models.Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    db.delete(pedido)
    db.commit()
    return {"detail": f"Pedido #{pedido_id} excluído com sucesso."}


# --- ROTAS DE AUTENTICAÇÃO ---

@app.post("/login")
def login(dados: UserLogin, db: Session = Depends(get_db)):
    # Trava de contingência
    if dados.username == "admin" and dados.senha == "admin123":
        tempo_expira = datetime.now(timezone.utc) + timedelta(hours=8)
        token_dados = {
            "sub": "admin", 
            "cargo": "admin", 
            "exp": int(tempo_expira.timestamp())
        }
        token = jwt.encode(token_dados, SECRET_KEY, algorithm=ALGORITHM)
        return {"token": token, "cargo": "admin", "username": "admin"}

    user = db.query(models.Usuario).filter(models.Usuario.username == dados.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
        
    # Verificação usando a nova função SHA-256 estável
    if gerar_senha_hash(dados.senha) != user.senha_hash:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")
    
    tempo_expira = datetime.now(timezone.utc) + timedelta(hours=8)
    token_dados = {
        "sub": user.username, 
        "cargo": user.cargo, 
        "exp": int(tempo_expira.timestamp())
    }
    
    token = jwt.encode(token_dados, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token, "cargo": user.cargo, "username": user.username}


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
            raise HTTPException(status_code=403, detail="Apenas administradores podem cadastrar novos usuários")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
        
    existe = db.query(models.Usuario).filter(models.Usuario.username == dados.username).first()
    if existe:
        raise HTTPException(status_code=400, detail="Este usuário já existe")
        
    # Cadastro usando a nova função estável
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
        
    # Impedir que o administrador mestre se auto-exclua e fique preso do lado de fora
    if username == admin_atual:
        raise HTTPException(status_code=400, detail="Você não pode excluir o seu próprio usuário enquanto estiver logado")

    # Busca o usuário alvo no banco de dados
    user = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    db.delete(user)
    db.commit()
    return {"detail": f"Usuário '{username}' foi removido do sistema com sucesso!"}
