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
Cloud Composer から Variables を取得して Secret Manager に送信するスクリプト

このスクリプトは、Cloud Composer 環境から Airflow Variables を取得し、
Secret Manager に保存します。
"""

import argparse
import json

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from composer_local import composer_settings, constants
from composer_local.secret_manager_sync import SecretManagerSync, export_variables_via_gcloud
from composer_local.utils import require_gcp_secret_manager


def main():
    parser = argparse.ArgumentParser(
        description="Cloud Composer の Airflow Variables を取得し、Secret Manager に保存します。"
    )
    parser.add_argument("--project", default=composer_settings.PROJECT_ID)
    parser.add_argument("--location", default=composer_settings.COMPOSER_LOCATION)
    parser.add_argument("--env-name", default=composer_settings.COMPOSER_ENV_NAME)
    parser.add_argument("--secret-id", default=composer_settings.SECRET_ID)
    args = parser.parse_args()

    with Progress(
        SpinnerColumn(),
        TextColumn("[blue]Secret Manager と Variables を比較中..."),
        TimeElapsedColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task("Secret Manager と Variables を比較中...", total=None)
        try:
            variables = export_variables_via_gcloud(args.project, args.location, args.env_name)

            # 変更を検出してdiffを表示
            sync_client = SecretManagerSync(project_id=args.project, secret_id=args.secret_id)
            changes = sync_client.compare_variables(variables)

            if changes["has_changes"]:
                # Secret Manager に保存
                sync_client.update_secret(args.secret_id, json.dumps(variables, ensure_ascii=False))

                progress.update(
                    task,
                    description="[green]Variables の変更を検出し、Secret Manager を更新しました",
                )
                progress.stop()

                # diff表示
                print()
                diff_output = sync_client.format_variables_diff(changes)
                print("─" * 30)
                print(diff_output)
                print("─" * 30)
            else:
                progress.update(task, description="[yellow]Variables に変更はありません")
                progress.stop()
                msg = (
                    f"{constants.ANSI_YELLOW}Variables に変更はありませんでした。"
                    f"{constants.ANSI_RESET}"
                )
                print(msg)

        except Exception as e:
            progress.update(task, description="[red]Variables の取得/比較に失敗")
            progress.stop()
            # Secret が存在しない場合は新規作成
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                msg = (
                    f"{constants.ANSI_YELLOW}Secret が存在しないため、"
                    f"新規作成します{constants.ANSI_RESET}"
                )
                print(msg)
                secretmanager, _DefaultCredentialsError = require_gcp_secret_manager()
                client = secretmanager.SecretManagerServiceClient()
                parent = f"projects/{args.project}"
                name = f"{parent}/secrets/{args.secret_id}"

                client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": args.secret_id,
                        "secret": {"replication": {"automatic": {}}},
                    }
                )
                client.add_secret_version(
                    request={
                        "parent": name,
                        "payload": {
                            "data": json.dumps(variables, ensure_ascii=False).encode("utf-8")
                        },
                    }
                )
                print(
                    f"{constants.ANSI_GREEN}Secret を新規作成し、Variables を保存しました"
                    f"{constants.ANSI_RESET}"
                )
            else:
                raise


if __name__ == "__main__":
    main()
