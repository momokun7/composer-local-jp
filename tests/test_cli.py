"""composer_local.cli のユニットテスト.

Click の CliRunner を使い、Docker 不要のテスト（--help 出力やモック化した同期）を実施する。
"""

from unittest.mock import patch

from click.testing import CliRunner

from composer_local.cli import cli

# =============================================================================
# ヘルパー
# =============================================================================


def _invoke(*args):
    """CliRunner で CLI を呼び出し、Result を返す."""
    runner = CliRunner()
    return runner.invoke(cli, list(args))


# =============================================================================
# トップレベル CLI のテスト
# =============================================================================


class TestCliTopLevel:
    """トップレベルの CLI テスト."""

    def test_help_exits_successfully(self):
        """--help が正常に終了すること."""
        assert _invoke("--help").exit_code == 0

    def test_help_contains_usage(self):
        """--help 出力に Usage が含まれること."""
        assert "Usage" in _invoke("--help").output

    def test_help_lists_subcommands(self):
        """--help 出力に新しい 7 コマンドが含まれること."""
        result = _invoke("--help")
        for cmd in ("start", "stop", "status", "logs", "run", "sync", "remove"):
            assert cmd in result.output, f"サブコマンド '{cmd}' が --help 出力に見つかりません"

    def test_help_does_not_list_removed_subcommands(self):
        """削除済みコマンドが --help 出力に現れないこと."""
        result = _invoke("--help")
        for cmd in ("create", "describe", "list", "run-airflow", "sync-vars", "sync-settings"):
            assert cmd not in result.output

    def test_version_exits_successfully(self):
        """--version が正常に終了すること."""
        assert _invoke("--version").exit_code == 0

    def test_version_contains_version_string(self):
        """--version 出力にバージョン文字列が含まれること."""
        from composer_local.version import __version__

        assert __version__ in _invoke("--version").output

    def test_version_contains_program_name(self):
        """--version 出力にプログラム名が含まれること."""
        assert "composer-local" in _invoke("--version").output

    def test_verbose_option_in_help(self):
        """トップレベル --help に --verbose オプションが表示されること."""
        assert "--verbose" in _invoke("--help").output

    def test_debug_option_in_help(self):
        """トップレベル --help に --debug オプションが表示されること."""
        assert "--debug" in _invoke("--help").output


# =============================================================================
# サブコマンド --help のテスト
# =============================================================================


class TestStartCommandHelp:
    """start サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("start", "--help").exit_code == 0

    def test_help_contains_usage(self):
        assert "Usage" in _invoke("start", "--help").output

    def test_help_contains_port_option(self):
        result = _invoke("start", "--help")
        assert "--port" in result.output or "--web-server-port" in result.output

    def test_help_contains_image_version_option(self):
        assert "--image-version" in _invoke("start", "--help").output

    def test_help_contains_project_option(self):
        assert "--project" in _invoke("start", "--help").output

    def test_help_contains_database_option(self):
        assert "--database" in _invoke("start", "--help").output


class TestStopCommandHelp:
    """stop サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("stop", "--help").exit_code == 0

    def test_help_contains_usage(self):
        assert "Usage" in _invoke("stop", "--help").output


class TestStatusCommandHelp:
    """status サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("status", "--help").exit_code == 0

    def test_help_contains_usage(self):
        assert "Usage" in _invoke("status", "--help").output


class TestRemoveCommandHelp:
    """remove サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("remove", "--help").exit_code == 0

    def test_help_contains_force_option(self):
        assert "--force" in _invoke("remove", "--help").output

    def test_help_contains_skip_confirmation_option(self):
        assert "--skip-confirmation" in _invoke("remove", "--help").output


class TestLogsCommandHelp:
    """logs サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("logs", "--help").exit_code == 0

    def test_help_contains_follow_option(self):
        assert "--follow" in _invoke("logs", "--help").output

    def test_help_contains_max_lines_option(self):
        assert "--max-lines" in _invoke("logs", "--help").output


class TestRunCommandHelp:
    """run サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("run", "--help").exit_code == 0

    def test_help_contains_usage(self):
        assert "Usage" in _invoke("run", "--help").output


class TestSyncCommandHelp:
    """sync サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        assert _invoke("sync", "--help").exit_code == 0

    def test_help_contains_settings_option(self):
        assert "--settings" in _invoke("sync", "--help").output

    def test_help_contains_secret_id_option(self):
        assert "--secret-id" in _invoke("sync", "--help").output

    def test_help_contains_env_name_option(self):
        assert "--env-name" in _invoke("sync", "--help").output


# =============================================================================
# start の自動作成ロジックのテスト
# =============================================================================


class TestStartAutoCreate:
    """start コマンドの自動作成挙動のテスト."""

    @patch("composer_local.environment.Environment.start_foreground")
    @patch("composer_local.environment.Environment.load_from_config")
    @patch("composer_local.environment.Environment.create")
    @patch("composer_local.cli.files.resolve_environment_path")
    @patch("composer_local.cli.pathlib.Path.is_file", return_value=False)
    def test_creates_environment_when_config_absent(
        self, mock_is_file, mock_path, mock_create, mock_load, mock_fg, tmp_path
    ):
        """config.json が無い場合、create と start_foreground の両方が呼ばれる."""
        mock_path.return_value = tmp_path
        result = _invoke("start", "myenv")
        assert result.exit_code == 0, result.output
        assert mock_create.called
        assert mock_fg.called

    @patch("composer_local.environment.Environment.start_foreground")
    @patch("composer_local.environment.Environment.load_from_config")
    @patch("composer_local.environment.Environment.create")
    @patch("composer_local.cli.files.resolve_environment_path")
    @patch("composer_local.cli.pathlib.Path.is_file", return_value=True)
    def test_does_not_create_when_config_present(
        self, mock_is_file, mock_path, mock_create, mock_load, mock_fg, tmp_path
    ):
        """config.json が存在する場合、create は呼ばれず start_foreground のみ呼ばれる."""
        mock_path.return_value = tmp_path
        result = _invoke("start", "myenv")
        assert result.exit_code == 0, result.output
        assert not mock_create.called
        assert mock_fg.called


# =============================================================================
# sync コマンドのテスト
# =============================================================================


class TestSyncCommand:
    """sync コマンドが正しい gcp_sync 関数を呼ぶことのテスト."""

    def test_uses_secret_manager_when_secret_id_given(self, tmp_path):
        """--secret-id 指定時は sync_vars_via_secret_manager が呼ばれる."""
        with patch("composer_local.gcp_sync.sync_vars_via_secret_manager") as mock_sm, \
             patch("composer_local.files.resolve_environment_path") as mock_path, \
             patch("composer_local.environment.Environment.load_from_config"):
            mock_path.return_value = tmp_path
            result = _invoke(
                "sync", "--secret-id", "my-secret", "-p", "proj", "-e", "comp-env"
            )
            assert result.exit_code == 0, result.output
            assert mock_sm.called

    def test_uses_direct_sync_without_secret_id(self, tmp_path):
        """--secret-id 未指定時は sync_vars_direct が呼ばれる."""
        with patch("composer_local.gcp_sync.sync_vars_direct") as mock_direct, \
             patch("composer_local.files.resolve_environment_path") as mock_path, \
             patch("composer_local.environment.Environment.load_from_config"):
            mock_path.return_value = tmp_path
            result = _invoke("sync", "-p", "proj", "-e", "comp-env")
            assert result.exit_code == 0, result.output
            assert mock_direct.called

    def test_settings_flag_calls_sync_composer_settings(self):
        """--settings 指定時は sync_composer_settings が呼ばれる."""
        with patch("composer_local.gcp_sync.sync_composer_settings") as mock_settings:
            result = _invoke("sync", "--settings", "-p", "proj", "-e", "comp-env")
            assert result.exit_code == 0, result.output
            assert mock_settings.called

    def test_errors_when_project_cannot_be_resolved(self):
        """プロジェクト ID を解決できない場合は UsageError になる."""
        with patch("composer_local.gcp_sync.get_project_id", return_value=None):
            result = _invoke("sync", "-e", "comp-env")
            assert result.exit_code != 0
