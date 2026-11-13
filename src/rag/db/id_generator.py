import hashlib
import json
import uuid
from typing import Optional

def compute_content_hash(content: bytes) -> str:
    """Computes a SHA-256 hash of raw file bytes for duplicate detection."""
    return hashlib.sha256(content).hexdigest()

def generate_document_id(tenant_id: str, filename: str, content_hash: str) -> str:
    """
    Generates a deterministic document UUID (UUIDv5) based on tenant_id, filename, and content_hash.
    Uses canonical JSON tuple serialization to guarantee unambiguous, injective identity.
    """
    namespace = uuid.NAMESPACE_DNS
    identity_str = json.dumps([tenant_id, filename, content_hash], separators=(",", ":"), ensure_ascii=False)
    return str(uuid.uuid5(namespace, identity_str))

def generate_chunk_id(document_id: str, chunk_index: int, chunk_type: str = "text") -> str:
    """
    Generates a deterministic chunk UUID (UUIDv5) based on parent document_id, chunk_index, and chunk_type.
    Uses canonical JSON tuple serialization to guarantee unambiguous identity.
    """
    namespace = uuid.NAMESPACE_OID
    chunk_str = json.dumps([document_id, chunk_type, int(chunk_index)], separators=(",", ":"), ensure_ascii=False)
    return str(uuid.uuid5(namespace, chunk_str))
