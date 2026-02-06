# Copyright 2025 Hirohiko Nakui
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Secret Manager 変数同期モジュール

このモジュールは、Google Cloud Secret Manager に保存された Airflow Variables を
ローカルの Composer 環境へ安全に同期する機能を提供します。
"""

import json
import logging
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from google.auth.exceptions import DefaultCredentialsError
from google.cloud import secretmanager

from composer_local import composer_settings, constants, errors

LOG = logging.getLogger(__name__)


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
            executor.submit(_run_single, label, cmd): label
            for label, cmd in commands.items()
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
    """Composer 内で `airflow variables export -- /dev/stdout` を実行し、JSON を直接取得（GCS不使用）。"""
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
        raise RuntimeError(
            "Composer の出力から JSON の抽出に失敗しました。rawの出力:\n" + out
        )
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
        """
        既存の Secret に新しいバージョンを追加する。

        Args:
            secret_id: Secret の ID
            new_value: 新しい値（文字列）
        """
        client = self._get_client()
        sid = secret_id or self.secret_id

        try:
            client.add_secret_version(
                request={
                    "parent": f"projects/{self.project_id}/secrets/{sid}",
                    "payload": {"data": new_value.encode("UTF-8")},
                }
            )

            LOG.info(f"Secret を更新しました: {sid}")

        except Exception as e:
            LOG.error(f"Secret 更新エラー {sid}: {e}")
            raise errors.ComposerCliError(f"Secret の更新に失敗しました {sid}: {e}")

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
            diff_lines.append(f"  {constants.ANSI_GREEN}+ \"{masked_value}\"{constants.ANSI_RESET}")

        # 削除された変数（赤色）
        for key, value in changes["removed"].items():
            masked_value = mask_value(value)
            diff_lines.append(f"{constants.ANSI_RED}-{constants.ANSI_RESET} {key}")
            diff_lines.append(f"  {constants.ANSI_RED}- \"{masked_value}\"{constants.ANSI_RESET}")

        # 変更された変数（黄色）
        for key, change_info in changes["modified"].items():
            old_value = change_info["old_value"]
            new_value = change_info["new_value"]
            old_masked = mask_value(old_value)
            new_masked = mask_value(new_value)
            diff_lines.append(f"{constants.ANSI_YELLOW}~{constants.ANSI_RESET} {key}")
            diff_lines.append(f"  {constants.ANSI_RED}- \"{old_masked}\"{constants.ANSI_RESET}")
            diff_lines.append(f"  {constants.ANSI_GREEN}+ \"{new_masked}\"{constants.ANSI_RESET}")

        return "\n".join(diff_lines)

    def sync_to_local_airflow(self, env=None) -> None:
        """
        Secret Manager から取得した Variables をローカル Airflow に反映する。
        Secret Manager に値がある場合は、ローカルの Variables を一度すべて削除してから取り込む。

        Args:
            env: Environment インスタンス（実行中のコンテナ内のVariables削除用）
        """
        variables = self.get_all_variables()

        if not variables:
            LOG.warning("Secret Manager に Variables が見つかりません")
            return

        # Secret Manager に値がある場合は、ローカルの Variables を更新

        # 実行中のAirflowコンテナ内のVariablesを更新
        if env:
            self.clear_airflow_variables_in_container(env)

        # ローカルのvariables.jsonファイルを更新
        self.clear_all_local_variables()

        # ローカルの variables.json に書き出し
        if self.local_env_path:
            variables_file = self.local_env_path / "data" / "variables.json"
            variables_file.parent.mkdir(parents=True, exist_ok=True)

            with open(variables_file, "w") as f:
                json.dump(variables, f, indent=2)

            LOG.info(f"{len(variables)} 件の Variables を保存しました: {variables_file}")

    def clear_all_local_variables(self) -> None:
        """
        ローカルの Airflow Variables をすべて削除する。
        """
        LOG.info("ローカルの Airflow Variables をすべて削除します")

        # ローカルの variables.json を削除
        if self.local_env_path:
            variables_file = self.local_env_path / "data" / "variables.json"
            if variables_file.exists():
                try:
                    variables_file.unlink()
                    LOG.info(f"ローカルの variables.json を削除しました: {variables_file}")
                except Exception as e:
                    LOG.warning(f"variables.json の削除に失敗しました: {e}")

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
                    variables_output = result.output.decode('utf-8')
                    # 変数名を抽出（空行やヘッダーを除く）
                    variable_names = []
                    for line in variables_output.split('\n'):
                        line = line.strip()
                        if line and not line.startswith('Key') and not line.startswith('---'):
                            # 最初の列（変数名）を取得
                            var_name = line.split()[0] if line.split() else None
                            if var_name:
                                variable_names.append(var_name)

                    LOG.info(f"削除対象のVariables: {len(variable_names)} 件")

                    # 並列でVariablesを削除
                    commands = {
                        name: ["/home/airflow/run_as_user.sh", "airflow", "variables", "delete", name]
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

def create_sync_client(
    project_id: str,
    local_env_path: Path | None = None,
) -> SecretManagerSync:
    """
    SecretManagerSync クライアントを適切な設定で作成する。

    Args:
        project_id: GCP プロジェクト ID
        local_env_path: ローカル環境のパス

    Returns:
        SecretManagerSync: 構成済みクライアント
    """
    return SecretManagerSync(
        project_id=project_id,
        local_env_path=local_env_path,
    )
