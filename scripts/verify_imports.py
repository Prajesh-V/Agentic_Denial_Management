import sys


def test_imports():
    modules = [
        ("FastAPI", "fastapi"),
        ("Uvicorn", "uvicorn"),
        ("Pydantic", "pydantic"),
        ("Pydantic Settings", "pydantic_settings"),
        ("SQLAlchemy", "sqlalchemy"),
        ("Alembic", "alembic"),
        ("psycopg", "psycopg"),
        ("LangGraph", "langgraph"),
        ("LangChain Core", "langchain_core"),
        ("LangChain Ollama", "langchain_ollama"),
        ("Faker", "faker"),
        ("NumPy", "numpy"),
        ("Sentence Transformers", "sentence_transformers"),
        ("FAISS", "faiss"),
        ("pytest", "pytest"),
        ("HTTPX", "httpx"),
        ("Ruff", "ruff"),
    ]
    
    print(f"Testing imports on Python {sys.version}...\n", flush=True)
    all_ok = True
    for name, mod in modules:
        print(f"Importing {name} ({mod})...", end="", flush=True)
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "installed")
            print(f" [OK: {ver}]", flush=True)
        except Exception as e:
            print(f" [FAIL: {e}]", flush=True)
            all_ok = False
            
    if all_ok:
        print("\nAll 17 core libraries imported successfully!", flush=True)
        sys.exit(0)
    else:
        print("\nSome libraries failed to import!", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
