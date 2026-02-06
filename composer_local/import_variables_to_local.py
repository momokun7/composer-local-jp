#!/usr/bin/env python3
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
Secret Manager からローカル Composer 環境へ Variables をインポートするスクリプト

このスクリプトは、Secret Manager から Airflow Variables を取得し、
ローカル Composer 環境にインポートします。
"""

import argparse
import json
import logging
from pathlib import Path

from composer_local import composer_settings, constants
from composer_local import environment as composer_environment
from composer_local.secret_manager_sync import create_sync_client, run_parallel_container_commands

LOG = logging.getLogger(__name__)


def _import_variables_to_container(env, variables: dict) -> None:
    """実行中のAirflowコンテナ内にVariablesをインポートする。"""
    try:
        status = env.status()
        if status != constants.ContainerStatus.RUNNING:
            LOG.warning("Airflow が実行中ではありません。Variables のインポートをスキップします。")
            return

        LOG.info(f"実行中のAirflowコンテナ内にVariablesをインポート中... ({len(variables)} 件)")

        app = env._get_container(env.container_name, assert_running=True)
        commands = {
            name: ["/home/airflow/run_as_user.sh", "airflow", "variables", "set", name, value]
            for name, value in variables.items()
        }
        run_parallel_container_commands(app, commands, "Variable設定")

    except Exception as e:
        LOG.error(f"Airflow Variablesインポート処理でエラーが発生しました: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Secret Manager から Airflow Variables を取得し、"
            "ローカル Composer 環境にインポートします。"
        )
    )
    parser.add_argument("--project", default=composer_settings.PROJECT_ID)
    parser.add_argument("--secret-id", default=composer_settings.SECRET_ID)
    parser.add_argument(
        "--local-env-dir", default=str(Path.cwd() / "composer" / composer_settings.LOCAL_ENV_NAME)
    )
    parser.add_argument("--airflow-url", default=composer_settings.AIRFLOW_URL)
    parser.add_argument("--verbose", action="store_true", help="詳細なログを表示する")
    parser.add_argument("--debug", action="store_true", help="デバッグログを表示する")
    args = parser.parse_args()

    # ログ設定
    from composer_local.utils import setup_logging
    setup_logging(verbose=args.verbose, debug=args.debug)

    try:
        # ローカル環境を読み込み
        env_path = Path(args.local_env_dir)
        env = composer_environment.Environment.load_from_config(env_path, None)

        # SecretManagerSync クライアントを作成
        sync_client = create_sync_client(
            project_id=args.project,
            local_env_path=env_path,
        )
        sync_client.secret_id = args.secret_id

        # Secret Manager から Variables を取得
        variables = sync_client.get_all_variables()

        if not variables:
            print(f"{constants.ANSI_YELLOW}Secret Manager に Variables が見つかりません{constants.ANSI_RESET}")
            return

        # ローカルの既存Variablesを削除してインポート
        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[blue]ローカルの Variables を更新中..."),
            TimeElapsedColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("ローカルの Variables を更新中...", total=None)

            # コンテナ内の既存Variablesを削除
            sync_client.clear_airflow_variables_in_container(env)

            # コンテナ内に新しいVariablesをインポート
            _import_variables_to_container(env, variables)

            # ローカルファイルも更新
            sync_client.clear_all_local_variables()
            variables_file = env_path / "data" / "variables.json"
            variables_file.parent.mkdir(parents=True, exist_ok=True)
            with open(variables_file, "w") as f:
                json.dump(variables, f, indent=2, ensure_ascii=False)

            progress.update(task, description="[green]Variables の更新が完了しました")

        print(f"ローカルの Airflow Variables を更新しました ({len(variables)} 件)")

    except Exception as e:
        print(f"{constants.ANSI_RED}Variables のインポートでエラーが発生しました: {e}{constants.ANSI_RESET}")
        raise


if __name__ == "__main__":
    main()
