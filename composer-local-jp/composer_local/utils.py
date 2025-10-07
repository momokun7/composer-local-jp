import json
import logging
import os
import pathlib
import re
import subprocess
import textwrap
from typing import Any, Dict, List, Optional, Tuple

import click
import rich.box
import rich.table
from rich.logging import RichHandler

from composer_local import constants, errors

LOG = logging.getLogger(__name__)

_CLOUD_CLI_POSIX_COMMAND = "gcloud"
_CLOUD_CLI_WINDOWS_COMMAND = "gcloud.cmd"
_CLOUD_CLI_CONFIG_COMMAND = "config config-helper --format json"

LOG_FORMAT = "%(name)s:%(message)s"
LOG_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def is_windows_os() -> bool:
    return os.name == "nt"


def gcloud_cmd() -> str:
    if is_windows_os():
        return _CLOUD_CLI_WINDOWS_COMMAND
    return _CLOUD_CLI_POSIX_COMMAND


def get_project_id() -> Optional[str]:
    try:
        output = subprocess.run(
            [gcloud_cmd()] + _CLOUD_CLI_CONFIG_COMMAND.split(),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        LOG.debug("Cloud CLI output: %s", output)
    except (subprocess.CalledProcessError, OSError, IOError) as err:
        logging.debug("Failed to get project ID from the Cloud CLI.", exc_info=True)
        raise errors.InvalidAuthError(err)

    try:
        configuration = json.loads(output)
    except ValueError as err:
        raise errors.ComposerCliError(f"gcloud CLI の設定のデコードに失敗しました: {err}") from None

    try:
        project_id = configuration["configuration"]["properties"]["core"]["project"]
        LOG.info("GCP プロジェクトを使用します: %s", project_id)
        return project_id
    except KeyError:
        raise errors.ComposerCliError("gcloud の設定に project id が存在しません。")


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


def resolve_kube_config_path() -> Optional[str]:
    return os.environ.get(constants.KUBECONFIG_PATH_ENV)


def create_plain_status_text(
    name: str,
    state: str,
    web_url: str,
    image_version: str,
    dags_path: str,
    auth_description: str,
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

    # 認証情報の有効性をチェックして表示
    auth_check = check_auth_validity()
    if auth_check["is_valid"]:
        auth_status = wrap_auth_status_in_color(auth_description, True)
    else:
        auth_status = wrap_auth_status_in_color(auth_check['error_message'], False)

    add_item("認証情報", auth_status)
    add_item("設定パス", gcloud_path)

    return "\n".join(lines)


def get_auth_info() -> Dict[str, str]:
    """現在のgcloud認証情報を取得する"""
    try:
        # application_default_credentials.json を確認
        gcloud_config_path = resolve_gcloud_config_path()
        adc_path = pathlib.Path(gcloud_config_path) / "application_default_credentials.json"

        if adc_path.exists():
            try:
                with open(adc_path, 'r') as f:
                    adc_data = json.load(f)

                # impersonated_service_account の場合はサービスアカウントの権限借用
                if adc_data.get("type") == "impersonated_service_account":
                    service_account_url = adc_data.get("service_account_impersonation_url", "")
                    # URLからサービスアカウント名を抽出
                    # URL形式: https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/
                    # ACCOUNT_EMAIL:generateAccessToken
                    if "serviceAccounts/" in service_account_url:
                        account_name = service_account_url.split("serviceAccounts/")[-1].split(":")[
                            0
                        ]
                    else:
                        account_name = "不明なサービスアカウント"

                    return {
                        "type": "service_account",
                        "account": account_name,
                        "description": f"サービスアカウントの権限借用: {account_name}",
                    }
            except (json.JSONDecodeError, KeyError, IOError) as e:
                LOG.debug("Failed to parse application_default_credentials.json: %s", e)

        # 通常のユーザー認証の場合
        account_output = subprocess.run(
            [gcloud_cmd(), "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "type": "user",
            "account": account_output,
            "description": f"ユーザー認証: {account_output}",
        }
    except (subprocess.CalledProcessError, OSError, IOError) as err:
        LOG.debug("Failed to get auth info: %s", err)
        return {"type": "unknown", "account": "不明", "description": "認証情報の取得に失敗しました"}


def check_auth_validity() -> Dict[str, Any]:
    """
    現在の認証情報の有効性をチェックする

    Returns:
        Dict[str, Any]: 認証情報の状態と詳細情報
        - is_valid: bool - 認証情報が有効かどうか
        - auth_info: Dict[str, str] - 認証情報の詳細
        - error_message: str - エラーメッセージ（無効な場合）
        - suggestions: List[str] - 対処法の提案
    """
    auth_info = get_auth_info()

    # 認証情報が取得できない場合
    if auth_info.get("type") == "unknown":
        return {
            "is_valid": False,
            "auth_info": auth_info,
            "error_message": "認証情報が見つかりません",
            "suggestions": [
                "make auth-user を実行してユーザー認証を行ってください",
                "make auth-sa を実行してサービスアカウント認証を行ってください",
            ],
        }

    try:
        # 現在のプロジェクトを取得して認証の有効性をテスト
        project_output = subprocess.run(
            [gcloud_cmd(), "config", "get-value", "project"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not project_output:
            return {
                "is_valid": False,
                "auth_info": auth_info,
                "error_message": "プロジェクトが設定されていません",
                "suggestions": [
                    "gcloud config set project PROJECT_ID でプロジェクトを設定してください",
                    "make auth-user を実行して認証を行ってください",
                ],
            }

        # 認証トークンの有効性をテスト（簡単なAPI呼び出し）
        try:
            subprocess.run(
                [gcloud_cmd(), "auth", "print-access-token"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            # より詳細なエラーメッセージを生成
            if e.returncode == 1:
                error_msg = "認証トークンの取得に失敗しました（認証情報が無効または期限切れ）"
            elif e.returncode == 2:
                error_msg = "gcloudコマンドの実行に失敗しました"
            else:
                error_msg = f"認証の検証中にエラーが発生しました（終了コード: {e.returncode}）"

            return {
                "is_valid": False,
                "auth_info": auth_info,
                "error_message": error_msg,
                "suggestions": [
                    "make auth-user を実行してユーザー認証を更新してください",
                    "make auth-sa を実行してサービスアカウント認証を更新してください",
                ],
            }

        # サービスアカウントの権限借用の場合、追加のチェック
        if auth_info.get("type") == "service_account":
            try:
                # サービスアカウントの権限をテスト
                account_name = auth_info.get("account", "")
                subprocess.run(
                    [gcloud_cmd(), "iam", "service-accounts", "get-iam-policy", account_name],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError:
                return {
                    "is_valid": False,
                    "auth_info": auth_info,
                    "error_message": "サービスアカウントの権限が不足しています",
                    "suggestions": [
                        "make auth-sa を実行してサービスアカウント認証を更新してください",
                        "サービスアカウントに必要な権限があることを確認してください",
                    ],
                }

        return {"is_valid": True, "auth_info": auth_info, "error_message": None, "suggestions": []}

    except subprocess.CalledProcessError as e:
        # より具体的なエラーメッセージを生成
        if "auth" in str(e.cmd) and e.returncode == 1:
            error_msg = "gcloud認証コマンドの実行に失敗しました（認証情報が無効または期限切れ）"
        elif "config" in str(e.cmd) and e.returncode == 1:
            error_msg = (
                "gcloud設定の取得に失敗しました（プロジェクトが設定されていない可能性があります）"
            )
        else:
            error_msg = f"gcloudコマンドの実行に失敗しました（終了コード: {e.returncode}）"

        return {
            "is_valid": False,
            "auth_info": auth_info,
            "error_message": error_msg,
            "suggestions": [
                "make auth-user を実行してユーザー認証を更新してください",
                "make auth-sa を実行してサービスアカウント認証を更新してください",
            ],
        }
    except FileNotFoundError:
        return {
            "is_valid": False,
            "auth_info": auth_info,
            "error_message": "gcloudコマンドが見つかりません（Google Cloud SDKがインストールされていない可能性があります）",
            "suggestions": [
                "Google Cloud SDKをインストールしてください",
                "https://cloud.google.com/sdk/docs/install を参照してください",
            ],
        }
    except Exception as e:
        return {
            "is_valid": False,
            "auth_info": auth_info,
            "error_message": f"予期しないエラーが発生しました: {str(e)}",
            "suggestions": [
                "make auth-user を実行してユーザー認証を更新してください",
                "make auth-sa を実行してサービスアカウント認証を更新してください",
            ],
        }


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
    LOG.info("プロジェクト ID が指定されていないため、Cloud CLI から取得します。")
    try:
        return get_project_id()
    except errors.ComposerCliError as err:
        msg = (
            "Google Cloud のプロジェクト ID を指定してください（'-p' / '--project'）。\n"
            "gcloud の設定から project id を取得できませんでした:\n"
            f"{err}"
        )
        raise click.UsageError(msg)
