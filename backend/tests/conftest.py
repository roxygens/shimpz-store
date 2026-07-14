"""Provide transaction-isolated test fixtures.

Each test runs inside a transaction rolled back at teardown, leaving the database untouched and avoiding
ordering coupling. This survives code under test calling `session.commit()` because
`join_transaction_mode="create_savepoint"` turns each commit into a SAVEPOINT release, and the outer
rollback undoes everything.
"""

import pytest
from app.db import engine, get_db
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture()
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session):
    # routes get the SAME rolled-back session, so HTTP tests are isolated too.
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
