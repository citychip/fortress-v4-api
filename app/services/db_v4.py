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
