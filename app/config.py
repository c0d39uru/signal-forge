from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://scanner:scanner@localhost:5432/scanner"
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    FMP_API_KEY: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "market-news-scanner/0.1"
    SEC_USER_AGENT: str = "MarketNewsScanner contact@example.com"
    AI_PROVIDER: str = "mock"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()