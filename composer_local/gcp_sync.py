"""GCP 連携モジュール

Cloud Composer / Secret Manager との Variables・設定同期、
gcloud 認証情報の取得をすべてこのモジュールに集約する。
google-cloud-* パッケージは関数内で遅延 import する（gcp extra）。
"""

import json
import logging
import pathlib
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from composer_local import composer_settings, constants, errors
from composer_local.utils import is_windows_os

LOG = logging.getLogger(__name__)

_CLOUD_CLI_POSIX_COMMAND = "gcloud"
_CLOUD_CLI_WINDOWS_COMMAND = "gcloud.cmd"
_CLOUD_CLI_CONFIG_COMMAND = "config config-helper --format json"

_GCP_INSTALL_HINT = (
    "GCP 連携機能には追加パッケージが必要です。\n  uv sync --extra gcp\nを実行してください。"
)


# ---------------------------------------------------------------------------
# GCP パッケージの遅延インポートヘルパー
# ---------------------------------------------------------------------------


def require_gcp_secret_manager():
    """google-cloud-secret-manager パッケージの存在を確認し、モジュールを返す。

    Returns:
        tuple: (secretmanager モジュール, DefaultCredentialsError 例外クラス)

    Raises:
        ImportError: パッケージが未インストールの場合
    """
    try:
        from google.auth.exceptions import DefaultCredentialsError  # type: ignore[import-not-found]
        from google.cloud import secretmanager  # type: ignore[import-not-found]
    except ImportError as _err:
        raise ImportError(_GCP_INSTALL_HINT) from _err
    return secretmanager, DefaultCredentialsError


def require_gcp_composer():
    """google-cloud-orchestration-airflow パッケージの存在を確認し、モジュールを返す。

    Returns:
        service_v1 モジュール

    Raises:
        ImportError: パッケージが未インストールの場合
    """
    try:
        from google.cloud.orchestration.airflow import service_v1  # type: ignore[import-not-found]
    except ImportError as _err:
        raise ImportError(_GCP_INSTALL_HINT) from _err
    return service_v1


# ---------------------------------------------------------------------------
# gcloud 認証情報の取得・検証
# ---------------------------------------------------------------------------


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
        raise errors.InvalidAuthError(str(err))

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


def get_auth_info() -> Dict[str, str]:
    """現在のgcloud認証情報を取得する"""
    from composer_local import utils

    try:
        # application_default_credentials.json を確認
        gcloud_config_path = utils.resolve_gcloud_config_path()
        adc_path = pathlib.Path(gcloud_config_path) / "application_default_credentials.json"

        if adc_path.exists():
            try:
                with open(adc_path, "r") as f:
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


def _auth_result(
    auth_info: Dict[str, str],
    error_message: Optional[str] = None,
    suggestions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """check_auth_validity の戻り値を組み立てるヘルパー"""
    if error_message is None:
        return {"is_valid": True, "auth_info": auth_info, "error_message": None, "suggestions": []}
    default_suggestions = [
        "make auth を実行してユーザー認証を更新してください",
        "make auth SERVICE_ACCOUNT=... を実行してサービスアカウント認証を更新してください",
    ]
    return {
        "is_valid": False,
        "auth_info": auth_info,
        "error_message": error_message,
        "suggestions": suggestions or default_suggestions,
    }


def _error_msg_for_returncode(returncode: int) -> str:
    """returncode に応じた認証エラーメッセージを返す"""
    if returncode == 1:
        return "認証トークンの取得に失敗しました（認証情報が無効または期限切れ）"
    if returncode == 2:
        return "gcloudコマンドの実行に失敗しました"
    return f"認証の検証中にエラーが発生しました（終了コード: {returncode}）"


def check_auth_validity() -> Dict[str, Any]:
    """現在の認証情報の有効性をチェックする。

    Returns:
        Dict[str, Any]: ``is_valid``, ``auth_info``, ``error_message``,
        ``suggestions`` をキーに持つ辞書。
    """
    auth_info = get_auth_info()

    if auth_info.get("type") == "unknown":
        return _auth_result(auth_info, "認証情報が見つかりません")

    try:
        project = subprocess.run(
            [gcloud_cmd(), "config", "get-value", "project"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        if not project:
            return _auth_result(
                auth_info,
                "プロジェクトが設定されていません",
                [
                    "gcloud config set project PROJECT_ID でプロジェクトを設定してください",
                    "make auth を実行して認証を行ってください",
                ],
            )

        subprocess.run(
            [gcloud_cmd(), "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        )

        if auth_info.get("type") == "service_account":
            subprocess.run(
                [
                    gcloud_cmd(),
                    "iam",
                    "service-accounts",
                    "get-iam-policy",
                    auth_info.get("account", ""),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        return _auth_result(auth_info)

    except subprocess.CalledProcessError as e:
        return _auth_result(auth_info, _error_msg_for_returncode(e.returncode))
    except FileNotFoundError:
        return _auth_result(
            auth_info,
            "gcloudコマンドが見つかりません"
            "（Google Cloud SDKがインストールされていない可能性があります）",
            [
                "Google Cloud SDKをインストールしてください",
                "https://cloud.google.com/sdk/docs/install を参照してください",
            ],
        )
    except Exception as e:
        return _auth_result(auth_info, f"予期しないエラーが発生しました: {e}")


# ---------------------------------------------------------------------------
# Variables 同期（Secret Manager / 直接同期）
# ---------------------------------------------------------------------------


def run_parallel_container_commands(
    app,
    commands: dict[str, list[str]],
    action: str = "処理",
    max_workers: int | None = None,
) -> tuple[int, int]:
    """Docker コンテナ内でコマンドを並列実行する。

    Args:
        app: Docker container instance
        commands: {識別ラベル: コマンドリスト}
        action: ログ出力用のアクション名
        max_workers: 最大並列数（None の場合は設定値を使用）

    Returns:
        (成功件数, 失敗件数)
    """
    if not commands:
        return 0, 0

    log_lock = threading.Lock()
    if max_workers is None:
        max_workers = min(len(commands), composer_settings.MAX_PARALLEL_WORKERS)

    def _run_single(label: str, cmd: list[str]) -> tuple[str, bool]:
        try:
            result = app.exec_run(cmd=cmd)
            if result.exit_code == 0:
                with log_lock:
                    LOG.info(f"{action}完了: {label}")
                return label, True
            else:
                with log_lock:
                    LOG.warning(f"{action}失敗 {label}: {result.output.decode('utf-8')}")
                return label, False
        except Exception as e:
            with log_lock:
                LOG.warning(f"{action}失敗 {label}: {e}")
            return label, False

    LOG.info(f"並列{action}開始: {len(commands)} 件を {max_workers} スレッドで処理")
    start_time = time.time()
    success_count = 0
    failure_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_run_single, label, cmd): label for label, cmd in commands.items()
        }
        for future in as_completed(futures):
            _, success = future.result()
            if success:
                success_count += 1
            else:
                failure_count += 1

    elapsed = time.time() - start_time
    LOG.info(f"並列{action}完了: {success_count} 件成功, {failure_count} 件失敗, {elapsed:.2f}秒")

    if failure_count > 0:
        LOG.warning(f"{failure_count} 件の{action}に失敗しました")

    return success_count, failure_count


def mask_value(value: str) -> str:
    """
    変数値をマスキングする。

    Args:
        value: マスキング対象の文字列

    Returns:
        str: マスキングされた文字列
    """
    prefix_len = composer_settings.MASK_PREFIX_LENGTH
    suffix_len = composer_settings.MASK_SUFFIX_LENGTH
    min_len = prefix_len + suffix_len
    if len(value) > min_len:
        return value[:prefix_len] + "..." + value[-suffix_len:]
    return "***"


def run_command(cmd: list[str]) -> str:
    """サブプロセスでコマンドを実行し、標準出力を文字列で返す。"""
    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout
    except subprocess.CalledProcessError as exc:
        # 失敗時に実行コマンド・標準出力・標準エラーを含めてわかりやすく報告
        cmd_str = " ".join(cmd)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        raise RuntimeError(
            (
                "コマンドの実行に失敗しました。\n"
                f"コマンド: {cmd_str}\n"
                f"終了コード: {exc.returncode}\n"
                f"標準出力:\n{stdout}\n"
                f"標準エラー出力:\n{stderr}\n"
            )
        ) from exc


def export_variables_via_gcloud(project: str, location: str, env_name: str) -> dict:
    """Composer 内で `airflow variables export -- /dev/stdout` を実行し、
    JSON を直接取得（GCS不使用）。"""
    out = run_command(
        [
            "gcloud",
            "--quiet",
            "--project",
            project,
            "composer",
            "environments",
            "run",
            env_name,
            "--location",
            location,
            "variables",
            "export",
            "--",
            "/dev/stdout",
        ]
    )

    # gcloud はコマンドの前後に余計な案内文を混ぜることがあるため、
    # 最後の { から最後の } までを抜き出して JSON として解釈する。
    start = out.find("{")
    end = out.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Composer の出力から JSON の抽出に失敗しました。rawの出力:\n" + out)
    payload = out[start : end + 1]
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("Variables の形式が不正です（JSON オブジェクトである必要があります）。")
    # 空値は除外
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


class SecretManagerSync:
    """
    Secret Manager とローカル環境間で Airflow Variables を同期するクラス。

    単一の Secret に JSON 形式のキー・バリューを格納する実装です。
    既定の secret_id は 'local_composer_airflow_variables' です。
    """

    def __init__(
        self,
        project_id: str,
        local_env_path: Path | None = None,
        secret_id: str = composer_settings.SECRET_ID,
    ):
        self.project_id = project_id
        self.local_env_path = local_env_path
        self.client = None
        self.secret_id = secret_id

    def _get_client(self):
        """Secret Manager クライアントを初期化する。"""
        if self.client is None:
            secretmanager, DefaultCredentialsError = require_gcp_secret_manager()
            try:
                self.client = secretmanager.SecretManagerServiceClient()
            except DefaultCredentialsError:
                msg = (
                    "Google Cloud の認証情報が見つかりません。"
                    "'gcloud auth application-default login' を実行してください"
                )
                raise errors.ComposerCliError(msg)
        return self.client

    def _get_secret_resource_name(self, secret_id: str | None = None) -> str:
        sid = secret_id or self.secret_id
        return f"projects/{self.project_id}/secrets/{sid}"

    def get_secret_value(self, secret_id: str | None = None) -> str:
        """
        指定した Secret の最新バージョンの値を取得する。

        Args:
            secret_id: Secret の ID

        Returns:
            str: Secret の文字列値
        """
        client = self._get_client()
        sid = secret_id or self.secret_id
        name = f"{self._get_secret_resource_name(sid)}/versions/latest"

        try:
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            LOG.error(f"Secret の取得エラー {sid}: {e}")
            raise errors.ComposerCliError(f"Secret の取得に失敗しました {sid}: {e}")

    def update_secret(self, secret_id: str | None, new_value: str) -> None:
        """既存の Secret に新しいバージョンを追加する。Secret が無ければ新規作成する。"""
        client = self._get_client()
        sid = secret_id or self.secret_id
        parent = f"projects/{self.project_id}"
        try:
            client.add_secret_version(
                request={
                    "parent": f"{parent}/secrets/{sid}",
                    "payload": {"data": new_value.encode("UTF-8")},
                }
            )
            LOG.info(f"Secret を更新しました: {sid}")
        except Exception as e:
            err_lower = str(e).lower()
            recoverable = (
                "not found" in err_lower
                or "does not exist" in err_lower
                or "destroyed" in err_lower
            )
            if not recoverable:
                LOG.error(f"Secret 更新エラー {sid}: {e}")
                raise errors.ComposerCliError(f"Secret の更新に失敗しました {sid}: {e}")
            print(
                f"{constants.ANSI_YELLOW}Secret が存在しないため、新規作成します"
                f"{constants.ANSI_RESET}"
            )
            client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": sid,
                    "secret": {"replication": {"automatic": {}}},
                }
            )
            client.add_secret_version(
                request={
                    "parent": f"{parent}/secrets/{sid}",
                    "payload": {"data": new_value.encode("UTF-8")},
                }
            )
            LOG.info(f"Secret を新規作成しました: {sid}")

    def get_all_variables(self) -> dict[str, str]:
        """
        単一 JSON Secret に格納された全 Variables を辞書で返す。

        Returns:
            Dict[str, str]: 変数名と値の辞書
        """
        raw = self.get_secret_value(self.secret_id)
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Secret の内容が JSON オブジェクトではありません")
            return {str(k): data[k] for k in data}
        except Exception as e:
            LOG.error(f"JSON の解析エラー（secret={self.secret_id}）: {e}")
            raise

    def compare_variables(
        self, new_variables: dict[str, str], old_variables: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        2つのvariablesを比較し、変更を検出する。

        Args:
            new_variables: 新しいvariablesデータ
            old_variables: 古いvariablesデータ。Noneの場合はSecret Managerから取得

        Returns:
            Dict: 変更情報を含む辞書
                - has_changes: bool - 変更があるかどうか
                - added: Dict[str, str] - 追加された変数
                - removed: Dict[str, str] - 削除された変数
                - modified: Dict[str, Dict[str, str]] - 変更された変数（old_value, new_value）
        """
        if old_variables is None:
            try:
                # Secret Managerから現在のvariablesを取得
                old_variables = self.get_all_variables()
            except Exception as e:
                # Secret Managerにvariablesが存在しない場合は、すべてが新規追加
                LOG.info(f"Secret Manager に variables が存在しません: {e}")
                return {"has_changes": True, "added": new_variables, "removed": {}, "modified": {}}

        added = {}
        removed = {}
        modified = {}

        # 追加・変更された変数をチェック
        for key, value in new_variables.items():
            if key not in old_variables:
                added[key] = value
            elif old_variables[key] != value:
                modified[key] = {"old_value": old_variables[key], "new_value": value}

        # 削除された変数をチェック
        for key, value in old_variables.items():
            if key not in new_variables:
                removed[key] = value

        has_changes = bool(added or removed or modified)

        return {
            "has_changes": has_changes,
            "added": added,
            "removed": removed,
            "modified": modified,
        }

    def format_variables_diff(self, changes: dict[str, Any]) -> str:
        """
        変更内容をdiff形式でフォーマットする。

        Args:
            changes: compare_variablesの戻り値

        Returns:
            str: フォーマットされたdiff文字列
        """
        if not changes["has_changes"]:
            return "変更はありません"

        diff_lines = [
            f"{constants.ANSI_GRAY}# Variables の変更:{constants.ANSI_RESET}",
            "",
        ]

        # 追加された変数（緑色）
        for key, value in changes["added"].items():
            masked_value = mask_value(value)
            diff_lines.append(f"{constants.ANSI_GREEN}+{constants.ANSI_RESET} {key}")
            diff_lines.append(f'  {constants.ANSI_GREEN}+ "{masked_value}"{constants.ANSI_RESET}')

        # 削除された変数（赤色）
        for key, value in changes["removed"].items():
            masked_value = mask_value(value)
            diff_lines.append(f"{constants.ANSI_RED}-{constants.ANSI_RESET} {key}")
            diff_lines.append(f'  {constants.ANSI_RED}- "{masked_value}"{constants.ANSI_RESET}')

        # 変更された変数（黄色）
        for key, change_info in changes["modified"].items():
            old_value = change_info["old_value"]
            new_value = change_info["new_value"]
            old_masked = mask_value(old_value)
            new_masked = mask_value(new_value)
            diff_lines.append(f"{constants.ANSI_YELLOW}~{constants.ANSI_RESET} {key}")
            diff_lines.append(f'  {constants.ANSI_RED}- "{old_masked}"{constants.ANSI_RESET}')
            diff_lines.append(f'  {constants.ANSI_GREEN}+ "{new_masked}"{constants.ANSI_RESET}')

        return "\n".join(diff_lines)

    def clear_airflow_variables_in_container(self, env) -> None:
        """
        実行中のAirflowコンテナ内のVariablesをすべて削除する。

        Args:
            env: Environment インスタンス
        """
        try:
            from composer_local import constants as _c

            # Airflowが実行中かチェック
            status = env.status()
            if status != _c.ContainerStatus.RUNNING:
                LOG.warning("Airflow が実行中ではありません。Variables の削除をスキップします。")
                return

            LOG.info("実行中のAirflowコンテナ内のVariablesを削除中...")

            # 既存のvariablesをリストアップ
            try:
                # Dockerコンテナに直接アクセスしてvariables listを実行
                app = env._get_container(env.container_name, assert_running=True)
                cmd = ["/home/airflow/run_as_user.sh", "airflow", "variables", "list"]
                result = app.exec_run(cmd=cmd)

                if result.exit_code == 0:
                    variables_output = result.output.decode("utf-8")
                    # 変数名を抽出（空行やヘッダーを除く）
                    variable_names = []
                    for line in variables_output.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("Key") and not line.startswith("---"):
                            # 最初の列（変数名）を取得
                            var_name = line.split()[0] if line.split() else None
                            if var_name:
                                variable_names.append(var_name)

                    LOG.info(f"削除対象のVariables: {len(variable_names)} 件")

                    # 並列でVariablesを削除
                    commands = {
                        name: [
                            "/home/airflow/run_as_user.sh",
                            "airflow",
                            "variables",
                            "delete",
                            name,
                        ]
                        for name in variable_names
                    }
                    run_parallel_container_commands(app, commands, "Variable削除")

                else:
                    LOG.warning(
                        f"Variables リストの取得に失敗しました: {result.output.decode('utf-8')}"
                    )

            except Exception as e:
                LOG.error(f"Variables削除中にエラーが発生しました: {e}")

        except Exception as e:
            LOG.error(f"Airflow Variables削除処理でエラーが発生しました: {e}")


# ---------------------------------------------------------------------------
# Composer 設定の同期
# ---------------------------------------------------------------------------


def _compose_env_resource_name(project_id: str, location: str, env_name: str) -> str:
    return f"projects/{project_id}/locations/{location}/environments/{env_name}"


def fetch_composer_env_details(project_id: str, location: str, env_name: str) -> dict:
    """
    Cloud Composer 環境の詳細を API を使用して取得します。

    Returns:
        dict: キーとして image_version, python_version, location, env_name を持つ辞書
    """
    service_v1 = require_gcp_composer()
    client = service_v1.EnvironmentsClient()
    name = _compose_env_resource_name(project_id, location, env_name)
    try:
        env = client.get_environment(request={"name": name})
    except Exception as err:
        raise errors.ComposerCliError(f"Composer 環境 '{name}' の取得に失敗しました: {err}")

    software = env.config.software_config
    image_version = getattr(software, "image_version", "") or ""
    python_version = getattr(software, "python_version", "") or ""

    return {
        "env_name": env_name,
        "location": location,
        "image_version": image_version,
        "python_version": str(python_version) if python_version else "",
    }


def _update_setting(content: str, key: str, value: str) -> str:
    """既存の設定ファイル内の特定のキーの値を更新する。キーが存在しない場合は末尾に追加する。"""
    pattern = re.compile(rf"^({key}\s*=\s*).*$", re.MULTILINE)
    new_line = f'{key} = "{value}"'
    if pattern.search(content):
        return pattern.sub(new_line, content)
    # キーが存在しない場合、末尾に追加
    return content.rstrip() + f"\n{new_line}\n"


def write_composer_settings(
    settings_path: Path,
    env_name: str,
    location: str,
    image_version: str,
    python_version: Optional[str],
) -> None:
    """composer_settings.py の Composer 関連設定のみを更新します。既存の設定は保持されます。"""
    if settings_path.exists():
        content = settings_path.read_text()
    else:
        content = ""

    updates = {
        "COMPOSER_ENV_NAME": env_name,
        "COMPOSER_LOCATION": location,
        "COMPOSER_IMAGE_VERSION": image_version,
        "COMPOSER_PYTHON_VERSION": python_version or "",
    }

    for key, value in updates.items():
        content = _update_setting(content, key, value)

    settings_path.write_text(content)
    updated_keys = ", ".join(updates.keys())
    LOG.info("Cloud Composer から %s を更新しました（%s）", settings_path, updated_keys)


def sync_composer_settings(
    project_id: str,
    location: str,
    env_name: str,
    settings_file: Path,
):
    details = fetch_composer_env_details(project_id, location, env_name)
    write_composer_settings(
        settings_file,
        env_name=details["env_name"],
        location=details["location"],
        image_version=details["image_version"],
        python_version=details["python_version"],
    )


# ---------------------------------------------------------------------------
# CLI エントリポイント用の同期フロー
# ---------------------------------------------------------------------------


def _write_and_import(env, env_path: Path, variables: Dict[str, str]) -> None:
    """variables をローカルへ書き出し、Airflow 起動中なら即時インポートする。"""
    variables_file = env_path / "data" / "variables.json"
    variables_file.parent.mkdir(parents=True, exist_ok=True)
    variables_file.write_text(json.dumps(variables, indent=2, ensure_ascii=False))
    if env.status() == constants.ContainerStatus.RUNNING:
        env.run_airflow_command(["variables", "import", "/home/airflow/gcs/data/variables.json"])
        variables_file.unlink(missing_ok=True)
        print(f"起動中の Airflow に {len(variables)} 件の Variables をインポートしました")
    else:
        print(f"{len(variables)} 件の Variables を保存しました（次回起動時に自動インポート）")


def sync_vars_direct(env, env_path: Path, project: str, location: str, env_name: str) -> None:
    """Cloud Composer から Variables を直接取得してローカルへ反映する（Secret Manager 不使用）。"""
    variables = export_variables_via_gcloud(project, location, env_name)
    if not variables:
        print(
            f"{constants.ANSI_YELLOW}Composer に Variables が見つかりません{constants.ANSI_RESET}"
        )
        return
    _write_and_import(env, env_path, variables)


def sync_vars_via_secret_manager(
    env, env_path: Path, project: str, location: str, env_name: str, secret_id: str
) -> None:
    """Composer → Secret Manager → ローカルの順に Variables を同期する。"""
    variables = export_variables_via_gcloud(project, location, env_name)
    client = SecretManagerSync(project_id=project, local_env_path=env_path, secret_id=secret_id)
    changes = client.compare_variables(variables)
    if changes["has_changes"]:
        client.update_secret(secret_id, json.dumps(variables, ensure_ascii=False))
        print(client.format_variables_diff(changes))
    else:
        print(f"{constants.ANSI_YELLOW}Variables に変更はありませんでした。{constants.ANSI_RESET}")
    stored = client.get_all_variables()
    client.clear_airflow_variables_in_container(env)
    _write_and_import(env, env_path, stored)
