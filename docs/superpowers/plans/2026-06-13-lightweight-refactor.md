# 軽量化リファクタリング実装プラン

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** composer-local-jp を軽量・高速・シンプルにする（依存分離 / GCP統合 / Mixin解体 / Makefile刷新 / CLI簡素化 / シークレット漏洩防止）

**Architecture:** 設計書 `docs/superpowers/specs/2026-06-13-lightweight-refactor-design.md` に従う。CLI本体は click/docker/rich のみに依存。GCP連携は `gcp_sync.py` 1ファイル + `sync` コマンドに統合。Environment は Mixin をやめ `docker_ops.py` の関数群を呼ぶコンポジションにする。

**Tech Stack:** Python 3.11+, click, docker SDK, rich, uv, pre-commit, gitleaks

**重要な制約:**
- テスト・lint の実行は settings.json の deny で Claude からは実行不可。各検証チェックポイントでは **ユーザーに `make test` / `make lint` の実行を依頼し、出力を貼ってもらう**こと
- コミットメッセージは日本語、prefix は feat/fix/refactor/chore/docs。Co-Authored-By 等の AI 痕跡は入れない
- 絵文字は使用しない

**最終ファイル構成:**

```
composer_local/
  __init__.py          # 既存維持（composer_settings デフォルト提供）
  __main__.py          # 既存維持
  cli.py               # 7コマンド: start/stop/status/logs/run/sync/remove
  environment.py       # Environment + EnvironmentConfig（Mixin統合済み）
  docker_ops.py        # 新規: Docker操作・ヘルスチェック関数群
  gcp_sync.py          # 新規: GCP連携すべて（SM同期/直接同期/設定同期/認証情報）
  files.py             # 既存維持
  errors.py            # 既存維持
  constants.py         # 既存維持（不要メッセージ削除のみ）
  utils.py             # GCP認証系を gcp_sync.py へ移動して縮小
  console.py           # 既存維持
  version.py           # 既存維持
  composer_settings.py.example
  docker_files/        # 既存維持
削除: docker_manager.py, health_check.py, initialization.py,
      secret_manager_sync.py, sync_settings.py, sync_variables.py,
      export_composer_variables.py, import_variables_to_local.py,
      scripts/load_make_settings.py
tests/
  test_gcp_sync.py     # 新規: GCP系テスト統合
  test_environment.py  # patch先パス更新
  test_cli.py          # 新コマンド体系に更新
  test_utils.py        # 移動関数のテストを test_gcp_sync.py へ
  （test_files.py / test_errors.py / test_constants.py は維持）
削除: test_secret_manager_sync.py, test_sync_settings.py,
      test_sync_variables.py, test_import_variables_to_local.py,
      test_export_composer_variables.py
```

---

### Task 1: 依存関係の分離（pyproject.toml）

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: dependencies から Airflow を外し、dag-dev extra と pre-commit を追加**

`pyproject.toml` の該当セクションを以下に書き換える:

```toml
dependencies = [
    "click>=8.1.8,<9.0.0",
    "docker>=7.0.0",
    "rich>=13.7.0",
]
[project.scripts]
composer-local = "composer_local.__main__:cli"


[project.optional-dependencies]
gcp = [
    "google-auth>=2.29.0,<3.0.0",
    "google-cloud-orchestration-airflow>=1.2.0",
    "google-cloud-artifact-registry>=1.2.0",
    "google-cloud-secret-manager>=2.0.0",
]
dag-dev = [
    "apache-airflow==2.10.5",
    "apache-airflow-providers-google>=14.0.0",
]
dev = [
    "ruff>=0.8.0",
    "pytest>=8.0.0,<9.0.0",
    "pytest-cov>=6.0.0,<7.0.0",
    "pre-commit>=4.0.0",
]
```

`[dependency-groups]` も同様に `pre-commit>=4.0.0` を追加する:

```toml
[dependency-groups]
dev = ["ruff>=0.8.0", "pytest>=8.0.0", "pytest-cov>=6.0.0", "pre-commit>=4.0.0"]
```

- [ ] **Step 2: uv.lock を更新**

Run: `uv lock`
Expected: ロックファイルが更新され、apache-airflow が optional 側に移動する

- [ ] **Step 3: コミット**

```bash
git add pyproject.toml uv.lock
git commit -m "refactor: apache-airflow を必須依存から dag-dev extra に分離"
```

---

### Task 2: gcp_sync.py の新設（GCP連携の統合）

**Files:**
- Create: `composer_local/gcp_sync.py`
- Modify: `composer_local/utils.py`（関数削除）
- Modify: `composer_local/environment.py:386-388`（describe の import 先変更）

**方針:** 既存5ファイル + utils.py のGCP系関数を移動して1ファイルに集約する。移動はコード変更なし（import の調整のみ）。新規追加はCLI用のグルー関数3つだけ。

- [ ] **Step 1: gcp_sync.py を作成し、既存コードを移動する**

`composer_local/gcp_sync.py` を新規作成。冒頭は以下:

```python
"""GCP 連携モジュール

Cloud Composer / Secret Manager との Variables・設定同期、
gcloud 認証情報の取得をすべてこのモジュールに集約する。
google-cloud-* パッケージは関数内で遅延 import する（gcp extra）。
"""

import json
import logging
import os
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
    "GCP 連携機能には追加パッケージが必要です。\n"
    "  uv sync --extra gcp\n"
    "を実行してください。"
)
```

続けて以下を**そのまま移動**する（コード変更なし、docstring含む）:

| 移動元 | 対象 |
|---|---|
| `utils.py` | `gcloud_cmd`, `get_project_id`, `get_auth_info`, `_auth_result`, `_error_msg_for_returncode`, `check_auth_validity`, `require_gcp_secret_manager`, `require_gcp_composer` |
| `secret_manager_sync.py` | `run_parallel_container_commands`, `mask_value`, `run_command`, `export_variables_via_gcloud`, `SecretManagerSync` クラス全体 |
| `sync_settings.py` | `_compose_env_resource_name`, `fetch_composer_env_details`, `_update_setting`, `write_composer_settings`, `sync_composer_settings` |

移動時の調整:
- `from composer_local.utils import require_gcp_secret_manager` → 同一モジュール内参照になるので import 削除
- `secret_manager_sync.py` 内の `create_sync_client` は移動しない（`SecretManagerSync(...)` 直接生成に置き換えるため廃止）
- `SecretManagerSync.update_secret` に「Secret が存在しない場合は新規作成」処理を統合する（`export_composer_variables.py:85-121` のリカバリロジックの吸収）。メソッド全体を以下に置き換える:

```python
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
            print(f"{constants.ANSI_YELLOW}Secret が存在しないため、新規作成します{constants.ANSI_RESET}")
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
```

- [ ] **Step 2: CLI用グルー関数3つを gcp_sync.py 末尾に追加**

```python
# ---------------------------------------------------------------------------
# CLI エントリポイント用の同期フロー
# ---------------------------------------------------------------------------


def _write_and_import(env, env_path: Path, variables: Dict[str, str]) -> None:
    """variables をローカルへ書き出し、Airflow 起動中なら即時インポートする。"""
    variables_file = env_path / "data" / "variables.json"
    variables_file.parent.mkdir(parents=True, exist_ok=True)
    variables_file.write_text(json.dumps(variables, indent=2, ensure_ascii=False))
    if env.status() == constants.ContainerStatus.RUNNING:
        env.run_airflow_command(
            ["variables", "import", "/home/airflow/gcs/data/variables.json"]
        )
        variables_file.unlink(missing_ok=True)
        print(f"起動中の Airflow に {len(variables)} 件の Variables をインポートしました")
    else:
        print(f"{len(variables)} 件の Variables を保存しました（次回起動時に自動インポート）")


def sync_vars_direct(env, env_path: Path, project: str, location: str, env_name: str) -> None:
    """Cloud Composer から Variables を直接取得してローカルへ反映する（Secret Manager 不使用）。"""
    variables = export_variables_via_gcloud(project, location, env_name)
    if not variables:
        print(f"{constants.ANSI_YELLOW}Composer に Variables が見つかりません{constants.ANSI_RESET}")
        return
    _write_and_import(env, env_path, variables)


def sync_vars_via_secret_manager(
    env, env_path: Path, project: str, location: str, env_name: str, secret_id: str
) -> None:
    """Composer → Secret Manager → ローカルの順に Variables を同期する。"""
    variables = export_variables_via_gcloud(project, location, env_name)
    client = SecretManagerSync(
        project_id=project, local_env_path=env_path, secret_id=secret_id
    )
    changes = client.compare_variables(variables)
    if changes["has_changes"]:
        client.update_secret(secret_id, json.dumps(variables, ensure_ascii=False))
        print(client.format_variables_diff(changes))
    else:
        print(f"{constants.ANSI_YELLOW}Variables に変更はありませんでした。{constants.ANSI_RESET}")
    stored = client.get_all_variables()
    client.clear_airflow_variables_in_container(env)
    _write_and_import(env, env_path, stored)
```

- [ ] **Step 3: utils.py から移動済み関数を削除し、describe 連携を整理**

`utils.py` から以下を削除: `gcloud_cmd`, `get_project_id`, `get_auth_info`, `_auth_result`, `_error_msg_for_returncode`, `check_auth_validity`, `require_gcp_secret_manager`, `require_gcp_composer`, `_GCP_INSTALL_HINT`, `_CLOUD_CLI_*` 定数 3 つ。

`utils.create_plain_status_text` は内部で `check_auth_validity` を呼んでいる（循環import回避のため引数化する）。`create_plain_status_text` の引数 `auth_description: str` を `auth_status: str` に変え、関数内の以下のブロックを削除:

```python
    # 削除するブロック（utils.py:131-141）
    try:
        auth_check = check_auth_validity()
        ...
    add_item("認証情報", auth_status)
```

を、単に `add_item("認証情報", auth_status)` だけ残す形にする。

`environment.py` の `describe()`（386-401行）を以下に変更:

```python
    def describe(self) -> None:
        env_status = self.status()
        web_url = (
            f"http://localhost:{self.port}"
            if env_status == constants.ContainerStatus.RUNNING
            else ""
        )
        env_status_colored = utils.wrap_status_in_color(env_status)

        try:
            from composer_local import gcp_sync

            auth_check = gcp_sync.check_auth_validity()
            gcloud_path = utils.resolve_gcloud_config_path()
            if auth_check["is_valid"]:
                auth_status = utils.wrap_auth_status_in_color(
                    auth_check["auth_info"]["description"], True
                )
            else:
                auth_status = utils.wrap_auth_status_in_color(
                    auth_check["error_message"], False
                )
        except Exception:
            auth_status = "ローカル専用モード（GCP 未設定）"
            gcloud_path = ""

        msg = utils.create_plain_status_text(
            name=self.name,
            state=env_status_colored,
            web_url=web_url,
            image_version=self.image_version,
            dags_path=str(self.dags_path),
            auth_status=auth_status,
            gcloud_path=gcloud_path,
        )
        console.get_console().print(f"\n{msg}\n{constants.FINAL_ENV_MESSAGE}")
```

- [ ] **Step 4: テストを移行（test_gcp_sync.py 新設）**

`tests/test_gcp_sync.py` を新規作成し、以下から代表的なテストを移行する（import を `composer_local.gcp_sync` に変更、`patch` のターゲットパスも `composer_local.gcp_sync.*` に変更）:

- `test_secret_manager_sync.py` から: `mask_value` 系全部、`run_command` 系、`export_variables_via_gcloud` 系、`SecretManagerSync` の `get_secret_value` / `update_secret` / `get_all_variables` / `compare_variables` / `format_variables_diff` の正常系・異常系（同種の重複ケースは1つに絞る）
- `test_sync_settings.py` から: `_update_setting` / `write_composer_settings` / `sync_composer_settings` の全ケース
- `test_utils.py` から: `get_project_id` / `get_auth_info` / `check_auth_validity` 系のテスト（移動して `gcp_sync` 参照に変更）
- 新規: `_write_and_import` のテスト2件:

```python
class TestWriteAndImport:
    def test_running_environment_imports_and_deletes_file(self, tmp_path):
        env = MagicMock()
        env.status.return_value = "running"
        gcp_sync._write_and_import(env, tmp_path, {"KEY": "value"})
        env.run_airflow_command.assert_called_once_with(
            ["variables", "import", "/home/airflow/gcs/data/variables.json"]
        )
        assert not (tmp_path / "data" / "variables.json").exists()

    def test_stopped_environment_keeps_file(self, tmp_path):
        env = MagicMock()
        env.status.return_value = "Not started"
        gcp_sync._write_and_import(env, tmp_path, {"KEY": "value"})
        env.run_airflow_command.assert_not_called()
        saved = json.loads((tmp_path / "data" / "variables.json").read_text())
        assert saved == {"KEY": "value"}
```

旧テストファイル5つを削除: `test_secret_manager_sync.py`, `test_sync_settings.py`, `test_sync_variables.py`, `test_import_variables_to_local.py`, `test_export_composer_variables.py`。`test_utils.py` から移動済み関数のテストを削除。

- [ ] **Step 5: 旧モジュール5ファイルを削除**

```bash
git rm composer_local/secret_manager_sync.py composer_local/sync_settings.py \
       composer_local/sync_variables.py composer_local/export_composer_variables.py \
       composer_local/import_variables_to_local.py
```

注意: この時点で `cli.py` の `sync-vars` / `sync-settings` コマンドが壊れる（import エラー）。Task 3 で cli.py を書き換えるため、Task 2 と Task 3 は**連続して実施し、間でテスト実行しない**。

- [ ] **Step 6: コミットは Task 3 完了後にまとめて行う**（この時点ではコミットしない）

---

### Task 3: CLI 再編（10 → 7 コマンド）

**Files:**
- Modify: `composer_local/cli.py`（全面書き換え）
- Modify: `tests/test_cli.py`

- [ ] **Step 1: cli.py を新コマンド体系に書き換える**

維持するもの: モジュール docstring、`MutuallyExclusiveOption`（start の --image-version/--source-environment 用）、`LogsMaxLines`、`cli` グループ定義、`option_port` / `optional_environment` / `option_location`。

`create` コマンドを削除し、`start` に吸収する。新しい `start`:

```python
@cli.command()
@optional_environment
@option_port
@click.option(
    "--image-version",
    default=None,
    help=f"Composer イメージ バージョン（参考: {constants.COMPOSER_VERSIONING_DOCS_LINK}）",
    show_default="composer_settings.COMPOSER_IMAGE_VERSION",
    metavar="COMPOSER_VERSION",
)
@click.option(
    "-p",
    "--project",
    default=None,
    help="使用する Google Cloud プロジェクト ID",
    metavar="PROJECT_ID",
)
@click.option(
    "--dags-path",
    default=None,
    help="DAGs フォルダのパス（無ければ作成されます）",
    show_default="カレントディレクトリの 'dags'",
    metavar="PATH",
    type=click.Path(file_okay=False),
)
@click.option(
    "--database",
    "database_engine",
    default=constants.DatabaseEngine.postgresql,
    show_default=True,
    type=click.Choice(constants.DatabaseEngine.choices(), case_sensitive=False),
    metavar="DATABASE_ENGINE",
)
@errors.catch_exceptions()
def start(
    environment: Optional[str],
    web_server_port: Optional[int],
    image_version: Optional[str],
    project: Optional[str],
    dags_path: Optional[str],
    database_engine: str,
) -> None:
    """環境を起動する。環境が存在しない場合は自動作成する。"""
    env_name = environment or composer_settings.LOCAL_ENV_NAME
    env_dir = pathlib.Path("composer", env_name)
    if not (env_dir / "config.json").is_file():
        print(f"{constants.ANSI_BLUE}環境が存在しません。作成しています...{constants.ANSI_RESET}")
        utils.assert_environment_name_is_valid(env_name)
        env = composer_environment.Environment(
            image_version=image_version or composer_settings.COMPOSER_IMAGE_VERSION,
            project_id=utils.resolve_project_id(project),
            location=composer_settings.COMPOSER_LOCATION or "asia-northeast1",
            env_dir_path=env_dir,
            port=web_server_port,
            dags_path=dags_path or str(pathlib.Path.cwd() / composer_settings.DAGS_PATH),
            database_engine=database_engine,
        )
        env.create()
    env_path = files.resolve_environment_path(env_name)
    env = composer_environment.Environment.load_from_config(env_path, web_server_port)
    env.start_foreground()
```

`list` と `describe` を削除し `status` に統合:

```python
@cli.command()
@optional_environment
@errors.catch_exceptions()
def status(environment: Optional[str]) -> None:
    """環境の一覧と詳細を表示する。"""
    current_path = pathlib.Path.cwd().resolve()
    envs = files.get_environment_directories()
    if not envs:
        console.get_console().print(constants.ENVIRONMENTS_NOT_FOUND.format(path=current_path))
        return
    environments_status = composer_environment.get_environments_status(envs)
    console.get_console().print(constants.ENVIRONMENTS_FOUND.format(path=current_path))
    console.get_console().print(utils.get_environment_status_table(environments_status))
    if environment or len(envs) == 1:
        env_path = files.resolve_environment_path(environment)
        env = composer_environment.Environment.load_from_config(env_path, None)
        env.describe()
```

`run-airflow` を `run` にリネーム（実装は既存の `run_airflow_cmd` をそのまま使い、`@cli.command(name="run", ...)` に変更。`users create` / `connections add` の特殊メッセージ分岐は削除し、verbose 時のバナーだけ残す）:

```python
@cli.command(name="run", context_settings=dict(ignore_unknown_options=True))
@required_environment
@click.argument("command", nargs=-1, required=True, metavar="COMMAND", type=click.UNPROCESSED)
@click.pass_context
@errors.catch_exceptions()
def run(ctx, environment: Optional[str], command: List[str]):
    """コンテナ内で airflow コマンドを実行する。"""
    if ctx.obj.get("verbose", False):
        print(
            f"{constants.ANSI_BLUE}Airflowコマンドを実行しています: "
            f"{' '.join(command)}{constants.ANSI_RESET}"
        )
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.run_airflow_command([*command])
```

`sync-vars` と `sync-settings` を削除し、新 `sync` コマンドを追加:

```python
@cli.command()
@optional_environment
@click.option("--settings", "settings_only", is_flag=True, default=False,
              help="Variables ではなく Composer の設定を composer_settings.py に同期する")
@click.option("--secret-id", default=None, metavar="SECRET_ID",
              help="指定時は Secret Manager 経由で Variables を同期する")
@click.option("-p", "--project", default=None, metavar="PROJECT_ID",
              help="GCP プロジェクト ID")
@click.option("-l", "--location", default=composer_settings.COMPOSER_LOCATION,
              show_default=True, metavar="LOCATION")
@click.option("-e", "--env-name", "env_name", default=composer_settings.COMPOSER_ENV_NAME,
              show_default=True, metavar="ENV_NAME",
              help="同期元の Cloud Composer 環境名")
@errors.catch_exceptions()
def sync(
    environment: Optional[str],
    settings_only: bool,
    secret_id: Optional[str],
    project: Optional[str],
    location: str,
    env_name: str,
):
    """Cloud Composer から Variables（既定）または設定を同期する。"""
    from composer_local import gcp_sync

    resolved_project = project or composer_settings.PROJECT_ID or gcp_sync.get_project_id()
    if not resolved_project:
        raise click.UsageError(
            "GCP プロジェクト ID を解決できませんでした。--project を指定してください。"
        )
    if not env_name and not settings_only:
        raise click.UsageError(
            "Cloud Composer 環境名が未設定です。--env-name を指定するか "
            "composer_settings.py に COMPOSER_ENV_NAME を設定してください。"
        )

    if settings_only:
        print(f"{constants.ANSI_BLUE}Cloud Composer の設定を同期しています...{constants.ANSI_RESET}")
        settings_path = pathlib.Path(__file__).parent / "composer_settings.py"
        gcp_sync.sync_composer_settings(
            project_id=resolved_project,
            location=location,
            env_name=env_name,
            settings_file=settings_path,
        )
        print(f"{constants.ANSI_GREEN}設定の同期が完了しました: {settings_path}{constants.ANSI_RESET}")
        return

    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    print(f"{constants.ANSI_BLUE}Variables を同期しています...{constants.ANSI_RESET}")
    if secret_id:
        gcp_sync.sync_vars_via_secret_manager(
            env, env_path, resolved_project, location, env_name, secret_id
        )
    else:
        gcp_sync.sync_vars_direct(env, env_path, resolved_project, location, env_name)
    print(f"{constants.ANSI_GREEN}Variables の同期が完了しました。{constants.ANSI_RESET}")
```

`stop` / `logs` / `remove` は現状のまま維持する。

- [ ] **Step 2: test_cli.py を更新**

- `create` 関連テスト → `start` の自動作成テストに書き換え（`Environment.create` と `start_foreground` を `patch` し、config.json 不在時に両方呼ばれること、存在時は `create` が呼ばれないことを検証）
- `list` / `describe` 関連テスト → `status` のテストに統合
- `sync-vars` / `sync-settings` 関連テスト → `sync` のテストに書き換え（`gcp_sync.sync_vars_direct` / `sync_vars_via_secret_manager` / `sync_composer_settings` が適切な引数で呼ばれることを `patch` で検証）
- `run-airflow` → `run` に名称変更

例（新規テストの形）:

```python
def test_sync_uses_secret_manager_when_secret_id_given(runner, tmp_path):
    with patch("composer_local.gcp_sync.sync_vars_via_secret_manager") as mock_sm, \
         patch("composer_local.files.resolve_environment_path") as mock_path, \
         patch("composer_local.environment.Environment.load_from_config"):
        mock_path.return_value = tmp_path
        result = runner.invoke(
            cli, ["sync", "--secret-id", "my-secret", "-p", "proj", "-e", "comp-env"]
        )
        assert result.exit_code == 0
        assert mock_sm.called
```

- [ ] **Step 3: 検証チェックポイント（ユーザー依頼）**

ユーザーに以下の実行を依頼し、結果を確認する:

```
make test
make lint
```

Expected: 全テスト PASS、lint OK。失敗があれば修正してから次へ。

- [ ] **Step 4: コミット（Task 2 + 3 をまとめて）**

```bash
git add -A
git commit -m "refactor: GCP連携を gcp_sync.py に統合し CLI を7コマンドに再編"
```

---

### Task 4: Mixin 解体（docker_ops.py 新設）

**Files:**
- Create: `composer_local/docker_ops.py`
- Modify: `composer_local/environment.py`
- Delete: `composer_local/docker_manager.py`, `composer_local/health_check.py`, `composer_local/initialization.py`
- Modify: `tests/test_environment.py`

- [ ] **Step 1: docker_ops.py を作成**

`composer_local/docker_ops.py` を新規作成。`docker_manager.py` の Mixin メソッドを **`self` を第一引数 `env` に置き換えた module-level 関数**として移動し、`health_check.py` の3関数も同様に移動する。

冒頭:

```python
"""Docker コンテナ・ネットワークの操作とヘルスチェック関数群。

Environment インスタンスを第一引数 env として受け取る純粋な関数の集合。
"""

import io
import logging
import pathlib
import tarfile
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, Tuple

import docker
from docker import errors as docker_errors

from composer_local import composer_settings, constants, errors, files, utils

LOG = logging.getLogger(__name__)

DOCKER_FILES = pathlib.Path(__file__).parent / "docker_files"

CONTAINER_COPY_FILES = [
    DOCKER_FILES / "entrypoint.sh",
    DOCKER_FILES / "run_as_user.sh",
    DOCKER_FILES / "webserver_config.py",
]
```

変換ルール（全関数に機械的に適用）:
- `def _network(self, create=True)` → `def get_network(env, create=True)`、本文の `self.` → `env.`
- 対応表:

| 旧（Mixin メソッド） | 新（docker_ops 関数） |
|---|---|
| `DockerManagerMixin._network` | `get_network(env, create=True)` |
| `DockerManagerMixin._ensure_attached` | `ensure_attached(network, container)`（self 不使用なので env 不要） |
| `DockerManagerMixin._copy_to_container` | `copy_to_container(container, src)`（同上） |
| `DockerManagerMixin._copy_files_to_container` | `copy_files_to_container(container)`（同上） |
| `DockerManagerMixin._warn_if_port_exposed` | `warn_if_port_exposed(service_label)`（同上） |
| `DockerManagerMixin._mounts` | `build_mounts(env, include_db)` |
| `DockerManagerMixin._db_env` | `build_db_env()`（self 不使用） |
| `DockerManagerMixin._get_container` | `get_container(env, name, assert_running=False, ignore_not_found=False)` |
| `DockerManagerMixin._create_db` | `create_db_container(env)` |
| `DockerManagerMixin._create_app` | `create_app_container(env)` |
| `DockerManagerMixin._ensure_containers_running` | `ensure_containers_running(env)` |
| `HealthCheckMixin._poll_until_ready` | `poll_until_ready(check_fn, timeout_seconds, interval_seconds, label, timeout_message)` |
| `HealthCheckMixin._wait_for_db_ready` | `wait_for_db_ready(db, timeout_seconds=60, interval_seconds=2)` |
| `HealthCheckMixin._wait_until_webserver_ready` | `wait_until_webserver_ready(port, timeout_seconds, interval_seconds)`（`self.port` → 引数 `port`） |

関数内の相互呼び出しも書き換える（例: `create_app_container` 内の `self._image_tag()` → `env._image_tag()`、`self._copy_files_to_container(c)` → `copy_files_to_container(c)`、`ensure_containers_running` 内の `self._wait_for_db_ready(db)` → `wait_for_db_ready(db)`、`from composer_local import files` のローカル import は冒頭 import に統合）。

- [ ] **Step 2: environment.py を更新**

1. import を変更: Mixin 3つの import を削除し `from composer_local import docker_ops` を追加
2. クラス定義を `class Environment:` に変更（継承なし）
3. `initialization.py` の全メソッド（`_auto_import_variables`, `_run_airflow_setup_command`, `_setup_google_connection`, `_create_admin_user`, `_first_time_init`, `_show_setup_banner`, `_handle_first_time_init`）を Environment クラス内へそのまま移動（コード変更なし、`json` import を environment.py 冒頭に確認）
4. Mixin メソッド呼び出しを docker_ops 呼び出しに置換:
   - `self._ensure_containers_running()` → `docker_ops.ensure_containers_running(self)`（2箇所: start_foreground, ※start/resume_env は次項で削除）
   - `self._wait_until_webserver_ready(timeout_seconds=..., interval_seconds=...)` → `docker_ops.wait_until_webserver_ready(self.port, timeout_seconds=..., interval_seconds=...)`
   - `self._get_container(...)` → `docker_ops.get_container(self, ...)`（stop / status / logs / run_airflow_command / remove 内）
   - `self._network(create=False)` → `docker_ops.get_network(self, create=False)`（remove 内）
5. **未使用メソッドを削除**: `start()`, `resume_env()`, `restart()`（CLI からは start_foreground / stop しか使われない。make restart は `make stop && make start` で実現）
6. `from_source_environment` クラスメソッドも削除（CLI の create 廃止により呼び出し元消滅）

- [ ] **Step 3: 旧ファイルを削除**

```bash
git rm composer_local/docker_manager.py composer_local/health_check.py composer_local/initialization.py
```

- [ ] **Step 4: test_environment.py を更新**

- `patch("composer_local.docker_manager.X")` / Mixin メソッドの patch → `patch("composer_local.docker_ops.X")` に変更
- `_ensure_containers_running` 等メソッド patch は `docker_ops.ensure_containers_running` の patch に変更
- `start()` / `resume_env()` / `restart()` / `from_source_environment` のテストは削除
- 初期化系（`_first_time_init` 等）のテストはメソッド名そのままなので patch パスを `composer_local.environment.Environment._xxx` に変更するだけ

- [ ] **Step 5: 検証チェックポイント（ユーザー依頼）**

ユーザーに `make test` と `make lint` の実行を依頼。Expected: 全 PASS。

- [ ] **Step 6: コミット**

```bash
git add -A
git commit -m "refactor: Mixin を解体し docker_ops.py のコンポジション構成に変更"
```

---

### Task 5: Makefile 刷新

**Files:**
- Modify: `Makefile`（全面書き換え）
- Delete: `scripts/load_make_settings.py`
- Delete: `scripts/test_gcp_integration.py`（後続 Task 7 でドキュメント代替）

- [ ] **Step 1: Makefile を以下の内容に全面書き換え**

```makefile
.DEFAULT_GOAL := help

# 上書き可能な変数（例: make start ENV=staging PORT=9090）
ENV     ?=
PORT    ?=
LINES   ?= all
FOLLOW  ?=
SETTINGS ?=
SECRET_ID ?=
PROJECT ?=
SERVICE_ACCOUNT ?=

RUN := uv run --active -- composer-local

.PHONY: help import import-dags start stop restart status logs sync auth remove test lint clean

help:
	@echo "利用可能なコマンド:"
	@echo ""
	@echo "  【基本操作】"
	@echo "  import        依存関係のインストールと pre-commit フックの設定（初回のみ）"
	@echo "  import-dags   DAG 開発用に apache-airflow を追加インストール（IDE補完用）"
	@echo "  start         環境を起動（無ければ自動作成）  例: make start PORT=9090"
	@echo "  stop          環境を停止"
	@echo "  restart       環境を再起動"
	@echo ""
	@echo "  【確認】"
	@echo "  status        環境の一覧と詳細を表示"
	@echo "  logs          ログを表示  例: make logs LINES=50 FOLLOW=1"
	@echo ""
	@echo "  【GCP 連携】"
	@echo "  auth          gcloud 認証  例: make auth SERVICE_ACCOUNT=sa@proj.iam.gserviceaccount.com"
	@echo "  sync          Cloud Composer から Variables を同期"
	@echo "                  例: make sync SETTINGS=1（設定同期） make sync SECRET_ID=xxx（SM経由）"
	@echo ""
	@echo "  【メンテナンス】"
	@echo "  remove        環境を削除"
	@echo "  test          テストを実行"
	@echo "  lint          lint とフォーマットチェック"
	@echo "  clean         キャッシュやビルド生成物を削除"
	@echo ""
	@echo "  クイックスタート: make import && make start"

import:
	@uv sync
	@uv run pre-commit install
	@echo "セットアップが完了しました。make start で環境を起動できます。"

import-dags:
	@uv sync --extra dag-dev
	@echo "DAG 開発用パッケージをインストールしました。"

start:
	@if [ ! -d ".venv" ]; then echo "依存関係をインストールしています..."; $(MAKE) import; fi
	@$(RUN) start $(ENV) $(if $(PORT),--port $(PORT))

stop:
	@$(RUN) stop $(ENV)

restart:
	@$(MAKE) stop || true
	@$(MAKE) start

status:
	@$(RUN) status $(ENV)

logs:
	@$(RUN) logs $(ENV) --max-lines $(LINES) $(if $(FOLLOW),--follow)

sync:
	@uv sync --extra gcp --quiet
	@$(RUN) sync $(ENV) \
		$(if $(SETTINGS),--settings) \
		$(if $(SECRET_ID),--secret-id $(SECRET_ID)) \
		$(if $(PROJECT),--project $(PROJECT))

auth:
	@gcloud auth login $(if $(PROJECT),--project $(PROJECT))
	@gcloud auth application-default login \
		$(if $(SERVICE_ACCOUNT),--impersonate-service-account=$(SERVICE_ACCOUNT))
	@echo "認証が完了しました。"

remove:
	@$(RUN) remove $(ENV) --force --skip-confirmation

test:
	@uv run pytest tests/ -v

lint:
	@uv run --active -- ruff check composer_local/ tests/
	@uv run --active -- ruff format --check composer_local/ tests/
	@echo "lint OK"

clean:
	@find . -name "__pycache__" -type d -prune -exec rm -rf {} + || true
	@rm -rf build dist *.egg-info .pytest_cache .coverage || true
```

設計のポイント:
- `$(shell uv run ...)` の事前実行が無いため、すべてのターゲットが即応する
- 環境存在チェック・自動作成は CLI（`start`）の責務に移管済み（Task 3）
- `ENV` 未指定時は CLI 側が `composer_settings.LOCAL_ENV_NAME` または唯一の環境に解決する

- [ ] **Step 2: 不要スクリプトを削除**

```bash
git rm scripts/load_make_settings.py
rm -f .make-settings.mk
```

`.gitignore` から `.make-settings.mk` の行は残してよい（過去のローカルファイル対策）。

- [ ] **Step 3: 動作確認（ユーザー依頼）**

ユーザーに以下を依頼:

```
make help        # 即座に表示されること（Python起動なし）
make test
make lint
```

- [ ] **Step 4: コミット**

```bash
git add -A
git commit -m "refactor: Makefile を14ターゲットに刷新し設定読み込みの Python 起動を廃止"
```

---

### Task 6: シークレット漏洩防止（gitleaks + pre-commit + CI + .gitignore）

**Files:**
- Modify: `.pre-commit-config.yaml`（全面書き換え）
- Modify: `.gitignore`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: .pre-commit-config.yaml を以下に書き換え**

```yaml
repos:
  # 機密情報の検出（gitleaks: baseline 不要で運用が軽い）
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks

  # lint + フォーマット（ruff に統一）
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  # 基本的なチェック
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: ['--maxkb=1000']
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  # Shellスクリプトのチェック
  - repo: https://github.com/shellcheck-py/shellcheck-py
    rev: v0.9.0.6
    hooks:
      - id: shellcheck
```

書き換え後に `uv run pre-commit autoupdate` を実行して rev を最新化してよい（実行できない場合は上記の固定値のままで問題ない）。

- [ ] **Step 2: .gitignore にシークレット系パターンを追加**

`# Composer Local Development (ignore all)` セクションの直前に以下を追加:

```gitignore
# シークレット・認証情報（絶対にコミットしない）
*-key.json
service-account*.json
credentials*.json
variables*.json
.secrets.baseline
```

- [ ] **Step 3: ci.yml に gitleaks ジョブを追加し、py_compile の対象を更新**

`jobs:` の先頭に追加:

```yaml
  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

lint ジョブの `Syntax check` ステップを以下に変更（削除済みファイルを外し、新ファイルを追加）:

```yaml
      - name: Syntax check
        run: uv run python -m py_compile composer_local/cli.py composer_local/environment.py composer_local/docker_ops.py composer_local/gcp_sync.py composer_local/errors.py composer_local/utils.py composer_local/constants.py
```

- [ ] **Step 4: pre-commit フックの動作確認（ユーザー依頼）**

ユーザーに以下を依頼:

```
uv sync
uv run pre-commit install
uv run pre-commit run --all-files
```

Expected: gitleaks / ruff / 基本チェックがすべて Passed（ruff-format による自動修正が入った場合は差分を確認してステージ）。

- [ ] **Step 5: コミット**

```bash
git add .pre-commit-config.yaml .gitignore .github/workflows/ci.yml
git commit -m "feat: gitleaks による多層シークレット漏洩防止を導入"
```

---

### Task 7: ドキュメント更新と最終整理

**Files:**
- Modify: `README.md`
- Modify: `docs/gcp-integration.md`（存在する場合）
- Delete: `scripts/test_gcp_integration.py`

- [ ] **Step 1: scripts/test_gcp_integration.py を削除**

```bash
git rm scripts/test_gcp_integration.py
```

GCP連携の手動検証手順は docs/gcp-integration.md に「`make sync` を実行して Variables が同期されることを確認する」という形で記載する（Step 3）。

- [ ] **Step 2: README.md を新コマンド体系に更新**

更新箇所:
- クイックスタート: `make import && make start`（変更なし、ただし import が数秒で済む旨を追記）
- 「停止と再起動」表: stop / start / restart / remove の4行に更新
- コマンド一覧表を新 Makefile の14ターゲットに差し替え
- 新セクション「DAG 開発時の IDE 補完」を追加:

```markdown
## DAG 開発時の IDE 補完（任意）

CLI 本体は Airflow に依存しないため、デフォルトではエディタで `from airflow import DAG` の
補完が効きません。DAG を本格的に書く場合は以下を実行してください:

​```bash
make import-dags
​```

これで `apache-airflow`（コンテナと同一バージョン）がローカルの venv に入り、
IDE の補完・型チェックが有効になります。日常の環境起動には不要です。
```

- 新セクション「シークレット管理」を追加:

```markdown
## シークレット管理

このリポジトリは多層防御でシークレットのコミット混入を防ぎます:

- `make import` 時に pre-commit フック（gitleaks / private key 検出）が自動で有効化されます
- CI でも gitleaks スキャンが実行されます
- 同期した Variables は gitignore 済みの `composer/` 配下にのみ保存されます
- `composer_settings.py` は gitignore 済みです（コミットされるのは `.example` のみ）
```

- `sync-vars` / `sync-vars-sm` / `sync-settings` / `auth-user` / `auth-sa` への言及をすべて `sync` / `auth` に書き換え

- [ ] **Step 3: docs/gcp-integration.md を更新**

`make sync`（直接同期）、`make sync SECRET_ID=xxx`（Secret Manager 経由）、`make sync SETTINGS=1`（設定同期）、`make auth` / `make auth SERVICE_ACCOUNT=xxx` の新体系で書き換える。手動検証手順として「`make auth` → `make start` → 別ターミナルで `make sync` → Airflow UI の Admin > Variables で同期結果を確認」を記載する。

- [ ] **Step 4: 最終検証チェックポイント（ユーザー依頼）**

ユーザーに以下のフル動作確認を依頼:

```
make clean && rm -rf .venv
make import          # 数秒で完了すること（Airflow をダウンロードしない）
make help            # 即座に表示されること
make test            # 全テスト PASS
make lint            # OK
make start           # 環境が起動し Web UI にアクセスできること
make status          # 別ターミナルで一覧+詳細表示
make stop
```

- [ ] **Step 5: コミット**

```bash
git add -A
git commit -m "docs: README と GCP 連携ドキュメントを新コマンド体系に更新"
```

---

## セルフレビュー結果（作成時実施済み）

- 設計書の全8セクションをタスクにマッピング済み（1→Task1, 2→Task2+3, 3→Task4, 4→Task5, 5→Task3, 6→Task2/3/4のテスト手順+Task5/7, 7→Task7, 8→Task6）
- Task 2 Step 5 の時点で cli.py が一時的に壊れるため、Task 2 と Task 3 は連続実施・一括コミットとする制約を明記済み
- `create_plain_status_text` の引数名変更（`auth_description` → `auth_status`）は Task 2 Step 3 と environment.describe の呼び出しで一致していることを確認済み
- docker_ops の関数名は Task 4 の対応表と environment.py の置換指示で一致していることを確認済み
```
