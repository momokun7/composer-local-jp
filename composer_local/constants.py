import enum

CLOUD_CLI_CONFIG_PATH_ENV = "CLOUDSDK_CONFIG"


class ContainerStatus(str, enum.Enum):
    RUNNING = "running"
    CREATED = "created"


class DatabaseEngine(str, enum.Enum):
    sqlite3 = "sqlite3"
    postgresql = "postgresql"

    @classmethod
    def choices(cls):
        return [e.value for e in cls]


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

ANSI_RED = "\033[0;31m"
ANSI_GREEN = "\033[0;32m"
ANSI_YELLOW = "\033[0;33m"
ANSI_BLUE = "\033[0;34m"
ANSI_CYAN = "\033[1;36m"
ANSI_GRAY = "\033[90m"
ANSI_RESET = "\033[0m"

# Airflow コマンド実行時にフィルタリングするログメッセージ
AIRFLOW_LOG_SKIP_PHRASES = [
    "WARNING - empty cryptography key",
    "Optional provider feature disabled",
    "exec airflow variables import",
    "variables successfully updated",
    "Airflow Variables のインポートが完了しました",
]

AIRFLOW_HOME = "/home/airflow"
ENTRYPOINT_PATH = f"{AIRFLOW_HOME}/entrypoint.sh"

CREATE_MESSAGE = (
    "\n"
    "環境ディレクトリ:\n"
    "{env_dir}\n"
    "\n"
    "設定ファイル:\n"
    "• 一般設定:{config_path}\n"
    "• PyPI パッケージ:{requirements_path}\n"
    "• 環境変数:{env_variables_path}\n"
    "\n"
    "ディレクトリ構成:\n"
    "• プラグイン:{env_dir}/plugins\n"
    "• データ:{env_dir}/data\n"
    "• DAG:{dags_path}\n"
    "\n"
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
ENVIRONMENT_DIR_NOT_FOUND_ERROR = (
    "'{env_dir}' ディレクトリが見つかりません。「make start」で環境を作成できます。"
)
ENVIRONMENT_DIR_EMPTY_ERROR = (
    "'{env_dir}' に環境が見つかりません。「make start」で環境を作成できます。"
)
ENVIRONMENTS_NOT_FOUND = "指定のパスに環境が見つかりませんでした: {path}"
ENVIRONMENTS_FOUND = "次のローカル Composer 環境が見つかりました: {path}\n"
ENVIRONMENT_PATH_NOT_FOUND_ERROR = (
    "'{env_path}' ディレクトリが見つかりません。"
    "環境名が正しいか、環境が存在するかを確認してください。「make start」で環境を作成できます。"
)
ENVIRONMENT_NOT_SELECTED_ERROR = (
    "'{env_dir}' には複数の環境が存在しますが、環境名が指定されていません。\n"
    "既存のいずれかの環境を選択するため、引数に環境名を指定してください:\n    {env_names}"
)
GCLOUD_CONFIG_NOT_FOUND_ERROR = (
    "gcloud の設定場所を解決できませんでした。CLOUDSDK_CONFIG 環境変数で上書きしてください。"
)
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
DOCKER_NOT_AVAILABLE_ERROR = (
    "Docker が利用できないか起動に失敗しました。"
    "Docker サービスがインストール済みで起動していることを確認してください。"
    "エラー: {error}"
)
LIST_COMMAND_EPILOG = (
    "\n詳細情報や潜在的な設定エラーを確認するには、"
    "環境名を指定して describe コマンドを実行してください。\n\n"
    "* 表示内容は環境設定ファイルの情報に基づきます。"
)
REMOVE_ENV_CONFIRMATION_PROMPT = (
    "この操作はディレクトリ '{env_path}' とその配下の全て（data/plugins/dags）を削除します。"
    "Docker イメージは削除されません。"
)
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

# Docker ヘルスチェック設定（ナノ秒）
HEALTHCHECK_INTERVAL_NS = 5_000_000_000  # 5秒
HEALTHCHECK_TIMEOUT_NS = 5_000_000_000  # 5秒
HEALTHCHECK_RETRIES = 5
HEALTHCHECK_START_PERIOD_DB_NS = 10_000_000_000  # 10秒
HEALTHCHECK_START_PERIOD_APP_NS = 30_000_000_000  # 30秒
