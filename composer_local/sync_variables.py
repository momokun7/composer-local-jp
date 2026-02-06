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
Cloud Composer → ローカル環境へ Variables を直接同期するスクリプト（Secret Manager 不要）

Cloud Composer 環境から Airflow Variables を取得し、ローカル環境に直接インポートします。
Secret Manager を経由しないため、SECRET_ID の設定や Secret Manager API の有効化が不要です。
"""

import argparse
import json
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from composer_local import composer_settings, constants
from composer_local import environment as composer_environment
from composer_local.secret_manager_sync import export_variables_via_gcloud


def main():
    parser = argparse.ArgumentParser(
        description="Cloud Composer の Variables をローカル環境に直接同期します（Secret Manager 不要）"
    )
    parser.add_argument("--project", default=composer_settings.PROJECT_ID)
    parser.add_argument("--location", default=composer_settings.COMPOSER_LOCATION)
    parser.add_argument("--env-name", default=composer_settings.COMPOSER_ENV_NAME)
    parser.add_argument(
        "--local-env-dir",
        default=str(Path.cwd() / "composer" / composer_settings.LOCAL_ENV_NAME),
    )
    args = parser.parse_args()

    # Cloud Composer から Variables を取得
    with Progress(
        SpinnerColumn(),
        TextColumn("[blue]Cloud Composer から Variables を取得中..."),
        TimeElapsedColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task("取得中...", total=None)
        variables = export_variables_via_gcloud(args.project, args.location, args.env_name)
        progress.update(task, description=f"[green]{len(variables)} 件の Variables を取得しました")

    # ローカル環境の variables.json に書き出し
    env_path = Path(args.local_env_dir)
    variables_file = env_path / "data" / "variables.json"
    variables_file.parent.mkdir(parents=True, exist_ok=True)
    with open(variables_file, "w") as f:
        json.dump(variables, f, indent=2, ensure_ascii=False)

    # Airflow が起動中なら即時インポート、そうでなければ次回起動時に自動インポート
    try:
        env = composer_environment.Environment.load_from_config(env_path, None)
        if env.status() == constants.ContainerStatus.RUNNING:
            env.run_airflow_command(
                ["variables", "import", "/home/airflow/gcs/data/variables.json"]
            )
            variables_file.unlink(missing_ok=True)
            print(f"起動中の Airflow に {len(variables)} 件の Variables をインポートしました")
        else:
            print(f"{len(variables)} 件の Variables を保存しました（次回起動時に自動インポート）")
    except Exception:
        print(f"{len(variables)} 件の Variables を保存しました（次回起動時に自動インポート）")


if __name__ == "__main__":
    main()
