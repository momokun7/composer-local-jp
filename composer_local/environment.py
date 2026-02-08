import getpass
import io
import json
import logging
import os
import pathlib
import platform
import signal
import sys
import tarfile
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Tuple

import docker
from docker import errors as docker_errors

from composer_local import composer_settings, console, constants, errors, files, utils

LOG = logging.getLogger(__name__)
DOCKER_FILES = pathlib.Path(__file__).parent / "docker_files"

# コンテナにコピーするファイル一覧
CONTAINER_COPY_FILES: List[pathlib.Path] = [
    DOCKER_FILES / "entrypoint.sh",
    DOCKER_FILES / "run_as_user.sh",
    DOCKER_FILES / "webserver_config.py",
]


class EnvironmentStatus:
    def __init__(self, name: str, version: str, status: str):
        self.name = name
        self.version = version
        self.status = status.capitalize()


class EnvironmentConfig:
    def __init__(self, env_dir_path: pathlib.Path, port: Optional[int]):
        self.env_dir_path = env_dir_path
        self.config = self._load()
        self.project_id = self._get_str("composer_project_id")
        self.image_version = self._get_str("composer_image_version")
        self.location = self._get_str("composer_location")
        self.dags_path = self._get_str("dags_path")
        self.dag_dir_list_interval = self._get_int("dag_dir_list_interval", (0,))
        self.port = self._resolve_port(port)
        self.database_engine = self._get_str("database_engine")

    def _load(self) -> Dict:
        path = self.env_dir_path / "config.json"
        if not path.is_file():
            raise errors.ComposerCliError(f"設定ファイル '{path}' が見つかりません。")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as err:
            raise errors.FailedToParseConfigError(path, err)

    def _get_str(self, name: str):
        try:
            return self.config[name]
        except KeyError:
            raise errors.MissingRequiredParameterError(name)

    def _get_int(self, name: str, allowed_range: Tuple[int, ...]):
        try:
            value = int(self._get_str(name))
        except ValueError:
            raise errors.FailedToParseConfigParamIntError(name, str(self.config.get(name)))
        if allowed_range and (
            value < allowed_range[0] or (len(allowed_range) > 1 and value > allowed_range[1])
        ):
            raise errors.FailedToParseConfigParamIntRangeError(name, value, allowed_range)
        return value

    def _resolve_port(self, port: Optional[int]) -> int:
        """ポート番号を解決する。

        解決順序:
        1. 引数 port が明示的に指定されていればそれを使う
        2. config.json に "port" キーがあればそれを使う
        3. どちらもなければ composer_settings.LOCAL_PORT をデフォルトとして使う
        """
        if port is not None:
            return port
        if "port" in self.config:
            return self._get_int("port", (0, 65536))
        return composer_settings.LOCAL_PORT


class Environment:
    def __init__(
        self,
        env_dir_path: pathlib.Path,
        project_id: str,
        image_version: str,
        location: str,
        dags_path: Optional[str],
        dag_dir_list_interval: int = 10,
        database_engine: str = constants.DatabaseEngine.postgresql,
        port: Optional[int] = None,
        pypi_packages: Optional[Dict] = None,
        environment_vars: Optional[Dict] = None,
    ):
        """Environment を初期化する。

        Args:
            env_dir_path: 環境ディレクトリのパス。
            project_id: GCP プロジェクト ID。
            image_version: Composer イメージバージョン文字列。
            location: GCP リージョン。
            dags_path: DAG ディレクトリのパス。
            dag_dir_list_interval: DAG ディレクトリの再読み込み間隔（秒）。
            database_engine: データベースエンジン種別。
                ``constants.DatabaseEngine`` enum の値
                (``"postgresql"`` または ``"sqlite3"``) を文字列で受け取る。
            port: Airflow Web UI のポート番号。
            pypi_packages: 追加でインストールする PyPI パッケージの辞書。
            environment_vars: Airflow に渡す追加の環境変数の辞書。
        """
        self.name = env_dir_path.name
        self.container_name = f"{constants.CONTAINER_NAME}-{self.name}"
        self.db_container_name = f"{constants.DB_CONTAINER_NAME}-{self.name}"
        self.docker_network_name = f"{constants.DOCKER_NETWORK_NAME}-{self.name}"
        self.env_dir_path = env_dir_path
        self.project_id = project_id
        self.image_version = image_version
        self.location = location
        self.dags_path = files.resolve_dags_path(dags_path, env_dir_path)
        self.dag_dir_list_interval = dag_dir_list_interval
        self.database_engine = database_engine
        self.port: int = port if port is not None else composer_settings.LOCAL_PORT
        self.pypi_packages = pypi_packages or {}
        self.environment_vars = environment_vars or {}
        self.docker_client = self._get_client()

    def _get_client(self):
        try:
            return docker.from_env()
        except docker.errors.DockerException as err:
            raise errors.DockerNotAvailableError(err)

    def _image_tag(self) -> str:
        airflow_v, composer_v = utils.get_airflow_composer_versions(self.image_version)
        dashed_airflow_v = airflow_v.replace(".", "-").split("-build")[0]
        return constants.DOCKER_REGISTRY_IMAGE_TAG.format(
            dashed_airflow_v=dashed_airflow_v,
            composer_v=composer_v,
            image_tag=utils.get_image_version_tag(airflow_v, composer_v),
        )

    def _assert_options(self):
        if (
            self.image_version.startswith("composer-3")
            and self.database_engine == constants.DatabaseEngine.sqlite3
        ):
            raise errors.InvalidConfigurationError(constants.COMPOSER_3_REQUIRES_POSTGRESQL)

    def _write_config(self):
        cfg = {
            "composer_image_version": self.image_version,
            "composer_location": self.location,
            "composer_project_id": self.project_id,
            "dags_path": self.dags_path,
            "dag_dir_list_interval": int(self.dag_dir_list_interval),
            "port": int(self.port),
            "database_engine": self.database_engine,
        }
        (self.env_dir_path / "config.json").write_text(json.dumps(cfg, indent=4))

    def _write_requirements(self):
        essential_packages = {
            "apache-airflow-providers-google": "",
        }
        all_packages = {**essential_packages, **self.pypi_packages}
        reqs = "\n".join(sorted(f"{k}{v}" for k, v in all_packages.items()))
        (self.env_dir_path / "requirements.txt").write_text(reqs)

    def _write_variables(self):
        env_vars = "\n".join(sorted(f"# {k}=" for k in self.environment_vars.keys()))
        (self.env_dir_path / "variables.env").write_text(env_vars)

    def create(self):
        files.create_environment_directories(self.env_dir_path, self.dags_path)
        self._assert_options()
        self._write_config()
        self._write_requirements()
        self._write_variables()
        console.get_console().print(
            constants.CREATE_MESSAGE.format(
                env_dir=self.env_dir_path,
                env_name=self.name,
                config_path=self.env_dir_path / "config.json",
                requirements_path=self.env_dir_path / "requirements.txt",
                env_variables_path=self.env_dir_path / "variables.env",
                dags_path=self.dags_path,
            )
        )

    @classmethod
    def load_from_config(cls, env_dir_path: pathlib.Path, port: Optional[int]):
        cfg = EnvironmentConfig(env_dir_path, port)
        return cls(
            env_dir_path=env_dir_path,
            project_id=cfg.project_id,
            image_version=cfg.image_version,
            location=cfg.location,
            dags_path=cfg.dags_path,
            dag_dir_list_interval=cfg.dag_dir_list_interval,
            port=cfg.port,
            database_engine=cfg.database_engine,
        )

    @classmethod
    def from_source_environment(
        cls,
        source_environment: str,
        project: str,
        location: str,
        env_dir_path: pathlib.Path,
        web_server_port: Optional[int],
        dags_path: Optional[str],
        database_engine: str,
    ):
        # Simplified: do not call Composer API here.
        return cls(
            env_dir_path=env_dir_path,
            project_id=project,
            image_version=composer_settings.COMPOSER_IMAGE_VERSION,
            location=location,
            dags_path=dags_path,
            dag_dir_list_interval=10,
            port=web_server_port,
            database_engine=database_engine,
        )

    def _network(self, create: bool = True):
        try:
            return self.docker_client.networks.get(self.docker_network_name)
        except docker_errors.NotFound:
            if not create:
                return None
            return self.docker_client.networks.create(self.docker_network_name)

    def _ensure_attached(self, network, container):
        existing = [c.name for c in network.containers]
        if container.name in existing:
            return
        try:
            network.connect(container)
        except docker_errors.APIError as err:
            if "already exists" not in str(err).lower():
                raise

    def _copy_to_container(self, container, src: pathlib.Path):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w|") as tar, open(src, "rb") as f:
            info = tar.gettarinfo(fileobj=f)
            info.name = src.name
            tar.addfile(info, f)
        container.put_archive(constants.AIRFLOW_HOME, stream.getvalue())

    def _copy_files_to_container(self, container) -> None:
        """CONTAINER_COPY_FILES に定義されたファイルをコンテナへコピーする。"""
        for src in CONTAINER_COPY_FILES:
            self._copy_to_container(container, src)

    def _warn_if_port_exposed(self, service_label: str) -> None:
        """BIND_TO_LOCALHOST_ONLY が False の場合にセキュリティ警告をログ出力する。

        Args:
            service_label: 警告メッセージに含めるサービス名（例: "PostgreSQL ポート"）。
        """
        if not composer_settings.BIND_TO_LOCALHOST_ONLY:
            LOG.warning(
                "BIND_TO_LOCALHOST_ONLY が False に設定されています。"
                f" {service_label}が外部ネットワークに公開されます。"
                " セキュリティリスクを理解した上で使用してください。"
            )

    def _poll_until_ready(
        self,
        check_fn: Callable[[], bool],
        timeout_seconds: int,
        interval_seconds: int,
        label: str,
        timeout_message: str,
    ) -> None:
        """check_fn が True を返すまでポーリングする汎用ヘルパー。

        Args:
            check_fn: 準備完了時に True を返すコールバック。
            timeout_seconds: タイムアウトまでの秒数。
            interval_seconds: ポーリング間隔（秒）。
            label: 待機中に表示するラベル文字列。
            timeout_message: タイムアウト時に ComposerCliError に渡すメッセージ。
        """
        start_time = time.time()
        print(f"{label}", end="", flush=True)
        while True:
            if check_fn():
                print(" 起動完了")
                return
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                print(" タイムアウト")
                raise errors.ComposerCliError(timeout_message)
            print(".", end="", flush=True)
            time.sleep(interval_seconds)

    def _mounts(self, include_db: bool):
        """Create Docker volume mounts for the Airflow container."""
        m = {
            pathlib.Path(self.dags_path): "gcs/dags/",
            self.env_dir_path / "plugins": "gcs/plugins/",
            self.env_dir_path / "data": "gcs/data/",
            self.env_dir_path / "requirements.txt": "composer_requirements.txt",
        }
        try:
            gcloud_path = pathlib.Path(utils.resolve_gcloud_config_path())
            if gcloud_path.is_dir():
                m[gcloud_path] = ".config/gcloud"
        except errors.ComposerCliError:
            LOG.debug("gcloud config not found; skipping mount (local-only mode)")
        if include_db:
            try:
                (self.env_dir_path / "postgresql_data").mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise errors.ComposerCliError(f"PostgreSQL データディレクトリの作成に失敗: {e}")
            m[self.env_dir_path / "postgresql_data"] = "/var/lib/postgresql/data"
        mounts = []
        for src, target in m.items():
            mounts.append(
                docker.types.Mount(
                    source=str(src),
                    target=(
                        target
                        if str(target).startswith("/")
                        else f"{constants.AIRFLOW_HOME}/{target}"
                    ),
                    type="bind",
                )
            )
        return mounts

    def _db_env(self) -> Dict[str, str]:
        return {
            "PGDATA": "/var/lib/postgresql/data/pgdata",
            "POSTGRES_USER": composer_settings.POSTGRES_USER,
            "POSTGRES_PASSWORD": composer_settings.POSTGRES_PASSWORD,
            "POSTGRES_DB": composer_settings.POSTGRES_DB,
        }

    def _default_airflow_env(self) -> Dict[str, str]:
        """Return default Airflow environment variables for local development."""
        return {
            "AIRFLOW__API__AUTH_BACKEND": "airflow.api.auth.backend.default",
            "AIRFLOW__CORE__DAGS_FOLDER": "/home/airflow/gcs/dags",
            "AIRFLOW__CORE__DATA_FOLDER": "/home/airflow/gcs/data",
            "AIRFLOW__CORE__LOAD_EXAMPLES": "false",
            "AIRFLOW__CORE__PLUGINS_FOLDER": "/home/airflow/gcs/plugins",
            "AIRFLOW_HOME": "/home/airflow/airflow",
            "AIRFLOW__LOGGING__LOGGING_LEVEL": "INFO",
            "AIRFLOW__LOGGING__FAB_LOGGING_LEVEL": "WARN",
            "PYTHONWARNINGS": "ignore::Warning",
            "AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL": str(self.dag_dir_list_interval),
            "AIRFLOW__SCHEDULER__STANDALONE_DAG_PROCESSOR": str(
                self.image_version.startswith("composer-3")
            ),
            "AIRFLOW__WEBSERVER__EXPOSE_CONFIG": "true",
            "AIRFLOW__WEBSERVER__RELOAD_ON_PLUGIN_CHANGE": "True",
            "AIRFLOW__WEBSERVER__WEB_SERVER_NAME": "Airflow [LOCAL]",
            "AIRFLOW__WEBSERVER__BASE_URL": f"http://localhost:{self.port}",
            "AIRFLOW__WEBSERVER__NAVBAR_COLOR": "#e4007f",
            "AIRFLOW__WEBSERVER__SHOW_TRIGGER_FORM_IF_NO_PARAMS": "True",
            "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": (
                f"postgresql+psycopg2://{composer_settings.POSTGRES_USER}:"
                f"{composer_settings.POSTGRES_PASSWORD}@{self.db_container_name}:"
                f"{composer_settings.POSTGRES_PORT}/{composer_settings.POSTGRES_DB}"
            ),
            "COMPOSER_IMAGE_VERSION": self.image_version,
            "COMPOSER_PYTHON_VERSION": composer_settings.COMPOSER_PYTHON_VERSION,
            "COMPOSER_CONTAINER_RUN_AS_HOST_USER": "False",
            "COMPOSER_HOST_USER_NAME": f"{getpass.getuser()}",
            "COMPOSER_HOST_USER_ID": f"{os.getuid() if platform.system() != 'Windows' else ''}",
        }

    def _get_container(
        self, name: str, assert_running: bool = False, ignore_not_found: bool = False
    ):
        try:
            c = self.docker_client.containers.get(name)
            if assert_running and c.status != constants.ContainerStatus.RUNNING:
                raise errors.EnvironmentNotRunningError()
            return c
        except docker_errors.NotFound:
            if ignore_not_found:
                return None
            raise errors.EnvironmentNotFoundError()

    def _create_db(self):
        self._warn_if_port_exposed("PostgreSQL ポート")
        self.docker_client.images.pull(composer_settings.POSTGRES_IMAGE)
        return self.docker_client.containers.create(
            image=composer_settings.POSTGRES_IMAGE,
            name=self.db_container_name,
            environment=self._db_env(),
            mounts=self._mounts(include_db=True),
            ports={
                f"{composer_settings.POSTGRES_PORT}/tcp": (
                    "127.0.0.1" if composer_settings.BIND_TO_LOCALHOST_ONLY else "0.0.0.0",
                    composer_settings.POSTGRES_LOCAL_PORT,
                )
            },
            healthcheck={
                "Test": [
                    "CMD-SHELL",
                    f"pg_isready -U {composer_settings.POSTGRES_USER} "
                    f"-d {composer_settings.POSTGRES_DB}",
                ],
                "Interval": constants.HEALTHCHECK_INTERVAL_NS,
                "Timeout": constants.HEALTHCHECK_TIMEOUT_NS,
                "Retries": constants.HEALTHCHECK_RETRIES,
                "StartPeriod": constants.HEALTHCHECK_START_PERIOD_DB_NS,
            },
            mem_limit=composer_settings.DOCKER_MEMORY_LIMIT,
            detach=True,
        )

    def _create_app(self):
        self._warn_if_port_exposed("Airflow Web サーバーのポート")
        if not composer_settings.BIND_TO_LOCALHOST_ONLY:
            # webserver_config.py で AUTH_ROLE_PUBLIC=Admin が設定されているため、
            # ポート公開時は認証なしで管理者権限のアクセスが可能になる
            LOG.warning(
                "AUTH_ROLE_PUBLIC が Admin に設定された状態でポートが外部に公開されます。"
                " 認証なしで管理者権限のアクセスが可能です。"
                " 信頼できないネットワークでの使用は避けてください。"
            )
        image_tag = self._image_tag()
        try:
            self.docker_client.images.pull(image_tag)
        except docker_errors.ImageNotFound:
            raise errors.ImageNotFoundError(self.image_version)
        except docker_errors.APIError as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "denied" in error_msg:
                raise errors.ComposerCliError(
                    f"Docker イメージの取得に認証エラーが発生しました。\n"
                    f"対処: gcloud auth configure-docker us-docker.pkg.dev"
                )
            raise errors.ComposerCliError(f"Docker イメージの取得に失敗しました: {e}")
        env_vars = {**self._default_airflow_env(), **(self.environment_vars or {})}
        entrypoint = f"sh {constants.ENTRYPOINT_PATH}"
        c = self.docker_client.containers.create(
            image=image_tag,
            name=self.container_name,
            entrypoint=entrypoint,
            environment=env_vars,
            mounts=self._mounts(include_db=False),
            # Bind webserver to localhost only for security
            ports={
                "8080/tcp": (
                    "127.0.0.1" if composer_settings.BIND_TO_LOCALHOST_ONLY else "0.0.0.0",
                    self.port,
                )
            },
            healthcheck={
                "Test": [
                    "CMD-SHELL",
                    "curl -f http://localhost:8080/health || exit 1",
                ],
                "Interval": constants.HEALTHCHECK_INTERVAL_NS,
                "Timeout": constants.HEALTHCHECK_TIMEOUT_NS,
                "Retries": constants.HEALTHCHECK_RETRIES,
                "StartPeriod": constants.HEALTHCHECK_START_PERIOD_APP_NS,
            },
            mem_limit=composer_settings.DOCKER_MEMORY_LIMIT,
            detach=True,
        )
        self._copy_files_to_container(c)
        return c

    def _auto_import_variables(self):
        """variables.json が存在すれば Airflow にインポートし、インポート後に削除する。"""
        variables_json_path = self.env_dir_path / "data" / "variables.json"
        if variables_json_path.is_file():
            self.run_airflow_command(
                ["variables", "import", "/home/airflow/gcs/data/variables.json"]
            )
            try:
                variables_json_path.unlink()
            except Exception as e:
                LOG.warning(f"一時ファイル削除失敗: {e}")

    def _wait_for_db_ready(self, db, timeout_seconds: int = 60, interval_seconds: int = 2) -> None:
        """PostgreSQL コンテナが接続可能になるまで待機する。

        Docker ヘルスチェックのステータスを確認し、healthy になるまでポーリングする。
        ヘルスチェックが設定されていない場合は pg_isready コマンドで直接確認する。
        """

        def _check_db() -> bool:
            db.reload()
            health = db.attrs.get("State", {}).get("Health", {}).get("Status")
            if health == "healthy":
                return True
            # ヘルスチェック未設定の場合は exec で直接確認する
            if health is None:
                result = db.exec_run(
                    ["pg_isready", "-U", composer_settings.POSTGRES_USER,
                     "-d", composer_settings.POSTGRES_DB]
                )
                return result.exit_code == 0
            return False

        self._poll_until_ready(
            check_fn=_check_db,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            label="PostgreSQL の起動を待機中",
            timeout_message=(
                f"PostgreSQL が {timeout_seconds} 秒以内に起動しませんでした。"
                " Docker のメモリ割り当てを確認してください（推奨: 4GB 以上）。"
            ),
        )

    def _ensure_containers_running(self) -> Tuple:
        """DB・Appコンテナを起動し、(db, app) タプルを返す。"""
        self._assert_options()
        files.assert_dag_path_exists(self.dags_path)
        net = self._network(create=True)

        # DBコンテナの取得/作成/起動
        db = self._get_container(self.db_container_name, ignore_not_found=True) or self._create_db()
        if db.status != constants.ContainerStatus.RUNNING:
            db.start()
        self._ensure_attached(net, db)

        # DBが接続可能になるまで待機
        self._wait_for_db_ready(db)

        # Appコンテナの取得/作成/起動
        app = self._get_container(self.container_name, ignore_not_found=True) or self._create_app()
        if app.status != constants.ContainerStatus.RUNNING:
            self._copy_files_to_container(app)
            app.start()
        self._ensure_attached(net, app)

        return db, app

    def _handle_first_time_init(self):
        """初回セットアップ判定と実行。未初期化なら初期化してバナー表示。"""
        initialized_marker = self.env_dir_path / ".initialized"
        if not initialized_marker.exists():
            self._first_time_init()
            self._show_setup_banner()
        else:
            print(f"{self.name} 環境を起動しました。")
            print(f"Airflow Web UI: http://localhost:{self.port}")

    def start(self):
        """既存環境をバックグラウンドで起動（再起動用）。"""
        self._ensure_containers_running()

        self._wait_until_webserver_ready(
            timeout_seconds=composer_settings.WEBSERVER_TIMEOUT,
            interval_seconds=composer_settings.WEBSERVER_CHECK_INTERVAL,
        )

        print(f"{self.name} 環境を起動しました。")

    def _run_airflow_setup_command(self, command, description: str) -> bool:
        """Airflow セットアップコマンドを実行するヘルパー。成功時 True を返す。"""
        try:
            self.run_airflow_command(command, quiet=True)
            return True
        except Exception:
            LOG.debug(f"{description}に失敗しました", exc_info=True)
            return False

    def _setup_google_connection(self) -> bool:
        """Google Cloud のデフォルト接続を設定する。成功時 True を返す。"""
        return self._run_airflow_setup_command(
            [
                "connections", "add",
                "google_cloud_default",
                "--conn-type", "google_cloud_platform",
                "--conn-extra", json.dumps({
                    "extra__google_cloud_platform__scope":
                        "https://www.googleapis.com/auth/cloud-platform",
                }),
            ],
            description="Google Cloud 接続の設定",
        )

    def _create_admin_user(self) -> bool:
        """Admin ユーザーを作成する。成功時 True を返す。"""
        return self._run_airflow_setup_command(
            [
                "users", "create",
                "--role", "Admin",
                "--username", composer_settings.ADMIN_USERNAME,
                "--password", composer_settings.ADMIN_PASSWORD,
                "--email", composer_settings.ADMIN_EMAIL,
                "--firstname", composer_settings.ADMIN_FIRSTNAME,
                "--lastname", composer_settings.ADMIN_LASTNAME,
            ],
            description="Admin ユーザーの作成",
        )

    def _first_time_init(self):
        """初回起動時の自動セットアップを実行する。"""
        print(f"{constants.ANSI_BLUE}初回セットアップを実行しています...{constants.ANSI_RESET}")

        gcp_ok = self._setup_google_connection()
        admin_ok = self._create_admin_user()

        if not gcp_ok:
            print("⚠ Google Cloud 接続の設定をスキップしました（GCP未設定の場合は正常です）")
        if not admin_ok:
            print("⚠ Admin ユーザーの作成をスキップしました（既に存在する場合は正常です）")

        (self.env_dir_path / ".initialized").touch()

    def _show_setup_banner(self):
        """初回セットアップ完了バナーを表示する。"""
        P = "\033[38;5;197m"
        P2 = "\033[38;5;163m"
        P3 = "\033[38;5;164m"
        P4 = "\033[38;5;165m"
        P5 = "\033[38;5;201m"
        P6 = "\033[38;5;200m"
        Y = "\033[1;33m"
        G = "\033[1;32m"
        C = "\033[1;36m"
        R = "\033[0m"

        print()
        print(f"{Y}=========================================={R}")
        print(f"{Y}   セットアップが完了しました！{R}")
        print(f"{Y}=========================================={R}")
        print()
        print(f"{P}  ██████╗ ██████╗ ███╗   ███╗██████╗  ███████╗███████╗██████╗ {R}")
        print(f"{P2} ██╔════╝██╔═══██╗████╗ ████║██╔══██╗██╔════╝██╔════╝██╔══██╗{R}")
        print(f"{P3} ██║     ██║   ██║██╔████╔██║██████╔╝███████╗█████╗  ██████╔╝{R}")
        print(f"{P4} ██║     ██║   ██║██║╚██╔╝██║██╔═══╝ ╚════██║██╔══╝  ██╔══██╗{R}")
        print(f"{P5} ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║     ███████║███████╗██║  ██║{R}")
        print(f"{P6}  ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝{R}")
        print()
        print(f"{P}  ██╗      ██████╗  ██████╗ █████╗ ██╗     {R}")
        print(f"{P2} ██║     ██╔═══██╗██╔════╝██╔══██╗██║     {R}")
        print(f"{P3} ██║     ██║   ██║██║     ███████║██║     {R}")
        print(f"{P4} ██║     ██║   ██║██║     ██╔══██║██║     {R}")
        print(f"{P5} ███████╗╚██████╔╝╚██████╗██║  ██║███████╗{R}")
        print(f"{P6} ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚══════╝{R}")
        print()
        print(f"{P}       ██╗██████╗ {R}")
        print(f"{P2}      ██║██╔══██╗{R}")
        print(f"{P3}      ██║██████╔╝{R}")
        print(f"{P2} ██   ██║██╔═══╝ {R}")
        print(f"{P5}  ╚████╔╝██║     {R}")
        print(f"{P6}   ╚═══╝ ╚═╝     {R}")
        print()
        print(f"{G} Airflow Web UI:{R}  {C}http://localhost:{self.port}{R}")
        print()
        print(f"{Y}=========================================={R}")
        print()

    def start_foreground(self):
        """環境をフォアグラウンドモードで起動し、コンテナログにアタッチする。"""
        import atexit

        db, app = self._ensure_containers_running()

        self._wait_until_webserver_ready(
            timeout_seconds=composer_settings.WEBSERVER_TIMEOUT,
            interval_seconds=composer_settings.WEBSERVER_CHECK_INTERVAL,
        )

        self._auto_import_variables()

        self._handle_first_time_init()

        print("Ctrl+C で停止します...")

        stopped = False
        def stop_containers():
            nonlocal stopped
            if stopped:
                return
            stopped = True
            print(f"\n{self.name} 環境を停止しています...")
            try:
                app.stop(timeout=30)
                db.stop(timeout=30)
            except Exception as e:
                LOG.warning(f"コンテナ停止中にエラー: {e}")
            print(f"{self.name} 環境が停止しました。")

        signal.signal(signal.SIGINT, lambda *_: (stop_containers(), sys.exit(0)))
        signal.signal(signal.SIGTERM, lambda *_: (stop_containers(), sys.exit(0)))
        signal.signal(signal.SIGHUP, lambda *_: (stop_containers(), sys.exit(0)))
        atexit.register(stop_containers)

        try:
            now = int(time.time())
            for log_line in app.logs(stream=True, follow=True, since=now):
                line = log_line.decode('utf-8').rstrip()
                if not line:
                    continue
                line_upper = line.upper()
                if any(p in line_upper for p in (' ERROR ', '[ERROR]', ' WARNING ', '[WARNING]')):
                    print(line)
        except (KeyboardInterrupt, BrokenPipeError, OSError, EOFError):
            stop_containers()

    def resume_env(self):
        """停止中の環境を再開する。"""
        self._ensure_containers_running()

        self._wait_until_webserver_ready(
            timeout_seconds=composer_settings.WEBSERVER_TIMEOUT,
            interval_seconds=composer_settings.WEBSERVER_CHECK_INTERVAL,
        )

        self._handle_first_time_init()

    def _wait_until_webserver_ready(self, timeout_seconds: int, interval_seconds: int) -> None:
        url = f"http://localhost:{self.port}"

        def _check_webserver() -> bool:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    return resp.getcode() in (200, 302)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionResetError, OSError):
                return False

        self._poll_until_ready(
            check_fn=_check_webserver,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
            label="Airflow Web サーバーを起動中",
            timeout_message=(
                f"Airflow Web サーバーが {timeout_seconds} 秒以内に起動しませんでした。"
                " ログを確認してから、もう一度お試しください。"
            ),
        )

    def stop(self):
        app = self._get_container(self.container_name, ignore_not_found=True)
        if app:
            app.stop(timeout=30)
        db = self._get_container(self.db_container_name, ignore_not_found=True)
        if db:
            db.stop(timeout=30)

    def restart(self):
        self.stop()
        self.start()

    def status(self) -> str:
        app = self._get_container(self.container_name, ignore_not_found=True)
        return app.status if app else "Not started"

    def logs(self, follow: bool, max_lines):
        app = self._get_container(self.container_name, assert_running=True)
        stream = app.logs(timestamps=True, stream=follow, follow=follow, tail=max_lines)
        if follow:
            for line in stream:
                console.get_console().print(line.decode("utf-8").strip())
        else:
            for line in stream.decode("utf-8").split("\n"):
                console.get_console().print(line)

    def run_airflow_command(self, command: List, quiet: bool = False) -> None:
        app = self._get_container(self.container_name, assert_running=True)
        cmd = ["/home/airflow/run_as_user.sh", "airflow", *command]
        result = app.exec_run(cmd=cmd)

        if quiet:
            return

        output = result.output.decode()
        filtered_lines = []
        for line in output.split('\n'):
            if any(phrase in line for phrase in constants.AIRFLOW_LOG_SKIP_PHRASES):
                continue
            filtered_lines.append(line)

        filtered_output = '\n'.join(filtered_lines).strip()
        if filtered_output:
            console.get_console().print(filtered_output)

    def describe(self) -> None:
        env_status = self.status()
        web_url = (
            f"http://localhost:{self.port}"
            if env_status == constants.ContainerStatus.RUNNING
            else ""
        )
        env_status_colored = utils.wrap_status_in_color(env_status)

        try:
            auth_info = utils.get_auth_info()
            gcloud_path = utils.resolve_gcloud_config_path()
        except (errors.ComposerCliError, Exception):
            auth_info = {"description": "ローカル専用モード（GCP 未設定）"}
            gcloud_path = ""

        msg = utils.create_plain_status_text(
            name=self.name,
            state=env_status_colored,
            web_url=web_url,
            image_version=self.image_version,
            dags_path=str(self.dags_path),
            auth_description=auth_info["description"],
            gcloud_path=gcloud_path,
        )
        console.get_console().print(f"\n{msg}\n{constants.FINAL_ENV_MESSAGE}")

    def remove(self, force: bool, force_error):
        for name in (self.container_name, self.db_container_name):
            c = self._get_container(name, ignore_not_found=True)
            if c is not None:
                if c.status == constants.ContainerStatus.RUNNING:
                    if not force:
                        raise force_error
                    c.stop(timeout=30)
                c.remove()
        net = self._network(create=False)
        if net:
            net.remove()


def get_environments_status(envs: List[pathlib.Path]) -> List[EnvironmentStatus]:
    out: List[EnvironmentStatus] = []
    for env_path in envs:
        try:
            env = Environment.load_from_config(env_path, None)
            status = env.status()
            version = env.image_version
        except errors.InvalidConfigurationError:
            status = "設定の解析に失敗"
            version = "x"
        out.append(EnvironmentStatus(env_path.name, version, status))
    return out
