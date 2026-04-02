from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    MIDTRANS_SERVER_KEY: str
    MIDTRANS_CLIENT_KEY: str
    MIDTRANS_IS_PRODUCTION: bool
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASS: str

    class Config:
        env_file = ".env"

settings = Settings()