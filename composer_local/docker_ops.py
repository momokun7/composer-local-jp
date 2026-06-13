"""Docker コンテナ・ネットワークの操作とヘルスチェック関数群。

Environment インスタンスを第一引数 env として受け取る純粋な関数の集合。
"""

import io
import logging
import pathlib
import tarfile
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Tuple

import docker
from docker import errors as docker_errors

from composer_local import composer_settings, constants, errors, files, utils

LOG = logging.getLogger(__name__)

DOCKER_FILES = pathlib.Path(__file__).parent / "docker_files"

CONTAINER_COPY_FILES = [
    DOCKER_FILES / "entrypoint.sh",
    DOCKER_FILES / "run_as_user.sh",
    DOCKER_FILES / "webserver_config.py",
]


def get_network(env, create: bool = True):
    try:
        return env.docker_client.networks.get(env.docker_network_name)
    except docker_errors.NotFound:
        if not create:
            return None
        return env.docker_client.networks.create(env.docker_network_name)


def ensure_attached(network, container):
    existing = [c.name for c in network.containers]
    if container.name in existing:
        return
    try:
        network.connect(container)
    except docker_errors.APIError as err:
        if "already exists" not in str(err).lower():
            raise


def copy_to_container(container, src: pathlib.Path):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w|") as tar, open(src, "rb") as f:
        info = tar.gettarinfo(fileobj=f)
        info.name = src.name
        tar.addfile(info, f)
    container.put_archive(constants.AIRFLOW_HOME, stream.getvalue())


def copy_files_to_container(container) -> None:
    """CONTAINER_COPY_FILES に定義されたファイルをコンテナへコピーする。"""
    for src in CONTAINER_COPY_FILES:
        copy_to_container(container, src)


def warn_if_port_exposed(service_label: str) -> None:
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


def build_mounts(env, include_db: bool):
    """Create Docker volume mounts for the Airflow container."""
    m = {
        pathlib.Path(env.dags_path): "gcs/dags/",
        env.env_dir_path / "plugins": "gcs/plugins/",
        env.env_dir_path / "data": "gcs/data/",
        env.env_dir_path / "requirements.txt": "composer_requirements.txt",
    }
    try:
        gcloud_path = pathlib.Path(utils.resolve_gcloud_config_path())
        if gcloud_path.is_dir():
            m[gcloud_path] = ".config/gcloud"
    except errors.ComposerCliError:
        LOG.debug("gcloud config not found; skipping mount (local-only mode)")
    if include_db:
        try:
            (env.env_dir_path / "postgresql_data").mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise errors.ComposerCliError(f"PostgreSQL データディレクトリの作成に失敗: {e}")
        m[env.env_dir_path / "postgresql_data"] = "/var/lib/postgresql/data"
    mounts = []
    for src, target in m.items():
        mounts.append(
            docker.types.Mount(  # type: ignore[attr-defined]
                source=str(src),
                target=(
                    target if str(target).startswith("/") else f"{constants.AIRFLOW_HOME}/{target}"
                ),
                type="bind",
            )
        )
    return mounts


def build_db_env() -> Dict[str, str]:
    return {
        "PGDATA": "/var/lib/postgresql/data/pgdata",
        "POSTGRES_USER": composer_settings.POSTGRES_USER,
        "POSTGRES_PASSWORD": composer_settings.POSTGRES_PASSWORD,
        "POSTGRES_DB": composer_settings.POSTGRES_DB,
    }


def get_container(env, name: str, assert_running: bool = False, ignore_not_found: bool = False):
    try:
        c = env.docker_client.containers.get(name)
        if assert_running and c.status != constants.ContainerStatus.RUNNING:
            raise errors.EnvironmentNotRunningError()
        return c
    except docker_errors.NotFound:
        if ignore_not_found:
            return None
        raise errors.EnvironmentNotFoundError()


def create_db_container(env):
    warn_if_port_exposed("PostgreSQL ポート")
    env.docker_client.images.pull(composer_settings.POSTGRES_IMAGE)
    return env.docker_client.containers.create(
        image=composer_settings.POSTGRES_IMAGE,
        name=env.db_container_name,
        environment=build_db_env(),
        mounts=build_mounts(env, include_db=True),
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


def create_app_container(env):
    warn_if_port_exposed("Airflow Web サーバーのポート")
    if not composer_settings.BIND_TO_LOCALHOST_ONLY:
        # webserver_config.py で AUTH_ROLE_PUBLIC=Admin が設定されているため、
        # ポート公開時は認証なしで管理者権限のアクセスが可能になる
        LOG.warning(
            "AUTH_ROLE_PUBLIC が Admin に設定された状態でポートが外部に公開されます。"
            " 認証なしで管理者権限のアクセスが可能です。"
            " 信頼できないネットワークでの使用は避けてください。"
        )
    image_tag = env._image_tag()
    try:
        env.docker_client.images.pull(image_tag)
    except docker_errors.ImageNotFound:
        raise errors.ImageNotFoundError(env.image_version)
    except docker_errors.APIError as e:
        error_msg = str(e).lower()
        if "unauthorized" in error_msg or "denied" in error_msg:
            raise errors.ComposerCliError(
                "Docker イメージの取得に認証エラーが発生しました。\n"
                "対処: gcloud auth configure-docker us-docker.pkg.dev"
            )
        raise errors.ComposerCliError(f"Docker イメージの取得に失敗しました: {e}")
    env_vars = {**env._default_airflow_env(), **(env.environment_vars or {})}
    entrypoint = f"sh {constants.ENTRYPOINT_PATH}"
    c = env.docker_client.containers.create(
        image=image_tag,
        name=env.container_name,
        entrypoint=entrypoint,
        environment=env_vars,
        mounts=build_mounts(env, include_db=False),
        # Bind webserver to localhost only for security
        ports={
            "8080/tcp": (
                "127.0.0.1" if composer_settings.BIND_TO_LOCALHOST_ONLY else "0.0.0.0",
                env.port,
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
    copy_files_to_container(c)
    return c


def ensure_containers_running(env) -> Tuple:
    """DB・Appコンテナを起動し、(db, app) タプルを返す。"""
    env._assert_options()
    files.assert_dag_path_exists(env.dags_path)
    net = get_network(env, create=True)

    # DBコンテナの取得/作成/起動
    db = get_container(env, env.db_container_name, ignore_not_found=True) or create_db_container(
        env
    )
    if db.status != constants.ContainerStatus.RUNNING:
        db.start()
    ensure_attached(net, db)

    # DBが接続可能になるまで待機
    wait_for_db_ready(db)

    # Appコンテナの取得/作成/起動
    app = get_container(env, env.container_name, ignore_not_found=True) or create_app_container(env)
    if app.status != constants.ContainerStatus.RUNNING:
        copy_files_to_container(app)
        app.start()
    ensure_attached(net, app)

    return db, app


def poll_until_ready(
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


def wait_for_db_ready(db, timeout_seconds: int = 60, interval_seconds: int = 2) -> None:
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
                [
                    "pg_isready",
                    "-U",
                    composer_settings.POSTGRES_USER,
                    "-d",
                    composer_settings.POSTGRES_DB,
                ]
            )
            return result.exit_code == 0
        return False

    poll_until_ready(
        check_fn=_check_db,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        label="PostgreSQL の起動を待機中",
        timeout_message=(
            f"PostgreSQL が {timeout_seconds} 秒以内に起動しませんでした。"
            " Docker のメモリ割り当てを確認してください（推奨: 4GB 以上）。"
        ),
    )


def wait_until_webserver_ready(port, timeout_seconds: int, interval_seconds: int) -> None:
    url = f"http://localhost:{port}"

    def _check_webserver() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.getcode() in (200, 302)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            ConnectionResetError,
            OSError,
        ):
            return False

    poll_until_ready(
        check_fn=_check_webserver,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        label="Airflow Web サーバーを起動中",
        timeout_message=(
            f"Airflow Web サーバーが {timeout_seconds} 秒以内に起動しませんでした。"
            " ログを確認してから、もう一度お試しください。"
        ),
    )
