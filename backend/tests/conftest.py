from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models.entities import AuditLog, AuthTokenRevocation, User

test_engine = create_engine(
    "sqlite+pysqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
TEST_TABLES = [User.__table__, AuthTokenRevocation.__table__, AuditLog.__table__]


@pytest.fixture(autouse=True)
def isolated_database() -> Iterator[None]:
    Base.metadata.create_all(test_engine, tables=TEST_TABLES)
    yield
    Base.metadata.drop_all(test_engine, tables=list(reversed(TEST_TABLES)))


@pytest.fixture
def db_session() -> Iterator[Session]:
    with TestSession() as session:
        yield session


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    def override_get_db() -> Iterator[Session]:
        with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
