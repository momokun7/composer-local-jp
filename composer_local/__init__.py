# composer_local package
#
# 注意: ここで cli 等を import すると click, rich, GCP SDK 等の重い依存が
# すべて読み込まれ、パッケージの import に数秒かかる。
# 各モジュールは from composer_local import xxx で必要に応じて直接 import すること。

import sys
import types
from typing import Any

# composer_settings.py が存在しない場合でも動作するようにデフォルト値を提供する。
# これにより GCP 設定なしでもローカル環境を構築・起動できる。
try:
    from composer_local import composer_settings as _test  # noqa: F401
except ImportError:
    # 動的に属性を設定するため Any として宣言（pyright の ModuleType 属性代入エラーを回避）
    _defaults: Any = types.ModuleType("composer_local.composer_settings")

    # ローカル環境設定（デフォルト値）
    _defaults.LOCAL_ENV_NAME = "my-local-env"
    _defaults.LOCAL_PORT = 8080
    _defaults.COMPOSER_IMAGE_VERSION = "composer-3-airflow-2.10.5-build.13"
    _defaults.COMPOSER_PYTHON_VERSION = ""
    _defaults.DAGS_PATH = "dags"

    # GCP 設定（空文字列 = 未設定）
    _defaults.PROJECT_ID = ""
    _defaults.COMPOSER_ENV_NAME = ""
    _defaults.COMPOSER_LOCATION = ""
    _defaults.SERVICE_ACCOUNT = ""
    _defaults.SECRET_ID = ""

    # Airflow 設定
    _defaults.AIRFLOW_URL = "http://localhost:8080"
    _defaults.ADMIN_USERNAME = "admin"
    _defaults.ADMIN_PASSWORD = "admin"
    _defaults.ADMIN_EMAIL = "admin@example.com"
    _defaults.ADMIN_FIRSTNAME = "Admin"
    _defaults.ADMIN_LASTNAME = "User"

    # データベース設定
    _defaults.DATABASE_ENGINE = "postgresql"
    _defaults.POSTGRES_USER = "postgres"
    _defaults.POSTGRES_PASSWORD = "airflow"
    _defaults.POSTGRES_DB = "airflow"
    _defaults.POSTGRES_PORT = 5432
    _defaults.POSTGRES_LOCAL_PORT = 25432
    _defaults.DAG_DIR_LIST_INTERVAL = 10

    # 同期・監視設定
    _defaults.SYNC_INTERVAL = 300
    _defaults.WEBSERVER_TIMEOUT = 300
    _defaults.WEBSERVER_CHECK_INTERVAL = 2

    # Docker 設定
    _defaults.DOCKER_MEMORY_LIMIT = "4g"
    _defaults.BIND_TO_LOCALHOST_ONLY = True
    _defaults.POSTGRES_IMAGE = "postgres:14-alpine"

    # Variables 処理設定
    _defaults.MAX_PARALLEL_WORKERS = 10
    _defaults.MASK_PREFIX_LENGTH = 4
    _defaults.MASK_SUFFIX_LENGTH = 4

    sys.modules["composer_local.composer_settings"] = _defaults
