from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Float, Boolean
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    senha_hash = Column(String, nullable=False) # Armazena a senha criptografada
    cargo = Column(String, default="operador")   # 'admin' ou 'operador'

class CafeEstoque(Base):
    __tablename__ = "cafe_estoque"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, unique=True, index=True)
    quantidade_kg = Column(Float, default=0.0)
    preco_250g = Column(Float, default=0.0)
    preco_500g = Column(Float, default=0.0)
    preco_1kg = Column(Float, default=0.0)

class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    cliente = Column(String, nullable=False)
    cafe_id = Column(Integer, nullable=False)
    tamanho_pacote = Column(String, nullable=False)
    quantidade = Column(Integer, default=1)
    tipo_cafe = Column(String, nullable=False)
    tipo_moagem = Column(String, nullable=True) 
    tipo_envio = Column(String, nullable=False)
    endereco = Column(String, nullable=True)
    status = Column(String, default="aguardando")
    pago = Column(Boolean, default=False)
    # Novos campos do pedido
    data_pedido = Column(DateTime, default=datetime.now) # <-- Captura a data e hora automaticamente
    valor_total = Column(Float, nullable=False)