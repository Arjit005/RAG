import hashlib
import uuid
from typing import Optional

def compute_content_hash(content: bytes) -> str:
    """Computes a SHA-256 hash of raw file bytes for duplicate detection."""
    return hashlib.sha256(content).hexdigest()

def generate_document_id(tenant_id: str, filename: str, content_hash: str) -> str:
    """
    Generates a deterministic document UUID (UUIDv5) based on tenant_id, filename, and content_hash.
    Guarantees stable identity across re-indexing and eliminates array-index shifting.
    """
    namespace = uuid.NAMESPACE_DNS
    identity_str = f"tenant:{tenant_id}:doc:{filename}:{content_hash}"
    return str(uuid.uuid5(namespace, identity_str))

def generate_chunk_id(document_id: str, chunk_index: int, chunk_type: str = "text") -> str:
    """
    Generates a deterministic chunk UUID (UUIDv5) based on parent document_id, chunk_index, and chunk_type.
    """
    namespace = uuid.NAMESPACE_OID
    chunk_str = f"doc:{document_id}:type:{chunk_type}:idx:{chunk_index}"
    return str(uuid.uuid5(namespace, chunk_str))
