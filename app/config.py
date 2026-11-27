import os


def _b(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "sim"}


class Settings:
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:SENHA@localhost:5432/postgres")
    # O módulo novo (Pregões/Atas) vive no schema pregao_atas; o portal existente fica em public.
    pg_search_path = os.getenv("PG_SEARCH_PATH", "pregao_atas,public,extensions")
    storage_dir = os.getenv("STORAGE_DIR", "./storage")
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "8"))               # confirmação / NF (Guia: 8 MB)
    max_pregao_upload_mb = int(os.getenv("MAX_PREGAO_UPLOAD_MB", "25"))  # editais costumam ser maiores
    cnpj_validar_dv = _b(os.getenv("CNPJ_VALIDAR_DV", "true"))
    email_reenvio_espera_s = int(os.getenv("EMAIL_REENVIO_ESPERA_S", "60"))  # "espere um minuto"
    # Autenticação: o Portal RPA já tem login; escolha como o token/usuário chega até aqui.
    auth_mode = os.getenv("AUTH_MODE", "header")          # header | jwt
    jwt_secret = os.getenv("AUTH_JWT_SECRET", "")
    jwt_algorithm = os.getenv("AUTH_JWT_ALGORITHM", "HS256")
    jwt_claim_user = os.getenv("AUTH_JWT_CLAIM_USER", "name")
    jwt_claim_role = os.getenv("AUTH_JWT_CLAIM_ROLE", "role")
    mail_backend = os.getenv("MAIL_BACKEND", "console")   # console | smtp
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_starttls = _b(os.getenv("SMTP_STARTTLS", "true"))
    mail_from = os.getenv("MAIL_FROM", "licitacoes@exemplo.com.br")
    cors_origins = [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]


settings = Settings()
