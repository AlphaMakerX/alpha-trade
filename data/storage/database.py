from sqlalchemy import create_engine, Engine

from utils.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        db = get_settings()["database"]
        url = f"postgresql+psycopg2://{db['user']}:{db.get('password', '')}@{db['host']}:{db['port']}/{db['name']}"
        _engine = create_engine(url)
    return _engine
