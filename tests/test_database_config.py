import pytest
import os
from src.rag.db.database import normalize_database_url, mask_connection_url, Base, DEFAULT_DB_URL
from src.rag.db import models

def test_normalize_database_url():
    # Legacy postgres:// prefix
    legacy = "postgres://user:pass@host:5432/db"
    assert normalize_database_url(legacy).startswith("postgresql://")

    # Standard postgresql://
    std = "postgresql://user:pass@host:5432/db?sslmode=require"
    assert normalize_database_url(std) == std

    # Empty fallback
    assert normalize_database_url(None) == DEFAULT_DB_URL
    assert normalize_database_url("") == DEFAULT_DB_URL

def test_mask_connection_url_credentials():
    secret_url = "postgresql://neondb_owner:npg_SecretPass123@ep-sample-pooler.c-8.aws.neon.tech/neondb?sslmode=require"
    masked = mask_connection_url(secret_url)
    assert "npg_SecretPass123" not in masked
    assert ":****@" in masked
    assert "neondb_owner" in masked
    assert "ep-sample-pooler.c-8.aws.neon.tech" in masked

def test_models_remain_consistent():
    tables = Base.metadata.tables
    expected_tables = {"tenants", "users", "documents", "document_chunks", "ingestion_jobs"}
    assert set(tables.keys()) == expected_tables

    # Check key columns
    assert "content_hash" in tables["documents"].columns
    assert "sync_status" in tables["document_chunks"].columns
    assert "qdrant_point_id" in tables["document_chunks"].columns
