import getpass
import json
import logging
import os
import pathlib
import platform
import signal
import sys
import time
from typing import Dict, List, Optional, Tuple

import docker
from docker import errors as docker_errors

from composer_local import composer_settings, console, constants, docker_ops, errors, files, utils

LOG = logging.getLogger(__name__)


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
            raise errors.FailedToParseConfigError(str(path), str(err))

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
        except docker_errors.DockerException as err:
            raise errors.DockerNotAvailableError(str(err))

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

    def start_foreground(self):
        """環境をフォアグラウンドモードで起動し、コンテナログにアタッチする。"""
        import atexit

        db, app = docker_ops.ensure_containers_running(self)

        docker_ops.wait_until_webserver_ready(
            self.port,
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
                line = log_line.decode("utf-8").rstrip()
                if not line:
                    continue
                line_upper = line.upper()
                if any(p in line_upper for p in (" ERROR ", "[ERROR]", " WARNING ", "[WARNING]")):
                    print(line)
        except (KeyboardInterrupt, BrokenPipeError, OSError, EOFError):
            stop_containers()

    def stop(self):
        app = docker_ops.get_container(self, self.container_name, ignore_not_found=True)
        if app:
            app.stop(timeout=30)
        db = docker_ops.get_container(self, self.db_container_name, ignore_not_found=True)
        if db:
            db.stop(timeout=30)

    def status(self) -> str:
        app = docker_ops.get_container(self, self.container_name, ignore_not_found=True)
        return app.status if app else "Not started"

    def logs(self, follow: bool, max_lines):
        app = docker_ops.get_container(self, self.container_name, assert_running=True)
        # assert_running=True のため存在が保証される（無ければ get_container が送出）
        assert app is not None
        stream = app.logs(timestamps=True, stream=follow, follow=follow, tail=max_lines)
        if follow:
            for line in stream:
                console.get_console().print(line.decode("utf-8").strip())  # type: ignore[union-attr]
        else:
            for line in stream.decode("utf-8").split("\n"):  # type: ignore[union-attr]
                console.get_console().print(line)

    def run_airflow_command(self, command: List, quiet: bool = False) -> None:
        app = docker_ops.get_container(self, self.container_name, assert_running=True)
        assert app is not None
        cmd = ["/home/airflow/run_as_user.sh", "airflow", *command]
        result = app.exec_run(cmd=cmd)

        if quiet:
            return

        output = result.output.decode()  # type: ignore[union-attr]
        filtered_lines = []
        for line in output.split("\n"):
            if any(phrase in line for phrase in constants.AIRFLOW_LOG_SKIP_PHRASES):
                continue
            filtered_lines.append(line)

        filtered_output = "\n".join(filtered_lines).strip()
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
            from composer_local import gcp_sync

            auth_check = gcp_sync.check_auth_validity()
            gcloud_path = utils.resolve_gcloud_config_path()
            if auth_check["is_valid"]:
                auth_status = utils.wrap_auth_status_in_color(
                    auth_check["auth_info"]["description"], True
                )
            else:
                auth_status = utils.wrap_auth_status_in_color(auth_check["error_message"], False)
        except Exception:
            auth_status = "ローカル専用モード（GCP 未設定）"
            gcloud_path = ""

        msg = utils.create_plain_status_text(
            name=self.name,
            state=env_status_colored,
            web_url=web_url,
            image_version=self.image_version,
            dags_path=str(self.dags_path),
            auth_status=auth_status,
            gcloud_path=gcloud_path,
        )
        console.get_console().print(f"\n{msg}\n{constants.FINAL_ENV_MESSAGE}")

    def remove(self, force: bool, force_error):
        for name in (self.container_name, self.db_container_name):
            c = docker_ops.get_container(self, name, ignore_not_found=True)
            if c is not None:
                if c.status == constants.ContainerStatus.RUNNING:
                    if not force:
                        raise force_error
                    c.stop(timeout=30)
                c.remove()
        net = docker_ops.get_network(self, create=False)
        if net:
            net.remove()

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

    def _run_airflow_setup_command(self, command: List, description: str) -> bool:
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
                "connections",
                "add",
                "google_cloud_default",
                "--conn-type",
                "google_cloud_platform",
                "--conn-extra",
                json.dumps(
                    {
                        "extra__google_cloud_platform__scope": "https://www.googleapis.com/auth/cloud-platform",
                    }
                ),
            ],
            description="Google Cloud 接続の設定",
        )

    def _create_admin_user(self) -> bool:
        """Admin ユーザーを作成する。成功時 True を返す。"""
        return self._run_airflow_setup_command(
            [
                "users",
                "create",
                "--role",
                "Admin",
                "--username",
                composer_settings.ADMIN_USERNAME,
                "--password",
                composer_settings.ADMIN_PASSWORD,
                "--email",
                composer_settings.ADMIN_EMAIL,
                "--firstname",
                composer_settings.ADMIN_FIRSTNAME,
                "--lastname",
                composer_settings.ADMIN_LASTNAME,
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

    def _handle_first_time_init(self):
        """初回セットアップ判定と実行。未初期化なら初期化してバナー表示。"""
        initialized_marker = self.env_dir_path / ".initialized"
        if not initialized_marker.exists():
            self._first_time_init()
            self._show_setup_banner()
        else:
            print(f"{self.name} 環境を起動しました。")
            print(f"Airflow Web UI: http://localhost:{self.port}")


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
