# Copyright 2022 Google LLC
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

import logging
from pathlib import Path
from typing import Optional

from google.cloud.orchestration.airflow import service_v1

from composer_local import errors

LOG = logging.getLogger(__name__)


def _compose_env_resource_name(project_id: str, location: str, env_name: str) -> str:
    return f"projects/{project_id}/locations/{location}/environments/{env_name}"


def fetch_composer_env_details(project_id: str, location: str, env_name: str) -> dict:
    """
    Cloud Composer 環境の詳細を API を使用して取得します。

    Returns:
        dict: キーとして image_version, python_version, location, env_name を持つ辞書
    """
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


def write_composer_settings(
    settings_path: Path,
    env_name: str,
    location: str,
    image_version: str,
    python_version: Optional[str],
) -> None:
    """composer_settings.py を Cloud Composer の値で上書きします。"""
    content = (
        '"""\n'
        "このファイルは、ローカル環境の Composer 設定を管理します。\n"
        "Cloud Composer の設定をこのファイルに同期することで、ローカル環境の Composer 設定を管理できます。\n\n"
        "このファイルの設定は以下の場所で使用されます：\n"
        "- Makefile: 環境作成、認証、変数同期などのコマンド\n"
        "- CLI: composer-local コマンドのデフォルト値\n"
        "- 各種スクリプト: プロジェクトID、サービスアカウントなどの参照\n"
        '"""\n\n'
        "# =============================================================================\n"
        "# Cloud Composer 環境設定\n"
        "# =============================================================================\n\n"
        "# Cloud Composer 環境の識別情報\n"
        f"COMPOSER_ENV_NAME = \"{env_name}\"\n"
        f"COMPOSER_LOCATION = \"{location}\"\n\n"
        "# ランタイム/ツールバージョン\n"
        "# 例: \"composer-3-airflow-2.10.5-build.0\"\n"
        f"COMPOSER_IMAGE_VERSION = \"{image_version}\"\n\n"
        "# Composer イメージで報告される Python のメジャー/マイナーバージョン（文字列）\n"
        f"COMPOSER_PYTHON_VERSION = \"{python_version or ''}\"\n"
    )
    settings_path.write_text(content)
    LOG.info("Cloud Composer から %s を更新しました", settings_path)


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
