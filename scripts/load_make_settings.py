"""composer_settings.py の設定値を Makefile 変数として標準出力に書き出す。

Makefile から呼び出され、.make-settings.mk に設定値を書き出す。
__init__.py の重い import chain（cli -> click, rich, GCP SDK 等）をバイパスし、
importlib.util で設定ファイルのみを直接読み込むことで高速化（~0.03s）。

エラー時（ファイル未存在、構文エラー等）は空出力で正常終了する。
Makefile 側でデフォルト値にフォールバックされるため問題ない。
"""

import importlib.util

# composer_settings.py -> Makefile 変数のマッピング定義
# (Makefile変数名, composer_settings.py の属性名)
_MAPPING = [
    ("_CS_ENV", "LOCAL_ENV_NAME"),
    ("_CS_PORT", "LOCAL_PORT"),
    ("_CS_IMAGE", "COMPOSER_IMAGE_VERSION"),
    ("_CS_DAGS", "DAGS_PATH"),
    ("_CS_PROJECT", "PROJECT_ID"),
    ("_CS_LOCATION", "COMPOSER_LOCATION"),
    ("_CS_ENV_NAME", "COMPOSER_ENV_NAME"),
    ("_CS_SECRET_ID", "SECRET_ID"),
    ("_CS_SA", "SERVICE_ACCOUNT"),
    ("_CS_AU", "ADMIN_USERNAME"),
    ("_CS_AP", "ADMIN_PASSWORD"),
    ("_CS_AE", "ADMIN_EMAIL"),
    ("_CS_AF", "ADMIN_FIRSTNAME"),
    ("_CS_AL", "ADMIN_LASTNAME"),
    ("_CS_DB", "DATABASE_ENGINE"),
]


def main() -> None:
    """設定ファイルを読み込み、Makefile 変数として出力する。"""
    # 設定ファイルを直接読み込み（パッケージ全体の import を回避）
    spec = importlib.util.spec_from_file_location(
        "composer_settings", "composer_local/composer_settings.py"
    )
    if spec is None or spec.loader is None:
        return

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 各設定値を Makefile 変数として出力
    # 属性が未定義の場合（例: GCP 設定がコメントアウトされている）はスキップ
    for make_var, attr_name in _MAPPING:
        value = getattr(mod, attr_name, None)
        if value is not None:
            print(f"{make_var} := {value}")


if __name__ == "__main__":
    try:
        main()
    except (ImportError, FileNotFoundError, SyntaxError, Exception):
        # 読み込みに失敗した場合は空出力で正常終了
        # Makefile 側のデフォルト値が使われる
        pass
