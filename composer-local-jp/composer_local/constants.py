import enum
from dataclasses import dataclass

CLOUD_CLI_CONFIG_PATH_ENV = "CLOUDSDK_CONFIG"
KUBECONFIG_PATH_ENV = "KUBECONFIG"

OPERATION_TIMEOUT_SECONDS = 1200


class ContainerStatus(str, enum.Enum):
    RUNNING = "running"
    CREATED = "created"


@dataclass
class DatabaseEngine:
    sqlite3 = "sqlite3"
    postgresql = "postgresql"

    @classmethod
    def choices(cls):
        return [cls.sqlite3, cls.postgresql]


COMPOSER_VERSIONING_DOCS_LINK = (
    "https://cloud.google.com/composer/docs/concepts/versioning/composer-versions"
)
IMAGE_VERSION_PATTERN = (
    r"composer-([1-9]+(?:\.[0-9]+\.[0-9]+)?)-airflow-([1-9]+\.[0-9]+\.[0-9]+(?:-build\.[0-9]+)?)"
)
DOCKER_REGISTRY_IMAGE_TAG = (
    "us-docker.pkg.dev/cloud-airflow-releaser/"
    "airflow-worker-scheduler-{dashed_airflow_v}/"
    "airflow-worker-scheduler-{dashed_airflow_v}:"
    "{image_tag}"
)

# =============================================================================
# ANSI色コード
# =============================================================================
ANSI_RED = "\033[0;31m"
ANSI_GREEN = "\033[0;32m"
ANSI_YELLOW = "\033[0;33m"
ANSI_BLUE = "\033[0;34m"
ANSI_GRAY = "\033[90m"
ANSI_RESET = "\033[0m"

AIRFLOW_HOME = "/home/airflow"
ENTRYPOINT_PATH = f"{AIRFLOW_HOME}/entrypoint.sh"

CREATE_MESSAGE = (
    "\n"
    f"環境ディレクトリ:\n"
    "{env_dir}\n"
    "\n"
    f"設定ファイル:\n"
    f"• 一般設定:{{config_path}}\n"
    f"• PyPI パッケージ:{{requirements_path}}\n"
    f"• 環境変数:{{env_variables_path}}\n"
    "\n"
    f"ディレクトリ構成:\n"
    f"• プラグイン:{{env_dir}}/plugins\n"
    f"• データ:{{env_dir}}/data\n"
    f"• DAG:{{dags_path}}\n"
    "\n"
)
START_MESSAGE = (
    "\n{env_name} 環境を起動しました。\n\n"
    "DAG は {dags_path} に配置すると自動で読み込まれ、更新すると即座に反映されます\n"
)
FINAL_ENV_MESSAGE = "\nこの情報は環境の構成ファイルに基づいて表示されています。\n"

CONTAINER_NAME = "composer-local-dev"
DB_CONTAINER_NAME = "composer-local-dev-db"
DOCKER_NETWORK_NAME = "composer-local-dev-network"
CREATING_DAGS_PATH_WARN = "DAGs パス '{dags_path}' が存在しません。作成します。"
DAGS_PATH_NOT_PROVIDED_WARN = (
    "DAGs ディレクトリが指定されていないため、デフォルトのディレクトリを使用します。"
)
ADD_DEBUG_ON_ERROR_INFO = "\n\nデバッグメッセージを表示するには --debug フラグを付与してください。"
DAGS_PATH_NOT_EXISTS_ERROR = "DAGs パスが存在しないか、ディレクトリではありません: {dags_path}"
ENVIRONMENT_NAME_TOO_SHORT_ERROR = "環境名 '{env_name}' が短すぎます（最小 3 文字）。"
ENVIRONMENT_NAME_TOO_LONG_ERROR = "環境名 '{env_name}' が長すぎます（最大 40 文字）。"
ENVIRONMENT_NAME_NOT_VALID_ERROR = (
    "環境名 '{env_name}' は無効です。使用できるのは英数字、アンダースコア、ハイフンのみです。"
)
COMPOSER_SOFTWARE_CONFIG_API_ERROR = "Cloud Composer の環境設定の取得に失敗しました: {err}"
ENVIRONMENT_DIR_NOT_FOUND_ERROR = "'{env_dir}' ディレクトリが見つかりません。{create_help}"
ENVIRONMENT_DIR_EMPTY_ERROR = "'{env_dir}' に環境が見つかりません。{create_help}"
ENVIRONMENTS_NOT_FOUND = "指定のパスに環境が見つかりませんでした: {path}"
ENVIRONMENTS_FOUND = "次のローカル Composer 環境が見つかりました: {path}\n"
ENVIRONMENT_PATH_NOT_FOUND_ERROR = (
    "'{env_path}' ディレクトリが見つかりません。"
    "環境名が正しいか、環境が存在するかを確認してください。{create_help}"
)
ENVIRONMENT_NOT_SELECTED_ERROR = (
    "'{env_dir}' には複数の環境が存在しますが、環境名が指定されていません。\n"
    "既存のいずれかの環境を選択するため、引数に環境名を指定してください:\n    {env_names}"
)
ENVIRONMENT_ALREADY_RUNNING = (
    "環境 '{name}' はすでに起動中です。実行したい場合は停止または再起動してください。"
)
GCLOUD_CONFIG_NOT_FOUND_ERROR = (
    "gcloud の設定場所を解決できませんでした。" "CLOUDSDK_CONFIG 環境変数で上書きしてください。"
)
PORT_IN_USE_ERROR = (
    "ポート {port} は既に使用中です。別のポートを使用するか、このポートを使用しているアプリケーションを終了してください。\n"
    "環境起動時に --port オプションで別ポートを指定できます。"
)
ENVIRONMENT_FAILED_TO_START_ERROR = "環境の起動に失敗しました。"
ENV_DID_NOT_START_TIMEOUT_ERROR = "環境が {seconds} 秒以内に起動しませんでした。"
ENV_NOT_RUNNING = "コマンドの実行に失敗しました：環境が起動していません。"
MISSING_REQUIRED_PARAM_ERROR = "必須パラメータ '{param}' が 'config.json' に存在しません。"
INVALID_CONFIGURATION_FILE_ERROR = "設定ファイル '{config_path}' の解析に失敗しました: {error}"
INVALID_ENV_VARIABLES_FILE_ERROR = (
    "環境変数ファイル ({env_file_path}) の解析に失敗しました。"
    "行 '{line}' は無効です。各行は FOO=BAR の形式で指定してください。"
)
INVALID_INT_VALUE_ERROR = "設定 '{param_name}' の値が無効です。'{value}' は整数ではありません。"
INVALID_INT_RANGE_VALUE_ERROR = (
    "設定 '{param_name}' の値が無効です。{value} は許可範囲 {allowed_range} に含まれません。"
)
INVALID_IMAGE_VERSION_ERROR = (
    "Composer のバージョンは"
    " `composer-(2.y.z|3)-airflow-a.b.c[-build.d]`"
    " の形式である必要があります。"
)
IMAGE_TAG_DOES_NOT_EXIST_ERROR = (
    "Composer バージョン {image_tag} は無効の可能性があります。"
    "存在する Cloud Composer のバージョンを使用してください。"
    "利用可能なバージョンはドキュメントを参照してください: "
    f"{COMPOSER_VERSIONING_DOCS_LINK}"
)
AUTH_INVALID_ERROR = (
    "認証データを検証できませんでした: {error}\n"
    "インターネット接続を確認してください。\n"
    "新しい認証情報を取得・適用するには次の 2 コマンドを実行してください:\n\n"
    "    $ gcloud auth login\n"
    "    $ gcloud auth application-default login\n\n"
    "実行後に再試行してください。"
)
PULL_IMAGE_MSG = "[bold green]Composer イメージを取得中です。数分かかる場合があります。"
DB_PULL_IMAGE_MSG = "[bold green]データベース イメージを取得中です。数分かかる場合があります。"
DOCKER_NOT_AVAILABLE_ERROR = (
    "Docker が利用できないか起動に失敗しました。"
    "Docker サービスがインストール済みで起動していることを確認してください。"
    "エラー: {error}"
)
# メモリ制限は composer_settings.py から取得
# DOCKER_CONTAINER_MEMORY_LIMIT = "4g"  # 削除: composer_settings.py から取得
NOT_MODIFIABLE_ENVIRONMENT_VARIABLES = {"AIRFLOW_HOME"}
STRICT_ENVIRONMENT_VARIABLES = {"AIRFLOW__CORE__EXECUTOR": ["LocalExecutor", "SequentialExecutor"]}
LIST_COMMAND_EPILOG = (
    "\n詳細情報や潜在的な設定エラーを確認するには、環境名を指定して describe コマンドを実行してください。\n\n"
    "* 表示内容は環境設定ファイルの情報に基づきます。"
)
REMOVE_ENV_CONFIRMATION_PROMPT = (
    "この操作はディレクトリ '{env_path}' とその配下の全て（data/plugins/dags）を削除します。"
    "Docker イメージは削除されません。"
)
REMOVING_CONTAINER_MSG = "環境は実行中です。コンテナを停止します..."
USE_FORCE_TO_REMOVE_ERROR = (
    "環境は実行中です。停止して削除するには --force フラグを使用してください。"
)
MALFORMED_CONFIG_REMOVING_CONTAINER = (
    "環境設定の読み込みに失敗しました。環境の Docker コンテナを削除できませんでした。"
)
COMPOSER_3_REQUIRES_POSTGRESQL = (
    "Composer 3 でスタンドアロン DAG プロセッサを使用するには postgresql が必要です。"
    "`--database postgresql` を使用してください。"
)
LOCAL_EXECUTOR_REQUIRES_POSTGRESQL = (
    "LocalExecutor を使用するにはスタンドアロン DAG プロセッサに postgresql が必要です。"
    "`--database postgresql` を使用してください。"
)
