"""Check which required environment variables are set/missing."""
import os
from dotenv import load_dotenv
load_dotenv()

REQUIRED = {
    "DATABASE_URL": "Neon PostgreSQL connection string",
    "JWT_SECRET_KEY": "JWT signing secret",
    "QDRANT_URL": "Qdrant Cloud cluster URL (e.g. https://xxx.cloud.qdrant.io)",
    "QDRANT_API_KEY": "Qdrant Cloud API key",
    "GROQ_API_KEY": "Groq LLM API key",
    "GEMINI_API_KEY": "Google Gemini API key",
    "OPENROUTER_API_KEY": "OpenRouter API key",
    "ENV": "Environment (should be 'production' on Render)",
}

OPTIONAL = {
    "FRONTEND_URL": "Frontend URL for CORS (e.g. https://rag-2-ggpa.onrender.com)",
    "QDRANT_COLLECTION": "Qdrant collection name (default: rag_enterprise_chunks)",
    "EMBEDDING_MODEL": "Embedding model (default: all-MiniLM-L6-v2)",
}

print("=" * 60)
print("RAG Intelligence — Environment Check")
print("=" * 60)

all_ok = True
for key, desc in REQUIRED.items():
    val = os.getenv(key)
    if val:
        masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
        print(f"  ✅ {key}: {masked}")
    else:
        print(f"  ❌ {key}: NOT SET ({desc})")
        all_ok = False

print()
print("Optional:")
for key, desc in OPTIONAL.items():
    val = os.getenv(key)
    status = f"✅ {val[:20]}..." if val else f"⚠️  NOT SET (default ok)"
    print(f"  {status} {key}")

print()
if all_ok:
    print("✅ All required environment variables are set!")
else:
    print("❌ Some required env vars are missing. Add them to Render or your .env file.")
