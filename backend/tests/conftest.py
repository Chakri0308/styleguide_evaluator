import os
import tempfile

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://stylelens:stylelens@localhost:5432/stylelens_test")
os.environ["JOB_MODE"] = "inline"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_ROOT"] = tempfile.mkdtemp(prefix="stylelens-objects-")
os.environ.setdefault("EMBEDDING_MODEL", "hash:1024")
os.environ.setdefault("RERANKER_MODEL", "lexical")
os.environ.setdefault("LLM_GENERATION_MODEL", "fake:fake")
os.environ.setdefault("LLM_EXTRACTION_MODEL", "fake:fake")
os.environ.setdefault("LLM_VISION_MODEL", "fake:fake")
os.environ.setdefault("LLM_FAST_MODEL", "fake:fake")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

HERE = os.path.dirname(__file__)


@pytest.fixture(scope="session", autouse=True)
def migrate():
    cfg = Config(os.path.join(HERE, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "..", "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean_db(migrate):
    from stylelens.db.models import Base
    from stylelens.db.session import engine

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    yield


@pytest.fixture
async def client():
    from stylelens.api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def fixtures_dir():
    return os.path.join(HERE, "fixtures")
