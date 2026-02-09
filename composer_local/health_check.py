"""ヘルスチェック・ポーリング関連の処理を担うミックスイン。

Environment クラスにサービスの準備完了待機の責務を提供する。
"""

import time
import urllib.error
import urllib.request
from typing import Callable

from composer_local import composer_settings, errors


class HealthCheckMixin:
    """ヘルスチェック・ポーリング関連の処理を行うミックスイン。"""

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

    def _wait_until_webserver_ready(self, timeout_seconds: int, interval_seconds: int) -> None:
        url = f"http://localhost:{self.port}"

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
