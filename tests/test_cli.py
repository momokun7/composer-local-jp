"""composer_local.cli のユニットテスト.

Click の CliRunner を使い、Docker 不要のテスト（--help 出力など）のみ実施する。
"""

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
        result = _invoke("--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """--help 出力に Usage が含まれること."""
        result = _invoke("--help")
        assert "Usage" in result.output

    def test_help_lists_subcommands(self):
        """--help 出力にサブコマンド一覧が含まれること."""
        result = _invoke("--help")
        for cmd in ("create", "start", "stop", "describe", "remove", "logs"):
            assert cmd in result.output, f"サブコマンド '{cmd}' が --help 出力に見つかりません"

    def test_version_exits_successfully(self):
        """--version が正常に終了すること."""
        result = _invoke("--version")
        assert result.exit_code == 0

    def test_version_contains_version_string(self):
        """--version 出力にバージョン文字列が含まれること."""
        from composer_local.version import __version__

        result = _invoke("--version")
        assert __version__ in result.output

    def test_version_contains_program_name(self):
        """--version 出力にプログラム名が含まれること."""
        result = _invoke("--version")
        assert "composer-local" in result.output


# =============================================================================
# サブコマンド --help のテスト
# =============================================================================


class TestCreateCommandHelp:
    """create サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """create --help が正常に終了すること."""
        result = _invoke("create", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """create --help 出力に Usage が含まれること."""
        result = _invoke("create", "--help")
        assert "Usage" in result.output

    def test_help_contains_option_from_source_environment(self):
        """create --help に --from-source-environment オプションが表示されること."""
        result = _invoke("create", "--help")
        assert "--from-source-environment" in result.output

    def test_help_contains_option_from_image_version(self):
        """create --help に --from-image-version オプションが表示されること."""
        result = _invoke("create", "--help")
        assert "--from-image-version" in result.output

    def test_help_contains_option_project(self):
        """create --help に --project オプションが表示されること."""
        result = _invoke("create", "--help")
        assert "--project" in result.output

    def test_help_contains_option_database_engine(self):
        """create --help に --database-engine オプションが表示されること."""
        result = _invoke("create", "--help")
        assert "--database-engine" in result.output


class TestStartCommandHelp:
    """start サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """start --help が正常に終了すること."""
        result = _invoke("start", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """start --help 出力に Usage が含まれること."""
        result = _invoke("start", "--help")
        assert "Usage" in result.output

    def test_help_contains_port_option(self):
        """start --help に --port オプションが表示されること."""
        result = _invoke("start", "--help")
        assert "--port" in result.output or "--web-server-port" in result.output


class TestStopCommandHelp:
    """stop サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """stop --help が正常に終了すること."""
        result = _invoke("stop", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """stop --help 出力に Usage が含まれること."""
        result = _invoke("stop", "--help")
        assert "Usage" in result.output

    def test_help_contains_verbose_option(self):
        """stop --help に --verbose オプションが表示されること."""
        result = _invoke("stop", "--help")
        assert "--verbose" in result.output


class TestDescribeCommandHelp:
    """describe サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """describe --help が正常に終了すること."""
        result = _invoke("describe", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """describe --help 出力に Usage が含まれること."""
        result = _invoke("describe", "--help")
        assert "Usage" in result.output

    def test_help_contains_debug_option(self):
        """describe --help に --debug オプションが表示されること."""
        result = _invoke("describe", "--help")
        assert "--debug" in result.output


class TestRemoveCommandHelp:
    """remove サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """remove --help が正常に終了すること."""
        result = _invoke("remove", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """remove --help 出力に Usage が含まれること."""
        result = _invoke("remove", "--help")
        assert "Usage" in result.output

    def test_help_contains_force_option(self):
        """remove --help に --force オプションが表示されること."""
        result = _invoke("remove", "--help")
        assert "--force" in result.output

    def test_help_contains_skip_confirmation_option(self):
        """remove --help に --skip-confirmation オプションが表示されること."""
        result = _invoke("remove", "--help")
        assert "--skip-confirmation" in result.output


class TestLogsCommandHelp:
    """logs サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """logs --help が正常に終了すること."""
        result = _invoke("logs", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """logs --help 出力に Usage が含まれること."""
        result = _invoke("logs", "--help")
        assert "Usage" in result.output

    def test_help_contains_follow_option(self):
        """logs --help に --follow オプションが表示されること."""
        result = _invoke("logs", "--help")
        assert "--follow" in result.output

    def test_help_contains_max_lines_option(self):
        """logs --help に --max-lines オプションが表示されること."""
        result = _invoke("logs", "--help")
        assert "--max-lines" in result.output


class TestListCommandHelp:
    """list サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """list --help が正常に終了すること."""
        result = _invoke("list", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """list --help 出力に Usage が含まれること."""
        result = _invoke("list", "--help")
        assert "Usage" in result.output


class TestRunAirflowCommandHelp:
    """run-airflow サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """run-airflow --help が正常に終了すること."""
        result = _invoke("run-airflow", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """run-airflow --help 出力に Usage が含まれること."""
        result = _invoke("run-airflow", "--help")
        assert "Usage" in result.output


class TestSyncVarsCommandHelp:
    """sync-vars サブコマンドの --help テスト."""

    def test_help_exits_successfully(self):
        """sync-vars --help が正常に終了すること."""
        result = _invoke("sync-vars", "--help")
        assert result.exit_code == 0

    def test_help_contains_usage(self):
        """sync-vars --help 出力に Usage が含まれること."""
        result = _invoke("sync-vars", "--help")
        assert "Usage" in result.output

    def test_help_contains_secret_id_option(self):
        """sync-vars --help に --secret-id オプションが表示されること."""
        result = _invoke("sync-vars", "--help")
        assert "--secret-id" in result.output
