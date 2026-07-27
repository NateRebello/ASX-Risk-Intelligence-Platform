import json

import pandas as pd

from config import settings
from src.db import engine as db_engine
from src.storage.s3_archive import archive_dataframe


class FakeS3:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


class FakeSecretsManager:
    def __init__(self, value):
        self.value = value

    def get_secret_value(self, SecretId):
        return {"SecretString": self.value}


def test_archive_dataframe_writes_versioned_raw_csv():
    client = FakeS3()
    dataframe = pd.DataFrame({"date": ["2026-01-01"], "close": [100.0]})

    key = archive_dataframe(dataframe, "yahoo-prices", "CBA", bucket="audit-bucket", client=client)

    assert key is not None
    assert key.startswith("raw/yahoo-prices/")
    assert key.endswith("/CBA.csv")
    assert client.calls[0]["Bucket"] == "audit-bucket"
    assert client.calls[0]["ServerSideEncryption"] == "AES256"


def test_runtime_secret_json_password(monkeypatch):
    monkeypatch.setattr(settings, "DB_SECRET_ARN", "arn:aws:secretsmanager:ap-southeast-2:123:secret:test")
    monkeypatch.setattr(
        db_engine.boto3,
        "client",
        lambda *args, **kwargs: FakeSecretsManager(json.dumps({"username": "app", "password": "safe/password"})),
    )

    assert db_engine._database_password() == "safe/password"


def test_database_url_escapes_password(monkeypatch):
    monkeypatch.setattr(settings, "DB_SECRET_ARN", "")
    monkeypatch.setattr(settings, "DB_PASSWORD", "safe/password")

    url = db_engine.database_url()

    assert str(url).startswith("postgresql+psycopg2://")
    assert "safe%2Fpassword" in url.render_as_string(hide_password=False)


def test_get_engine_requires_ssl(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(settings, "DB_SECRET_ARN", "")
    monkeypatch.setattr(settings, "DB_PASSWORD", "safe/password")
    monkeypatch.setattr(db_engine, "create_engine", fake_create_engine)
    db_engine._engine = None

    db_engine.get_engine()

    assert captured["kwargs"]["connect_args"] == {"sslmode": "require"}


def test_run_migrations_executes_statements_via_text(tmp_path, monkeypatch):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "schema.sql").write_text(
        "CREATE TABLE IF NOT EXISTS demo (id INT);  -- percent % note\n",
        encoding="utf-8",
    )

    executed = []

    class FakeConn:
        def execute(self, statement):
            executed.append(statement)

    class FakeBegin:
        def __enter__(self):
            return FakeConn()

        def __exit__(self, *args):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    monkeypatch.setattr(db_engine, "get_engine", lambda: FakeEngine())
    db_engine.run_migrations(sql_dir=str(sql_dir))

    assert len(executed) == 1
    assert "CREATE TABLE IF NOT EXISTS demo" in str(executed[0])
