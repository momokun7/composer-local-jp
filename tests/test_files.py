"""composer_local.files のユニットテスト."""

import pathlib
from unittest import mock

import pytest

from composer_local import errors, files


class TestResolveDagsPath:
    """resolve_dags_path のテスト."""

    def test_returns_resolved_path_when_dags_path_given(self, tmp_dir):
        """dags_path が指定された場合、解決済みパスを返す."""
        dags = tmp_dir / "my_dags"
        result = files.resolve_dags_path(str(dags), tmp_dir)
        assert result == str(dags.resolve())

    def test_returns_default_when_none(self, tmp_dir):
        """dags_path が None の場合、env_dir/dags をデフォルトとして返す."""
        with mock.patch("composer_local.console.get_console") as mock_console:
            mock_console.return_value.print = mock.MagicMock()
            result = files.resolve_dags_path(None, tmp_dir)
        expected = str((tmp_dir / "dags").resolve())
        assert result == expected

    def test_relative_path_is_resolved(self, tmp_dir):
        """相対パスが絶対パスに解決される."""
        result = files.resolve_dags_path("relative/dags", tmp_dir)
        assert pathlib.Path(result).is_absolute()

    def test_path_with_trailing_slash(self, tmp_dir):
        """末尾スラッシュ付きのパスも正しく解決される."""
        dags = tmp_dir / "dags"
        result = files.resolve_dags_path(str(dags) + "/", tmp_dir)
        assert result == str(dags.resolve())


class TestAssertDagPathExists:
    """assert_dag_path_exists のテスト."""

    def test_existing_directory_passes(self, tmp_dags_dir):
        """存在するディレクトリでは例外が発生しない."""
        files.assert_dag_path_exists(str(tmp_dags_dir))

    def test_nonexistent_path_raises_error(self):
        """存在しないパスで DAGPathNotExistError が発生する."""
        with pytest.raises(errors.DAGPathNotExistError):
            files.assert_dag_path_exists("/nonexistent/path/to/dags")

    def test_file_path_raises_error(self, tmp_file):
        """ファイルパス（ディレクトリではない）で DAGPathNotExistError が発生する."""
        with pytest.raises(errors.DAGPathNotExistError):
            files.assert_dag_path_exists(str(tmp_file))

    def test_error_message_contains_path(self):
        """エラーメッセージに問題のパスが含まれる."""
        bad_path = "/nonexistent/dags/path"
        with pytest.raises(errors.DAGPathNotExistError) as exc_info:
            files.assert_dag_path_exists(bad_path)
        assert bad_path in exc_info.value.message
