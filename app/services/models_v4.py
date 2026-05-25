"""V4 SQLAlchemy ORM models"""
from sqlalchemy import Column, Integer, String, DECIMAL, Date, DateTime, Enum, JSON, TIMESTAMP, Text
from sqlalchemy.sql import func
from app.services.db_v4 import Base

class Position(Base):
    __tablename__ = 'positions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    conid = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(20))
    sec_type = Column(String(10))
    description = Column(String(255))
    multiplier = Column(DECIMAL(10, 4))
    position = Column(Integer)
    market_value = Column(DECIMAL(15, 2))
    cost_basis = Column(DECIMAL(15, 2))
    unrealized_pnl = Column(DECIMAL(15, 2))
    realized_pnl = Column(DECIMAL(15, 2))
    avg_cost = Column(DECIMAL(15, 4))
    strike = Column(DECIMAL(10, 4))
    expiry = Column(Date)
    opt_right = Column(String(1))
    currency = Column(String(3))
    account = Column(String(20))
    sector = Column(String(50))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class MarketQuote(Base):
    __tablename__ = 'market_quotes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True)
    last_price = Column(DECIMAL(10, 4))
    bid_price = Column(DECIMAL(10, 4))
    ask_price = Column(DECIMAL(10, 4))
    bid_size = Column(Integer)
    ask_size = Column(Integer)
    open_price = Column(DECIMAL(10, 4))
    high_price = Column(DECIMAL(10, 4))
    low_price = Column(DECIMAL(10, 4))
    close_price = Column(DECIMAL(10, 4))
    volume = Column(Integer)
    timestamp = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class Alert(Base):
    __tablename__ = 'alerts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String(30), nullable=False)
    symbol = Column(String(20))
    alert_condition = Column(String(255))
    threshold_value = Column(DECIMAL(15, 4))
    current_value = Column(DECIMAL(15, 4))
    message = Column(Text)
    severity = Column(Enum('info', 'warning', 'critical', name='alert_severity'), default='info')
    status = Column(Enum('active', 'triggered', 'acknowledged', 'expired', name='alert_status'), default='active')
    triggered_at = Column(TIMESTAMP, nullable=True)
    acknowledged_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class Execution(Base):
    __tablename__ = 'executions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    exec_id = Column(String(50), unique=True)
    order_id = Column(String(50))
    conid = Column(String(50))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10))
    quantity = Column(Integer)
    price = Column(DECIMAL(10, 4))
    avg_price = Column(DECIMAL(10, 4))
    currency = Column(String(3))
    account = Column(String(20))
    exec_time = Column(DateTime)
    settlement_date = Column(Date)
    trade_id = Column(String(50))
    notes = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), unique=True)
    conid = Column(String(50))
    symbol = Column(String(20), nullable=False)
    side = Column(String(10))
    order_type = Column(String(20))
    quantity = Column(Integer)
    lmt_price = Column(DECIMAL(10, 4))
    aux_price = Column(DECIMAL(10, 4))
    status = Column(Enum('pending', 'submitted', 'filled', 'partially_filled', 'cancelled', 'rejected', name='order_status'), default='pending')
    filled_quantity = Column(Integer, default=0)
    avg_fill_price = Column(DECIMAL(10, 4))
    account = Column(String(20))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class Config(Base):
    __tablename__ = 'config'
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(Text)
    config_type = Column(String(20))
    description = Column(String(255))
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    entity_type = Column(String(30))
    entity_id = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    user_id = Column(String(50))
    metadata = Column(JSON)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())