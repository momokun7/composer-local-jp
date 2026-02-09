"""Docker コンテナ・ネットワーク・ボリュームの作成・管理を担うミックスイン。

Environment クラスに Docker リソース管理の責務を提供する。
"""

import io
import logging
import pathlib
import tarfile
from typing import Dict, List, Tuple

import docker
from docker import errors as docker_errors

from composer_local import composer_settings, constants, errors, utils

LOG = logging.getLogger(__name__)

DOCKER_FILES = pathlib.Path(__file__).parent / "docker_files"

# コンテナにコピーするファイル一覧
CONTAINER_COPY_FILES: List[pathlib.Path] = [
    DOCKER_FILES / "entrypoint.sh",
    DOCKER_FILES / "run_as_user.sh",
    DOCKER_FILES / "webserver_config.py",
]


class DockerManagerMixin:
    """Docker コンテナ・ネットワーク・ボリュームの管理を行うミックスイン。"""

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
                    "Docker イメージの取得に認証エラーが発生しました。\n"
                    "対処: gcloud auth configure-docker us-docker.pkg.dev"
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

    def _ensure_containers_running(self) -> Tuple:
        """DB・Appコンテナを起動し、(db, app) タプルを返す。"""
        self._assert_options()
        from composer_local import files
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
