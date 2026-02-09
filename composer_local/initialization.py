"""初回セットアップ・バナー表示関連の処理を担うミックスイン。

Environment クラスに初期化処理の責務を提供する。
"""

import json
import logging
from typing import List

from composer_local import composer_settings, constants

LOG = logging.getLogger(__name__)


class InitializationMixin:
    """初回セットアップ・バナー表示関連の処理を行うミックスイン。"""

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

    def _handle_first_time_init(self):
        """初回セットアップ判定と実行。未初期化なら初期化してバナー表示。"""
        initialized_marker = self.env_dir_path / ".initialized"
        if not initialized_marker.exists():
            self._first_time_init()
            self._show_setup_banner()
        else:
            print(f"{self.name} 環境を起動しました。")
            print(f"Airflow Web UI: http://localhost:{self.port}")
