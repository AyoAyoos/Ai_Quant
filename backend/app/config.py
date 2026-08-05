from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://quant_user:quant_pass@localhost:5432/quant_trading"

    # LLM provider config (Groq recommended: fast, free tier, Llama/Qwen models)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Market focus for MVP
    default_market: str = "NIFTY50"

    class Config:
        env_file = ".env"


settings = Settings()
