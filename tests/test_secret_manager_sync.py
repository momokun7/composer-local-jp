"""composer_local.secret_manager_sync のユニットテスト.

GCP Secret Manager API、Docker API、subprocess をモック化してテストする。
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from composer_local import constants, errors
from composer_local.secret_manager_sync import (
    SecretManagerSync,
    create_sync_client,
    export_variables_via_gcloud,
    mask_value,
    run_command,
    run_parallel_container_commands,
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
        result = mask_value("short")
        assert result == "***"

    def test_exact_boundary_value(self):
        """プレフィックス長+サフィックス長に等しい文字列は '***' になる."""
        # デフォルト: MASK_PREFIX_LENGTH=4, MASK_SUFFIX_LENGTH=4 なので 8 文字以下は ***
        result = mask_value("12345678")
        assert result == "***"

    def test_boundary_plus_one(self):
        """プレフィックス+サフィックス+1 の長さの文字列はマスクされる."""
        result = mask_value("123456789")
        assert result == "1234...6789"

    def test_empty_string(self):
        """空文字列は '***' にマスキングされる."""
        result = mask_value("")
        assert result == "***"

    def test_single_char(self):
        """1文字は '***' にマスキングされる."""
        result = mask_value("a")
        assert result == "***"


# =============================================================================
# run_command のテスト
# =============================================================================


class TestRunCommand:
    """run_command 関数のテスト."""

    @patch("composer_local.secret_manager_sync.subprocess.run")
    def test_successful_command(self, mock_run):
        """正常にコマンドが実行された場合、stdout が返される."""
        mock_run.return_value = MagicMock(stdout="output text", returncode=0)
        result = run_command(["echo", "hello"])
        assert result == "output text"
        mock_run.assert_called_once_with(
            ["echo", "hello"], check=True, capture_output=True, text=True
        )

    @patch("composer_local.secret_manager_sync.subprocess.run")
    def test_failed_command_raises_runtime_error(self, mock_run):
        """コマンドが失敗した場合、RuntimeError が発生する."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gcloud", "test"],
            output="some output",
            stderr="some error",
        )
        with pytest.raises(RuntimeError, match="コマンドの実行に失敗しました"):
            run_command(["gcloud", "test"])

    @patch("composer_local.secret_manager_sync.subprocess.run")
    def test_failed_command_includes_stderr(self, mock_run):
        """エラー時にstderr情報が含まれる."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=2,
            cmd=["gcloud", "test"],
            output="",
            stderr="permission denied",
        )
        with pytest.raises(RuntimeError, match="permission denied"):
            run_command(["gcloud", "test"])


# =============================================================================
# export_variables_via_gcloud のテスト
# =============================================================================


class TestExportVariablesViaGcloud:
    """export_variables_via_gcloud 関数のテスト."""

    @patch("composer_local.secret_manager_sync.run_command")
    def test_valid_json_output(self, mock_run_command):
        """正常な JSON 出力から Variables を取得できる."""
        mock_run_command.return_value = '{"key1": "value1", "key2": "value2"}'
        result = export_variables_via_gcloud("my-project", "us-central1", "my-env")
        assert result == {"key1": "value1", "key2": "value2"}

    @patch("composer_local.secret_manager_sync.run_command")
    def test_json_with_extra_output(self, mock_run_command):
        """gcloud の余計な出力が混ざっても JSON を抽出できる."""
        mock_run_command.return_value = (
            "kubeconfig entry generated for my-env.\n"
            '{"key1": "value1"}\n'
            "Operation completed."
        )
        result = export_variables_via_gcloud("p", "l", "e")
        assert result == {"key1": "value1"}

    @patch("composer_local.secret_manager_sync.run_command")
    def test_empty_values_excluded(self, mock_run_command):
        """空値の変数は除外される."""
        mock_run_command.return_value = '{"key1": "value1", "key2": "", "key3": null}'
        result = export_variables_via_gcloud("p", "l", "e")
        assert result == {"key1": "value1"}

    @patch("composer_local.secret_manager_sync.run_command")
    def test_no_json_in_output_raises_error(self, mock_run_command):
        """出力に JSON が含まれない場合 RuntimeError が発生する."""
        mock_run_command.return_value = "no json here"
        with pytest.raises(RuntimeError, match="JSON の抽出に失敗"):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.secret_manager_sync.run_command")
    def test_array_json_raises_extraction_error(self, mock_run_command):
        """JSON 配列の場合、{} が見つからず抽出エラーが発生する."""
        mock_run_command.return_value = '["item1", "item2"]'
        with pytest.raises(RuntimeError, match="JSON の抽出に失敗"):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.secret_manager_sync.run_command")
    def test_invalid_json_raises_error(self, mock_run_command):
        """不正な JSON の場合エラーが発生する."""
        mock_run_command.return_value = "{invalid json}"
        with pytest.raises(Exception):
            export_variables_via_gcloud("p", "l", "e")

    @patch("composer_local.secret_manager_sync.run_command")
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
        app = MagicMock()
        success, failure = run_parallel_container_commands(app, {})
        assert success == 0
        assert failure == 0

    def test_all_commands_succeed(self):
        """全コマンドが成功する場合."""
        app = MagicMock()
        app.exec_run.return_value = MagicMock(exit_code=0, output=b"ok")
        commands = {
            "cmd1": ["echo", "1"],
            "cmd2": ["echo", "2"],
        }
        success, failure = run_parallel_container_commands(app, commands, max_workers=2)
        assert success == 2
        assert failure == 0

    def test_some_commands_fail(self):
        """一部のコマンドが失敗する場合."""
        app = MagicMock()
        results = [
            MagicMock(exit_code=0, output=b"ok"),
            MagicMock(exit_code=1, output=b"error"),
        ]
        app.exec_run.side_effect = results
        commands = {
            "cmd1": ["echo", "1"],
            "cmd2": ["echo", "2"],
        }
        success, failure = run_parallel_container_commands(app, commands, max_workers=1)
        assert success + failure == 2
        assert failure >= 1

    def test_command_raises_exception(self):
        """コマンド実行中に例外が発生した場合."""
        app = MagicMock()
        app.exec_run.side_effect = Exception("Docker error")
        commands = {"cmd1": ["echo", "1"]}
        success, failure = run_parallel_container_commands(app, commands, max_workers=1)
        assert success == 0
        assert failure == 1

    def test_single_command_succeeds(self):
        """単一コマンドが成功する場合."""
        app = MagicMock()
        app.exec_run.return_value = MagicMock(exit_code=0, output=b"ok")
        commands = {"only_cmd": ["echo", "test"]}
        success, failure = run_parallel_container_commands(app, commands)
        assert success == 1
        assert failure == 0


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

    def test_init_with_local_env_path(self, tmp_path):
        """local_env_path を指定して初期化できる."""
        sync = SecretManagerSync(project_id="p", local_env_path=tmp_path)
        assert sync.local_env_path == tmp_path

    def test_init_with_custom_secret_id(self):
        """カスタム secret_id で初期化できる."""
        sync = SecretManagerSync(project_id="p", secret_id="custom-secret")
        assert sync.secret_id == "custom-secret"


class TestSecretManagerSyncGetClient:
    """SecretManagerSync._get_client のテスト."""

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_creates_client_on_first_call(self, mock_require):
        """初回呼び出し時にクライアントが作成される."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p")
        client = sync._get_client()
        assert client == mock_client

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_reuses_existing_client(self, mock_require):
        """既にクライアントがある場合は再利用する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        sync = SecretManagerSync(project_id="p")
        client1 = sync._get_client()
        client2 = sync._get_client()
        assert client1 is client2
        # SecretManagerServiceClient は 1 回しか呼ばれない
        assert mock_secretmanager.SecretManagerServiceClient.call_count == 1

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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


class TestSecretManagerSyncGetSecretResourceName:
    """SecretManagerSync._get_secret_resource_name のテスト."""

    def test_uses_default_secret_id(self):
        """引数なしの場合、デフォルトの secret_id が使われる."""
        sync = SecretManagerSync(project_id="my-project", secret_id="default-secret")
        name = sync._get_secret_resource_name()
        assert name == "projects/my-project/secrets/default-secret"

    def test_uses_custom_secret_id(self):
        """カスタム secret_id が指定された場合はそれが使われる."""
        sync = SecretManagerSync(project_id="my-project", secret_id="default-secret")
        name = sync._get_secret_resource_name("custom-secret")
        assert name == "projects/my-project/secrets/custom-secret"


class TestSecretManagerSyncGetSecretValue:
    """SecretManagerSync.get_secret_value のテスト."""

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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
        result = sync.get_secret_value()
        assert result == '{"key": "value"}'

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_update_secret_api_error(self, mock_require):
        """Secret 更新時の API エラーが ComposerCliError に変換される."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_client.add_secret_version.side_effect = Exception("update failed")

        sync = SecretManagerSync(project_id="p", secret_id="test-secret")
        with pytest.raises(errors.ComposerCliError, match="Secret の更新に失敗"):
            sync.update_secret("test-secret", "new value")

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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


class TestSecretManagerSyncGetAllVariables:
    """SecretManagerSync.get_all_variables のテスト."""

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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
        result = sync.get_all_variables()
        assert result == {"key1": "val1", "key2": "val2"}

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_invalid_json_raises_error(self, mock_require):
        """不正な JSON の場合エラーが発生する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "not json"
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="s")
        with pytest.raises(Exception):
            sync.get_all_variables()


class TestSecretManagerSyncCompareVariables:
    """SecretManagerSync.compare_variables のテスト."""

    def test_no_changes(self):
        """変更がない場合 has_changes が False."""
        sync = SecretManagerSync(project_id="p")
        old = {"key1": "val1", "key2": "val2"}
        new = {"key1": "val1", "key2": "val2"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is False
        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_added_variables(self):
        """新しい変数が追加された場合."""
        sync = SecretManagerSync(project_id="p")
        old = {"key1": "val1"}
        new = {"key1": "val1", "key2": "val2"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is True
        assert result["added"] == {"key2": "val2"}
        assert result["removed"] == {}
        assert result["modified"] == {}

    def test_removed_variables(self):
        """変数が削除された場合."""
        sync = SecretManagerSync(project_id="p")
        old = {"key1": "val1", "key2": "val2"}
        new = {"key1": "val1"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is True
        assert result["added"] == {}
        assert result["removed"] == {"key2": "val2"}
        assert result["modified"] == {}

    def test_modified_variables(self):
        """変数の値が変更された場合."""
        sync = SecretManagerSync(project_id="p")
        old = {"key1": "old_value"}
        new = {"key1": "new_value"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is True
        assert result["modified"] == {
            "key1": {"old_value": "old_value", "new_value": "new_value"}
        }

    def test_mixed_changes(self):
        """追加・削除・変更が混在する場合."""
        sync = SecretManagerSync(project_id="p")
        old = {"keep": "same", "modify": "old", "remove": "gone"}
        new = {"keep": "same", "modify": "new", "add": "fresh"}
        result = sync.compare_variables(new, old)
        assert result["has_changes"] is True
        assert result["added"] == {"add": "fresh"}
        assert result["removed"] == {"remove": "gone"}
        assert result["modified"] == {
            "modify": {"old_value": "old", "new_value": "new"}
        }

    def test_empty_to_non_empty(self):
        """空から変数が追加される場合."""
        sync = SecretManagerSync(project_id="p")
        result = sync.compare_variables({"key": "val"}, {})
        assert result["has_changes"] is True
        assert result["added"] == {"key": "val"}

    def test_non_empty_to_empty(self):
        """全変数が削除される場合."""
        sync = SecretManagerSync(project_id="p")
        result = sync.compare_variables({}, {"key": "val"})
        assert result["has_changes"] is True
        assert result["removed"] == {"key": "val"}

    def test_both_empty(self):
        """両方とも空の場合."""
        sync = SecretManagerSync(project_id="p")
        result = sync.compare_variables({}, {})
        assert result["has_changes"] is False

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
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
        result = sync.format_variables_diff(changes)
        assert result == "変更はありません"

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

    def test_removed_variables_format(self):
        """削除された変数のフォーマットに '-' が含まれる."""
        sync = SecretManagerSync(project_id="p")
        changes = {
            "has_changes": True,
            "added": {},
            "removed": {"old_key": "old_value_long_enough"},
            "modified": {},
        }
        result = sync.format_variables_diff(changes)
        assert "-" in result
        assert "old_key" in result

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


class TestSecretManagerSyncSyncToLocalAirflow:
    """SecretManagerSync.sync_to_local_airflow のテスト."""

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_sync_writes_variables_file(self, mock_require, tmp_path):
        """Variables をローカルファイルに書き出す."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '{"k1": "v1", "k2": "v2"}'
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", local_env_path=tmp_path, secret_id="s")
        sync.sync_to_local_airflow()

        variables_file = tmp_path / "data" / "variables.json"
        assert variables_file.exists()
        data = json.loads(variables_file.read_text())
        assert data == {"k1": "v1", "k2": "v2"}

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_sync_with_empty_variables(self, mock_require):
        """Variables が空の場合は何も書き出さない."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = "{}"
        mock_client.access_secret_version.return_value = mock_response

        sync = SecretManagerSync(project_id="p", secret_id="s")
        # 空の場合は early return される
        sync.sync_to_local_airflow()

    @patch("composer_local.secret_manager_sync.require_gcp_secret_manager")
    def test_sync_clears_container_variables_when_env_provided(self, mock_require, tmp_path):
        """env が提供された場合、コンテナ内の Variables を削除する."""
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        mock_response = MagicMock()
        mock_response.payload.data.decode.return_value = '{"k": "v"}'
        mock_client.access_secret_version.return_value = mock_response

        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_env.container_name = "test-container"
        mock_container = MagicMock()
        mock_env._get_container.return_value = mock_container
        # variables list の結果
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=b"key1\nkey2\n")

        sync = SecretManagerSync(project_id="p", local_env_path=tmp_path, secret_id="s")
        sync.sync_to_local_airflow(env=mock_env)


class TestSecretManagerSyncClearAllLocalVariables:
    """SecretManagerSync.clear_all_local_variables のテスト."""

    def test_deletes_variables_file(self, tmp_path):
        """variables.json が存在する場合に削除される."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        variables_file = data_dir / "variables.json"
        variables_file.write_text('{"key": "value"}')

        sync = SecretManagerSync(project_id="p", local_env_path=tmp_path)
        sync.clear_all_local_variables()
        assert not variables_file.exists()

    def test_no_error_when_file_not_exists(self, tmp_path):
        """variables.json が存在しない場合もエラーにならない."""
        sync = SecretManagerSync(project_id="p", local_env_path=tmp_path)
        sync.clear_all_local_variables()  # エラーにならないこと

    def test_no_error_when_no_local_env_path(self):
        """local_env_path が None の場合もエラーにならない."""
        sync = SecretManagerSync(project_id="p")
        sync.clear_all_local_variables()  # エラーにならないこと


class TestSecretManagerSyncClearAirflowVariablesInContainer:
    """SecretManagerSync.clear_airflow_variables_in_container のテスト."""

    def test_skips_when_not_running(self):
        """コンテナが実行中でない場合はスキップする."""
        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"

        sync = SecretManagerSync(project_id="p")
        sync.clear_airflow_variables_in_container(mock_env)
        # _get_container が呼ばれないこと
        mock_env._get_container.assert_not_called()

    def test_deletes_variables_in_running_container(self):
        """実行中のコンテナ内の Variables を削除する."""
        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_env.container_name = "test-container"

        mock_container = MagicMock()
        mock_env._get_container.return_value = mock_container

        # variables list の結果
        list_result = MagicMock(exit_code=0, output=b"var1\nvar2\n")
        # variables delete の結果
        delete_result = MagicMock(exit_code=0, output=b"ok")
        mock_container.exec_run.side_effect = [list_result, delete_result, delete_result]

        sync = SecretManagerSync(project_id="p")
        sync.clear_airflow_variables_in_container(mock_env)

    def test_handles_list_failure(self):
        """variables list が失敗した場合でもエラーにならない."""
        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_env.container_name = "test-container"

        mock_container = MagicMock()
        mock_env._get_container.return_value = mock_container

        mock_container.exec_run.return_value = MagicMock(exit_code=1, output=b"error")

        sync = SecretManagerSync(project_id="p")
        # エラーにならないこと
        sync.clear_airflow_variables_in_container(mock_env)

    def test_handles_exception_gracefully(self):
        """例外が発生した場合でもエラーにならない."""
        mock_env = MagicMock()
        mock_env.status.side_effect = Exception("docker error")

        sync = SecretManagerSync(project_id="p")
        # 例外が外に伝播しないこと
        sync.clear_airflow_variables_in_container(mock_env)


# =============================================================================
# create_sync_client のテスト
# =============================================================================


class TestCreateSyncClient:
    """create_sync_client 関数のテスト."""

    def test_creates_client_with_defaults(self):
        """デフォルト設定でクライアントが作成される."""
        client = create_sync_client(project_id="test-project")
        assert isinstance(client, SecretManagerSync)
        assert client.project_id == "test-project"
        assert client.local_env_path is None

    def test_creates_client_with_local_env_path(self, tmp_path):
        """local_env_path を指定してクライアントが作成される."""
        client = create_sync_client(project_id="p", local_env_path=tmp_path)
        assert client.local_env_path == tmp_path
