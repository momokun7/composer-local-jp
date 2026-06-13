"""composer_settings の型スタブ.

実体の composer_settings.py は gitignore 済み（プロジェクト ID 等を含むため）。
未作成時は __init__.py がデフォルト値を持つモジュールを動的に注入する。
このスタブは静的解析（pyright 等）に属性の型を伝えるためだけのもので、
実行時の値には影響しない。属性は __init__.py のフォールバックおよび
composer_settings.py.example と一致させること。
"""

# ローカル環境
LOCAL_ENV_NAME: str
LOCAL_PORT: int
COMPOSER_IMAGE_VERSION: str
COMPOSER_PYTHON_VERSION: str
DAGS_PATH: str

# GCP 連携
PROJECT_ID: str
COMPOSER_ENV_NAME: str
COMPOSER_LOCATION: str
SERVICE_ACCOUNT: str
SECRET_ID: str

# Airflow
AIRFLOW_URL: str
ADMIN_USERNAME: str
ADMIN_PASSWORD: str
ADMIN_EMAIL: str
ADMIN_FIRSTNAME: str
ADMIN_LASTNAME: str

# データベース
DATABASE_ENGINE: str
POSTGRES_USER: str
POSTGRES_PASSWORD: str
POSTGRES_DB: str
POSTGRES_PORT: int
POSTGRES_LOCAL_PORT: int

# 同期・監視・Docker・Variables 処理
DAG_DIR_LIST_INTERVAL: int
SYNC_INTERVAL: int
WEBSERVER_TIMEOUT: int
WEBSERVER_CHECK_INTERVAL: int
DOCKER_MEMORY_LIMIT: str
BIND_TO_LOCALHOST_ONLY: bool
POSTGRES_IMAGE: str
MAX_PARALLEL_WORKERS: int
MASK_PREFIX_LENGTH: int
MASK_SUFFIX_LENGTH: int
LOG_LEVEL: str
