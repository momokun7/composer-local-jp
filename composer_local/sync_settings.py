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
import re
from pathlib import Path
from typing import Optional

from composer_local import errors
from composer_local.utils import require_gcp_composer

LOG = logging.getLogger(__name__)


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
    pattern = re.compile(rf'^({key}\s*=\s*).*$', re.MULTILINE)
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
