from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://quant_user:quant_pass@localhost:5432/quant_trading"

    # LLM provider config (Groq recommended: fast, free tier, Llama/Qwen models)
    

     # Gemini LLM configuration
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"


    # Market focus for MVP
    default_market: str = "NIFTY50"

    class Config:
        env_file = ".env"


settings = Settings()






