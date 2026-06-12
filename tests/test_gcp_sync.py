"""composer_local.gcp_sync のユニットテスト.

GCP Secret Manager API、Composer API、Docker API、subprocess をモック化してテストする。
旧 test_secret_manager_sync / test_sync_settings のテストを統合している。
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from composer_local import errors, gcp_sync
from composer_local.gcp_sync import (
    SecretManagerSync,
    _compose_env_resource_name,
    export_variables_via_gcloud,
    fetch_composer_env_details,
    mask_value,
    run_command,
    run_parallel_container_commands,
    sync_composer_settings,
    write_composer_settings,
)

# =============================================================================
# mask_value のテスト
# =============================================================================


class TestMaskValue:
    """mask_value 関数のテスト."""

    def test_long_value_is_masked(self):
        """十分に長い文字列はプレフィックスとサフィックスのみ表示される."""
        result = mask_value("abcdefghijklmnop")
        assert result == "abcd...mnop"

    def test_short_value_returns_asterisks(self):
        """短い文字列は '***' にマスキングされる."""
        assert mask_value("short") == "***"

    def test_exact_boundary_value(self):
        """プレフィックス長+サフィックス長に等しい文字列は '***' になる."""
        assert mask_value("12345678") == "***"

    def test_boundary_plus_one(self):
        """プレフィックス+サフィックス+1 の長さの文字列はマスクされる."""
        assert mask_value("123456789") == "1234...6789"

    def test_empty_string(self):
        """空文字列は '***' にマスキングされる."""
        assert mask_value("") == "***"


# =============================================================================
# run_command のテスト
# =============================================================================


class TestRunCommand:
    """run_command 関数のテスト."""

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_successful_command(self, mock_run):
        """正常にコマンドが実行された場合、stdout が返される."""
        mock_run.return_value = MagicMock(stdout="output text", returncode=0)
        result = run_command(["echo", "hello"])
        assert result == "output text"
        mock_run.assert_called_once_with(
            ["echo", "hello"], check=True, capture_output=True, text=True
        )

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_failed_command_raises_runtime_error(self, mock_run):
        """コマンドが失敗した場合、RuntimeError が発生する."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["gcloud", "test"], output="some output", stderr="some error",
        )
        with pytest.raises(RuntimeError, match="コマンドの実行に失敗しました"):
            run_command(["gcloud", "test"])

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_failed_command_includes_stderr(self, mock_run):
        """エラー時にstderr情報が含まれる."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=2, cmd=["gcloud", "test"], output="", stderr="permission denied",
        )
        with pytest.raises(RuntimeError, match="permission denied"):
            run_command(["gcloud", "test"])


# =============================================================================
# export_variables_via_gcloud のテスト
# =============================================================================


class TestExportVariablesViaGcloud:
    """export_variables_via_gcloud 関数のテスト."""

    @patch("composer_local.gcp_sync.run_command")
    def test_valid_json_output(self, mock_run_command):
        """正常な JSON 出力から Variables を取得できる."""
        mock_run_command.return_value = '{"key1": "value1", "key2": "value2"}'
        result = export_variables_via_gcloud("my-project", "us-central1", "my-env")
        assert result == {"key1": "value1", "key2": "value2"}

    @patch("composer_local.gcp_sync.run_command")
    def test_json_with_extra_output(self, mock_run_command):
        """gcloud の余計な出力が混ざっても JSON を抽出できる."""
        mock_run_command.return_value = (
            "kubeconfig entry generated for my-env.\n"
            '{"key1": "value1"}\n'
            "Operation completed."
        )
        assert export_variables_via_gcloud("p", "l", "e") == {"key1": "value1"}

    @patch("composer_local.gcp_sync.run_command")
    def test_empty_values_excluded(self, mock_run_command):
        """空値の変数は除外される."""
        mock_run_command.return_value = '{"key1": "value1", "key2": "", "key3": null}'
        assert export_variables_via_gcloud("p", "l", "e") == {"key1": "value1"}

    @patch("composer_local.gcp_sync.run_command")
    def test_no_json_in_output_raises_error(self, mock_run_command):
        """出力に JSON が含まれない場合 RuntimeError が発生する."""
        mock_run_command.return_value = "no json here"
        with pytest.raises(RuntimeError, match="JSON の抽出に失敗"):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.gcp_sync.run_command")
    def test_array_json_raises_extraction_error(self, mock_run_command):
        """JSON 配列の場合、{} が見つからず抽出エラーが発生する."""
        mock_run_command.return_value = '["item1", "item2"]'
        with pytest.raises(RuntimeError, match="JSON の抽出に失敗"):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.gcp_sync.run_command")
    def test_invalid_json_raises_error(self, mock_run_command):
        """不正な JSON の場合エラーが発生する."""
        mock_run_command.return_value = "{invalid json}"
        with pytest.raises(Exception):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.gcp_sync.run_command")
    def test_gcloud_command_arguments(self, mock_run_command):
        """gcloud コマンドに正しい引数が渡される."""
        mock_run_command.return_value = '{"k": "v"}'
        export_variables_via_gcloud("test-proj", "asia-east1", "test-env")
        args = mock_run_command.call_args[0][0]
        assert "gcloud" in args
        assert "--project" in args
        assert "test-proj" in args
        assert "test-env" in args
        assert "asia-east1" in args


# =============================================================================
# run_parallel_container_commands のテスト
# =============================================================================


class TestRunParallelContainerCommands:
    """run_parallel_container_commands 関数のテスト."""

    def test_empty_commands_returns_zero(self):
        """空のコマンド辞書では (0, 0) を返す."""
        success, failure = run_parallel_container_commands(MagicMock(), {})
        assert (success, failure) == (0, 0)

    def test_all_commands_succeed(self):
        """全コマンドが成功する場合."""
        app = MagicMock()
        app.exec_run.return_value = MagicMock(exit_code=0, output=b"ok")
        commands = {"cmd1": ["echo", "1"], "cmd2": ["echo", "2"]}
        success, failure = run_parallel_container_commands(app, commands, max_workers=2)
        assert success == 2
        assert failure == 0

    def test_some_commands_fail(self):
        """一部のコマンドが失敗する場合."""
        app = MagicMock()
        app.exec_run.side_effect = [
            MagicMock(exit_code=0, output=b"ok"),
            MagicMock(exit_code=1, output=b"error"),
        ]
        commands = {"cmd1": ["echo", "1"], "cmd2": ["echo", "2"]}
        success, failure = run_parallel_container_commands(app, commands, max_workers=1)
        assert success + failure == 2
        assert failure >= 1

    def test_command_raises_exception(self):
        """コマンド実行中に例外が発生した場合."""
        app = MagicMock()
        app.exec_run.side_effect = Exception("Docker error")
        success, failure = run_parallel_container_commands(
            app, {"cmd1": ["echo", "1"]}, max_workers=1
        )
        assert success == 0
        assert failure == 1


# =============================================================================
# SecretManagerSync のテスト
# =============================================================================


class TestSecretManagerSyncInit:
    """SecretManagerSync.__init__ のテスト."""

    def test_init_default_values(self):
        """デフォルト値で正しく初期化される."""
        sync = SecretManagerSync(project_id="test-project")
        assert sync.project_id == "test-project"
        assert sync.local_env_path is None
        assert sync.client is None

    def test_init_with_custom_secret_id(self):
        """カスタム secret_id で初期化できる."""
        sync = SecretManagerSync(project_id="p", secret_id="custom-secret")
        assert sync.secret_id == "custom-secret"


class TestSecretManagerSyncGetClient:
    """SecretManagerSync._get_client のテスト."""

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_creates_client_on_first_call(self, mock_require):
        """初回呼び出し時にクライアントが作成される."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p")
        assert sync._get_client() == mock_client

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_reuses_existing_client(self, mock_require):
        """既にクライアントがある場合は再利用する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p")
        assert sync._get_client() is sync._get_client()
        assert mock_secretmanager.SecretManagerServiceClient.call_count == 1

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_default_credentials_error_raises_composer_error(self, mock_require):
        """DefaultCredentialsError が発生した場合、ComposerCliError に変換される."""
        mock_secretmanager = MagicMock()

        class FakeDefaultCredentialsError(Exception):
            pass

        mock_secretmanager.SecretManagerServiceClient.side_effect = FakeDefaultCredentialsError(
            "no creds"
        )
        mock_require.return_value = (mock_secretmanager, FakeDefaultCredentialsError)

        sync = SecretManagerSync(project_id="p")
        with pytest.raises(errors.ComposerCliError, match="認証情報が見つかりません"):
            sync._get_client()


class TestSecretManagerSyncGetSecretValue:
    """SecretManagerSync.get_secret_value のテスト."""

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_returns_secret_value(self, mock_require):
        """Secret の値が正しく取得される."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '{"key": "value"}'
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="test-secret")
        assert sync.get_secret_value() == '{"key": "value"}'

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_api_error_raises_composer_error(self, mock_require):
        """API エラー時に ComposerCliError が発生する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)
        mock_client.access_secret_version.side_effect = Exception("API error")

        sync = SecretManagerSync(project_id="p", secret_id="test-secret")
        with pytest.raises(errors.ComposerCliError, match="Secret の取得に失敗"):
            sync.get_secret_value()


class TestSecretManagerSyncUpdateSecret:
    """SecretManagerSync.update_secret のテスト."""

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_update_secret_success(self, mock_require):
        """Secret の更新が成功する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p", secret_id="test-secret")
        sync.update_secret("test-secret", "new value")

        mock_client.add_secret_version.assert_called_once()
        call_args = mock_client.add_secret_version.call_args
        assert call_args[1]["request"]["parent"] == "projects/p/secrets/test-secret"
        assert call_args[1]["request"]["payload"]["data"] == b"new value"

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_update_secret_uses_default_secret_id(self, mock_require):
        """secret_id が None の場合、デフォルトの secret_id が使われる."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p", secret_id="default-id")
        sync.update_secret(None, "value")

        call_args = mock_client.add_secret_version.call_args
        assert call_args[1]["request"]["parent"] == "projects/p/secrets/default-id"

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_creates_secret_when_not_found(self, mock_require):
        """Secret が存在しない場合は新規作成してからバージョンを追加する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        # 1 回目の add_secret_version は not found で失敗、create 後の 2 回目は成功
        mock_client.add_secret_version.side_effect = [Exception("Secret not found"), None]

        sync = SecretManagerSync(project_id="p", secret_id="missing")
        sync.update_secret("missing", "value")

        mock_client.create_secret.assert_called_once()
        assert mock_client.add_secret_version.call_count == 2

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_update_secret_unrecoverable_error_raises(self, mock_require):
        """回復不能なエラーの場合は ComposerCliError を送出する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)
        mock_client.add_secret_version.side_effect = Exception("permission denied")

        sync = SecretManagerSync(project_id="p", secret_id="s")
        with pytest.raises(errors.ComposerCliError, match="Secret の更新に失敗"):
            sync.update_secret("s", "value")


class TestSecretManagerSyncGetAllVariables:
    """SecretManagerSync.get_all_variables のテスト."""

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_returns_variables_dict(self, mock_require):
        """正常な JSON から Variables 辞書が返される."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '{"key1": "val1", "key2": "val2"}'
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="s")
        assert sync.get_all_variables() == {"key1": "val1", "key2": "val2"}

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_non_dict_json_raises_error(self, mock_require):
        """JSON がオブジェクトでない場合 ValueError が発生する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '["not", "a", "dict"]'
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="s")
        with pytest.raises(ValueError, match="JSON オブジェクトではありません"):
            sync.get_all_variables()


class TestSecretManagerSyncCompareVariables:
    """SecretManagerSync.compare_variables のテスト."""

    def test_no_changes(self):
        """変更がない場合 has_changes が False."""
        sync = SecretManagerSync(project_id="p")
        old = {"key1": "val1", "key2": "val2"}
        result = sync.compare_variables(dict(old), old)
        assert result["has_changes"] is False
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_mixed_changes(self):
        """追加・削除・変更が混在する場合."""
        sync = SecretManagerSync(project_id="p")
        old = {"keep": "same", "modify": "old", "remove": "gone"}
        new = {"keep": "same", "modify": "new", "add": "fresh"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is True
        assert result["added"] == {"add": "fresh"}
        assert result["removed"] == {"remove": "gone"}
        assert result["modified"] == {"modify": {"old_value": "old", "new_value": "new"}}

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_old_variables_none_fetches_from_secret_manager(self, mock_require):
        """old_variables が None の場合、Secret Manager から取得する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '{"old_key": "old_val"}'
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="s")
        result = sync.compare_variables({"new_key": "new_val"})
        assert result["has_changes"] is True
        assert result["added"] == {"new_key": "new_val"}
        assert result["removed"] == {"old_key": "old_val"}

    @patch("composer_local.gcp_sync.require_gcp_secret_manager")
    def test_old_variables_none_secret_not_found(self, mock_require):
        """old_variables が None で Secret が存在しない場合、全てが新規追加扱い."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)
        mock_client.access_secret_version.side_effect = Exception("not found")

        sync = SecretManagerSync(project_id="p", secret_id="s")
        new_vars = {"key1": "val1", "key2": "val2"}
        result = sync.compare_variables(new_vars)
        assert result["has_changes"] is True
        assert result["added"] == new_vars


class TestSecretManagerSyncFormatVariablesDiff:
    """SecretManagerSync.format_variables_diff のテスト."""

    def test_no_changes(self):
        """変更がない場合のフォーマット."""
        sync = SecretManagerSync(project_id="p")
        changes = {"has_changes": False, "added": {}, "removed": {}, "modified": {}}
        assert sync.format_variables_diff(changes) == "変更はありません"

    def test_added_variables_format(self):
        """追加された変数のフォーマットに '+' が含まれる."""
        sync = SecretManagerSync(project_id="p")
        changes = {
            "has_changes": True,
            "added": {"new_key": "new_value_long_enough"},
            "removed": {},
            "modified": {},
        }
        result = sync.format_variables_diff(changes)
        assert "+" in result
        assert "new_key" in result

    def test_modified_variables_format(self):
        """変更された変数のフォーマットに '~' が含まれる."""
        sync = SecretManagerSync(project_id="p")
        changes = {
            "has_changes": True,
            "added": {},
            "removed": {},
            "modified": {
                "mod_key": {
                    "old_value": "old_value_long_enough",
                    "new_value": "new_value_long_enough",
                }
            },
        }
        result = sync.format_variables_diff(changes)
        assert "~" in result
        assert "mod_key" in result


class TestSecretManagerSyncClearAirflowVariablesInContainer:
    """SecretManagerSync.clear_airflow_variables_in_container のテスト."""

    def test_skips_when_not_running(self):
        """コンテナが実行中でない場合はスキップする."""
        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"
        sync = SecretManagerSync(project_id="p")
        sync.clear_airflow_variables_in_container(mock_env)
        mock_env._get_container.assert_not_called()

    def test_handles_exception_gracefully(self):
        """例外が発生した場合でもエラーにならない."""
        mock_env = MagicMock()
        mock_env.status.side_effect = Exception("docker error")
        sync = SecretManagerSync(project_id="p")
        # 例外が外に伝播しないこと
        sync.clear_airflow_variables_in_container(mock_env)


# =============================================================================
# Composer 設定同期のテスト
# =============================================================================


class TestComposeEnvResourceName:
    """_compose_env_resource_name 関数のテスト."""

    def test_basic_resource_name(self):
        """基本的なリソース名が正しくフォーマットされる."""
        result = _compose_env_resource_name("my-project", "us-central1", "my-env")
        assert result == "projects/my-project/locations/us-central1/environments/my-env"


class TestFetchComposerEnvDetails:
    """fetch_composer_env_details 関数のテスト."""

    @patch("composer_local.gcp_sync.require_gcp_composer")
    def test_returns_env_details(self, mock_require):
        """環境詳細が正しく取得される."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1
        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client

        mock_env = MagicMock()
        mock_env.config.software_config.image_version = "composer-3-airflow-2.10.5"
        mock_env.config.software_config.python_version = "3"
        mock_client.get_environment.return_value = mock_env

        result = fetch_composer_env_details("proj", "us-central1", "my-env")
        assert result["env_name"] == "my-env"
        assert result["location"] == "us-central1"
        assert result["image_version"] == "composer-3-airflow-2.10.5"
        assert result["python_version"] == "3"

    @patch("composer_local.gcp_sync.require_gcp_composer")
    def test_api_error_raises_composer_error(self, mock_require):
        """API エラーが ComposerCliError に変換される."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1
        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client
        mock_client.get_environment.side_effect = Exception("API error")

        with pytest.raises(errors.ComposerCliError, match="取得に失敗"):
            fetch_composer_env_details("proj", "loc", "env")

    @patch("composer_local.gcp_sync.require_gcp_composer")
    def test_correct_resource_name_in_request(self, mock_require):
        """正しいリソース名が API リクエストに渡される."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1
        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client

        mock_env = MagicMock()
        mock_env.config.software_config.image_version = "composer-3-airflow-2.10.5"
        mock_env.config.software_config.python_version = ""
        mock_client.get_environment.return_value = mock_env

        fetch_composer_env_details("my-proj", "us-west1", "my-env")
        mock_client.get_environment.assert_called_once_with(
            request={"name": "projects/my-proj/locations/us-west1/environments/my-env"}
        )


class TestWriteComposerSettings:
    """write_composer_settings 関数のテスト."""

    def test_writes_settings_file(self, tmp_path):
        """設定ファイルが正しく書き出される."""
        settings_path = tmp_path / "composer_settings.py"
        write_composer_settings(
            settings_path,
            env_name="test-env",
            location="us-central1",
            image_version="composer-3-airflow-2.10.5",
            python_version="3",
        )
        content = settings_path.read_text()
        assert 'COMPOSER_ENV_NAME = "test-env"' in content
        assert 'COMPOSER_LOCATION = "us-central1"' in content
        assert 'COMPOSER_IMAGE_VERSION = "composer-3-airflow-2.10.5"' in content
        assert 'COMPOSER_PYTHON_VERSION = "3"' in content

    def test_writes_empty_python_version(self, tmp_path):
        """python_version が None の場合、空文字列として書き出される."""
        settings_path = tmp_path / "composer_settings.py"
        write_composer_settings(
            settings_path,
            env_name="env",
            location="loc",
            image_version="composer-2.9.7-airflow-2.9.3",
            python_version=None,
        )
        assert 'COMPOSER_PYTHON_VERSION = ""' in settings_path.read_text()

    def test_preserves_existing_settings(self, tmp_path):
        """既存の設定を保持しつつ Composer 関連の値のみ更新する."""
        settings_path = tmp_path / "composer_settings.py"
        settings_path.write_text(
            'PROJECT_ID = "my-project"\n'
            'COMPOSER_IMAGE_VERSION = "old-version"\n'
            'SECRET_ID = "my-secret"\n'
        )
        write_composer_settings(
            settings_path,
            env_name="new-env",
            location="new-loc",
            image_version="composer-3-airflow-2.10.5",
            python_version="3",
        )
        content = settings_path.read_text()
        assert 'PROJECT_ID = "my-project"' in content
        assert 'SECRET_ID = "my-secret"' in content
        assert 'COMPOSER_IMAGE_VERSION = "composer-3-airflow-2.10.5"' in content
        assert 'COMPOSER_ENV_NAME = "new-env"' in content

    def test_adds_missing_keys(self, tmp_path):
        """既存ファイルに Composer 設定がない場合、追加する."""
        settings_path = tmp_path / "composer_settings.py"
        settings_path.write_text('PROJECT_ID = "my-project"\n')
        write_composer_settings(settings_path, "e", "l", "v", "p")
        content = settings_path.read_text()
        assert 'PROJECT_ID = "my-project"' in content
        assert 'COMPOSER_ENV_NAME = "e"' in content
        assert 'COMPOSER_IMAGE_VERSION = "v"' in content


class TestSyncComposerSettings:
    """sync_composer_settings 関数のテスト."""

    @patch("composer_local.gcp_sync.fetch_composer_env_details")
    def test_syncs_settings_end_to_end(self, mock_fetch, tmp_path):
        """fetch から write まで一連の処理が正しく動作する."""
        mock_fetch.return_value = {
            "env_name": "prod-env",
            "location": "asia-east1",
            "image_version": "composer-3-airflow-2.10.5",
            "python_version": "3",
        }
        settings_path = tmp_path / "composer_settings.py"
        sync_composer_settings("my-proj", "asia-east1", "prod-env", settings_path)
        content = settings_path.read_text()
        assert 'COMPOSER_ENV_NAME = "prod-env"' in content
        assert 'COMPOSER_LOCATION = "asia-east1"' in content

    @patch("composer_local.gcp_sync.fetch_composer_env_details")
    def test_sync_passes_correct_arguments(self, mock_fetch, tmp_path):
        """正しい引数が fetch_composer_env_details に渡される."""
        mock_fetch.return_value = {
            "env_name": "env", "location": "loc", "image_version": "v", "python_version": "",
        }
        settings_path = tmp_path / "settings.py"
        sync_composer_settings("project-id", "us-west1", "env-name", settings_path)
        mock_fetch.assert_called_once_with("project-id", "us-west1", "env-name")

    @patch("composer_local.gcp_sync.fetch_composer_env_details")
    def test_sync_with_fetch_error(self, mock_fetch, tmp_path):
        """fetch_composer_env_details がエラーの場合、そのまま伝播する."""
        mock_fetch.side_effect = errors.ComposerCliError("fetch failed")
        settings_path = tmp_path / "settings.py"
        with pytest.raises(errors.ComposerCliError, match="fetch failed"):
            sync_composer_settings("p", "l", "e", settings_path)


# =============================================================================
# 認証情報の取得・検証のテスト
# =============================================================================


class TestGetProjectId:
    """get_project_id 関数のテスト."""

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_returns_project_id(self, mock_run):
        """gcloud 設定から project id を取得できる."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps(
                {"configuration": {"properties": {"core": {"project": "my-proj"}}}}
            )
        )
        assert gcp_sync.get_project_id() == "my-proj"

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_missing_project_raises(self, mock_run):
        """設定に project id が無い場合 ComposerCliError を送出する."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps({"configuration": {"properties": {"core": {}}}})
        )
        with pytest.raises(errors.ComposerCliError):
            gcp_sync.get_project_id()

    @patch("composer_local.gcp_sync.subprocess.run")
    def test_cli_failure_raises_invalid_auth(self, mock_run):
        """gcloud 実行失敗時に InvalidAuthError を送出する."""
        mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd=["gcloud"])
        with pytest.raises(errors.InvalidAuthError):
            gcp_sync.get_project_id()


class TestGetAuthInfo:
    """get_auth_info 関数のテスト."""

    @patch("composer_local.gcp_sync.subprocess.run")
    @patch("composer_local.utils.resolve_gcloud_config_path")
    def test_returns_user_auth(self, mock_path, mock_run, tmp_path):
        """ADC が無い場合、ユーザー認証情報を返す."""
        mock_path.return_value = str(tmp_path)
        mock_run.return_value = MagicMock(stdout="user@example.com\n")
        result = gcp_sync.get_auth_info()
        assert result["type"] == "user"
        assert result["account"] == "user@example.com"

    @patch("composer_local.gcp_sync.subprocess.run")
    @patch("composer_local.utils.resolve_gcloud_config_path")
    def test_returns_service_account_from_adc(self, mock_path, mock_run, tmp_path):
        """impersonated_service_account の ADC からサービスアカウントを抽出する."""
        adc = tmp_path / "application_default_credentials.json"
        adc.write_text(json.dumps({
            "type": "impersonated_service_account",
            "service_account_impersonation_url": (
                "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
                "sa@proj.iam.gserviceaccount.com:generateAccessToken"
            ),
        }))
        mock_path.return_value = str(tmp_path)
        result = gcp_sync.get_auth_info()
        assert result["type"] == "service_account"
        assert result["account"] == "sa@proj.iam.gserviceaccount.com"

    @patch("composer_local.gcp_sync.subprocess.run")
    @patch("composer_local.utils.resolve_gcloud_config_path")
    def test_returns_unknown_on_error(self, mock_path, mock_run, tmp_path):
        """例外発生時は unknown を返す."""
        mock_path.return_value = str(tmp_path)
        mock_run.side_effect = OSError("gcloud not found")
        result = gcp_sync.get_auth_info()
        assert result["type"] == "unknown"


class TestCheckAuthValidity:
    """check_auth_validity 関数のテスト."""

    @patch("composer_local.gcp_sync.get_auth_info")
    def test_unknown_auth_is_invalid(self, mock_auth):
        """認証情報が unknown の場合 is_valid が False."""
        mock_auth.return_value = {"type": "unknown", "account": "不明"}
        result = gcp_sync.check_auth_validity()
        assert result["is_valid"] is False
        assert result["error_message"] == "認証情報が見つかりません"

    @patch("composer_local.gcp_sync.subprocess.run")
    @patch("composer_local.gcp_sync.get_auth_info")
    def test_valid_user_auth(self, mock_auth, mock_run):
        """ユーザー認証が有効な場合 is_valid が True."""
        mock_auth.return_value = {"type": "user", "account": "user@example.com"}
        mock_run.return_value = MagicMock(stdout="my-proj\n")
        result = gcp_sync.check_auth_validity()
        assert result["is_valid"] is True

    @patch("composer_local.gcp_sync.subprocess.run")
    @patch("composer_local.gcp_sync.get_auth_info")
    def test_no_project_set_is_invalid(self, mock_auth, mock_run):
        """プロジェクト未設定の場合 is_valid が False."""
        mock_auth.return_value = {"type": "user", "account": "user@example.com"}
        mock_run.return_value = MagicMock(stdout="\n")
        result = gcp_sync.check_auth_validity()
        assert result["is_valid"] is False
        assert "プロジェクト" in result["error_message"]


# =============================================================================
# _write_and_import のテスト
# =============================================================================


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
