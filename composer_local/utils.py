import logging
import os
import pathlib
import re
import textwrap
from typing import List, Optional, Tuple

import rich.box
import rich.table
from rich.logging import RichHandler

from composer_local import constants, errors

LOG = logging.getLogger(__name__)

LOG_FORMAT = "%(name)s:%(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def is_windows_os() -> bool:
    return os.name == "nt"


def resolve_gcloud_config_path() -> str:
    if constants.CLOUD_CLI_CONFIG_PATH_ENV in os.environ:
        return os.environ[constants.CLOUD_CLI_CONFIG_PATH_ENV]

    if is_windows_os() and "APPDATA" in os.environ:
        config_path = pathlib.Path(os.environ["APPDATA"], "gcloud")
    else:
        config_path = pathlib.Path("~/.config/gcloud").expanduser()
    if config_path.is_dir():
        return str(config_path)
    raise errors.ComposerCliError(constants.GCLOUD_CONFIG_NOT_FOUND_ERROR)


def create_plain_status_text(
    name: str,
    state: str,
    web_url: str,
    image_version: str,
    dags_path: str,
    auth_status: str,
    gcloud_path: str,
    width: int = 80,
) -> str:
    """枠線なしのシンプルなステータス表示テキストを生成する。

    改行時は次行をインデントして可読性を高める。
    """
    lines: List[str] = []
    lines.append("Composer 環境情報")
    lines.append("")

    def add_item(label: str, value: str):
        if not value:
            return
        prefix = f"- {label}: "
        available = max(10, width - len(prefix))
        # 認証情報にメールアドレスが含まれる場合は、説明とアカウントを行分割
        if label == "認証情報" and ": " in value:
            head, tail = value.split(": ", 1)
            if "@" in tail:
                lines.append(prefix + head)
                indent = " " * len(prefix)
                wrapper = textwrap.TextWrapper(
                    width=width - len(prefix),
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                for cont in wrapper.wrap(tail):
                    lines.append(indent + cont)
                return
        wrapper = textwrap.TextWrapper(
            width=available,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped = wrapper.wrap(value) or [""]
        # 1行目
        lines.append(prefix + (wrapped[0] if wrapped else ""))
        # 2行目以降はラベル幅に合わせてインデント
        indent = " " * len(prefix)
        for cont in wrapped[1:]:
            lines.append(indent + cont)

    add_item("環境名", name)
    add_item("状態", state)
    add_item("Web サーバー", web_url)
    add_item("イメージバージョン", image_version)
    add_item("DAG ディレクトリ", dags_path)

    add_item("認証情報", auth_status)
    add_item("設定パス", gcloud_path)

    return "\n".join(lines)


def assert_environment_name_is_valid(env_name: str):
    if len(env_name) < 3:
        raise errors.ComposerCliError(
            constants.ENVIRONMENT_NAME_TOO_SHORT_ERROR.format(env_name=env_name)
        )
    if len(env_name) > 40:
        raise errors.ComposerCliError(
            constants.ENVIRONMENT_NAME_TOO_LONG_ERROR.format(env_name=env_name)
        )
    if re.search("[^A-Za-z0-9_-]", env_name):
        raise errors.ComposerCliError(
            constants.ENVIRONMENT_NAME_NOT_VALID_ERROR.format(env_name=env_name)
        )


def get_airflow_composer_versions(image_version: str) -> Tuple[str, str]:
    version_match = re.match(constants.IMAGE_VERSION_PATTERN, image_version)
    if not version_match:
        raise errors.ComposerCliError(constants.INVALID_IMAGE_VERSION_ERROR)
    composer_v, airflow_v = version_match.group(1), version_match.group(2)
    return airflow_v, composer_v


def get_image_version_tag(airflow_v: str, composer_v: str) -> str:
    if composer_v != "3":
        airflow_v = airflow_v.replace(".", "-")
    return f"composer-{composer_v}-airflow-{airflow_v}"


def get_environment_status_table(envs_status: List) -> rich.table.Table:
    table = rich.table.Table(box=rich.box.MINIMAL)
    for col in ("環境名", "バージョン*", "状態"):
        table.add_column(col)
    for env_status in envs_status:
        table.add_row(env_status.name, env_status.version, env_status.status)
    return table


def wrap_status_in_color(status: str) -> str:
    status_color = "green" if status == constants.ContainerStatus.RUNNING else "red"
    return f"[bold {status_color}]{status}[/]"


def wrap_auth_status_in_color(auth_description: str, is_valid: bool) -> str:
    """認証情報の状態を色付きで表示する"""
    if is_valid:
        return f"[bold green]{auth_description}[/]"
    else:
        return f"[bold red]{auth_description}[/]"


def get_log_level(verbose: bool, debug: bool):
    if debug:
        return logging.DEBUG
    if verbose:
        return logging.INFO
    return logging.WARNING


def get_external_log_level(debug: bool):
    if debug:
        return logging.DEBUG
    return logging.WARNING


def setup_logging(verbose: bool, debug: bool):
    log_level = get_log_level(verbose, debug)
    external_log_level = get_external_log_level(debug)
    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[RichHandler()],
    )
    logging.captureWarnings(True)
    logging.getLogger("docker").setLevel(external_log_level)
    logging.getLogger("urllib3").setLevel(external_log_level)


def resolve_project_id(project_id: Optional[str]) -> str:
    if project_id is not None:
        return project_id
    return "local-dev"
