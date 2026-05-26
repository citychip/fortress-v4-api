"""
V4 Database connections: MySQL + Redis
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
import redis
import os

# MySQL configuration
MYSQL_HOST = os.getenv('MYSQL_HOST', 'localhost')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_USER = os.getenv('MYSQL_USER', 'fortress')
MYSQL_PASS = os.getenv('MYSQL_PASS', 'fortress_v4_pass')
MYSQL_DB = os.getenv('MYSQL_DB', 'fortress_v4')

# Redis configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

# SQLAlchemy setup
MYSQL_URL = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASS}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
engine = create_engine(MYSQL_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis client
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_connections():
    """Test MySQL and Redis connections"""
    results = {}
    
    # Test MySQL
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT VERSION()"))
            results['mysql'] = f"OK - {result.fetchone()[0]}"
    except Exception as e:
        results['mysql'] = f"FAILED - {e}"
    
    # Test Redis
    try:
        redis_client.ping()
        results['redis'] = "OK - Connected"
    except Exception as e:
        results['redis'] = f"FAILED - {e}"
    
    return results


import logging as _logging
from datetime import date as _date

_db_logger = _logging.getLogger("fortress.db_v4")


def _pos_to_db_row(pos: dict, account_id: str):
    """Map a sync position dict to a MySQL positions-table row dict. Returns None on error."""
    try:
        conid = pos.get("conid")
        if conid is None:
            return None
        expiry_val = None
        expiry_str = pos.get("expiry")
        if expiry_str:
            try:
                expiry_val = _date.fromisoformat(expiry_str)
            except (ValueError, TypeError):
                pass
        qty = pos.get("qty")
        avg_cost = pos.get("avg_cost")
        market_value = pos.get("market_value")
        strike = pos.get("strike")
        mult = pos.get("multiplier", "100")
        try:
            mult_f = float(mult)
        except (TypeError, ValueError):
            mult_f = 100.0
        cost_basis = abs(float(avg_cost or 0) * float(qty or 0))
        return {
            "conid": str(conid),
            "symbol": pos.get("ticker", ""),
            "sec_type": pos.get("sec_type", ""),
            "description": pos.get("local_symbol") or "",
            "multiplier": mult_f,
            "position": int(round(float(qty or 0))),
            "market_value": float(market_value) if market_value is not None else None,
            "cost_basis": cost_basis if cost_basis else None,
            "avg_cost": float(avg_cost) if avg_cost is not None else None,
            "strike": float(strike) if strike is not None else None,
            "expiry": expiry_val,
            "opt_right": pos.get("right"),
            "currency": pos.get("currency", "USD"),
            "account": account_id,
        }
    except Exception as exc:
        _db_logger.debug("_pos_to_db_row skipped position: %s", exc)
        return None


def upsert_positions(positions_data: list, account_id: str) -> int:
    """Upsert a list of sync position dicts into the MySQL positions table.
    Returns count of rows written. Never raises — logs and returns 0 on error."""
    if not positions_data:
        return 0
    rows = [_pos_to_db_row(p, account_id) for p in positions_data]
    rows = [r for r in rows if r]
    if not rows:
        return 0
    try:
        from sqlalchemy.dialects.mysql import insert as _mysql_insert
        from app.services.models_v4 import Position as _Position
        with SessionLocal() as db:
            for row in rows:
                stmt = _mysql_insert(_Position).values(**row)
                update_cols = {k: stmt.inserted[k] for k in row if k not in ("conid", "account")}
                stmt = stmt.on_duplicate_key_update(**update_cols)
                db.execute(stmt)
            db.commit()
        _db_logger.info("MySQL upsert: %d positions written for account %s", len(rows), account_id)
        return len(rows)
    except Exception as exc:
        _db_logger.warning("MySQL positions upsert failed: %s", exc)
        return 0


def upsert_greeks(positions_data: list, account_id: str) -> int:
    """Upsert Greeks data for OPT positions into the MySQL greeks table.
    Returns count of rows written. Never raises."""
    opt_legs = [
        p for p in (positions_data or [])
        if (p.get("sec_type") or "").upper() == "OPT"
        and p.get("conid") is not None
        and p.get("current_delta") is not None
    ]
    if not opt_legs:
        return 0
    try:
        from sqlalchemy.dialects.mysql import insert as _mysql_insert
        from app.services.models_v4 import Greeks as _Greeks
        with SessionLocal() as db:
            for pos in opt_legs:
                row = {
                    "conid": str(pos["conid"]),
                    "symbol": pos.get("ticker", ""),
                    "account": account_id,
                    "delta": pos.get("current_delta"),
                    "gamma": pos.get("current_gamma"),
                    "theta": pos.get("current_theta"),
                    "vega": pos.get("current_vega"),
                    "underlying_symbol": pos.get("ticker", ""),
                }
                stmt = _mysql_insert(_Greeks).values(**row)
                update_cols = {k: stmt.inserted[k] for k in row if k not in ("conid", "account")}
                stmt = stmt.on_duplicate_key_update(**update_cols)
                db.execute(stmt)
            db.commit()
        _db_logger.info("MySQL upsert: %d greeks rows written", len(opt_legs))
        return len(opt_legs)
    except Exception as exc:
        _db_logger.warning("MySQL greeks upsert failed: %s", exc)
        return 0
