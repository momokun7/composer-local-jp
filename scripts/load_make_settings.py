"""composer_settings.py の設定値を Makefile 変数として標準出力に書き出す。

__init__.py の重い import chain（cli → click, rich, GCP SDK 等）をバイパスし、
importlib.util で設定ファイルのみを直接読み込むことで高速化（~0.03s）。
"""

import importlib.util
import sys

spec = importlib.util.spec_from_file_location(
    "composer_settings", "composer_local/composer_settings.py"
)
if spec is None:
    sys.exit()

mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SETTINGS = [
    ("_CS_ENV", mod.LOCAL_ENV_NAME),
    ("_CS_PORT", mod.LOCAL_PORT),
    ("_CS_IMAGE", mod.COMPOSER_IMAGE_VERSION),
    ("_CS_DAGS", mod.DAGS_PATH),
    ("_CS_PROJECT", mod.PROJECT_ID),
    ("_CS_LOCATION", mod.COMPOSER_LOCATION),
    ("_CS_ENV_NAME", mod.COMPOSER_ENV_NAME),
    ("_CS_SECRET_ID", mod.SECRET_ID),
    ("_CS_SA", mod.SERVICE_ACCOUNT),
    ("_CS_AU", mod.ADMIN_USERNAME),
    ("_CS_AP", mod.ADMIN_PASSWORD),
    ("_CS_AE", mod.ADMIN_EMAIL),
    ("_CS_AF", mod.ADMIN_FIRSTNAME),
    ("_CS_AL", mod.ADMIN_LASTNAME),
    ("_CS_DB", mod.DATABASE_ENGINE),
]

for key, value in SETTINGS:
    print(f"{key} := {value}")
