"""composer_local.import_variables_to_local のユニットテスト.

GCP Secret Manager API、Docker API をモック化してテストする。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from composer_local import constants
from composer_local.import_variables_to_local import _import_variables_to_container


# =============================================================================
# _import_variables_to_container のテスト
# =============================================================================


class TestImportVariablesToContainer:
    """_import_variables_to_container 関数のテスト."""

    def test_imports_variables_to_running_container(self):
        """実行中のコンテナに Variables をインポートする."""
        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_env.container_name = "test-container"
        mock_container = MagicMock()
        mock_env._get_container.return_value = mock_container
        mock_container.exec_run.return_value = MagicMock(exit_code=0, output=b"ok")

        variables = {"key1": "val1", "key2": "val2"}
        _import_variables_to_container(mock_env, variables)

        # exec_run が各変数に対して呼ばれること
        assert mock_container.exec_run.call_count == 2

    def test_skips_when_not_running(self):
        """コンテナが実行中でない場合はスキップする."""
        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"

        variables = {"key1": "val1"}
        _import_variables_to_container(mock_env, variables)

        # _get_container が呼ばれないこと
        mock_env._get_container.assert_not_called()

    def test_empty_variables(self):
        """空の Variables 辞書の場合."""
        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_env.container_name = "test-container"
        mock_container = MagicMock()
        mock_env._get_container.return_value = mock_container

        _import_variables_to_container(mock_env, {})

    def test_exception_is_reraised(self):
        """処理中の例外は再送出される."""
        mock_env = MagicMock()
        mock_env.status.side_effect = Exception("docker error")

        with pytest.raises(Exception, match="docker error"):
            _import_variables_to_container(mock_env, {"key": "val"})


# =============================================================================
# main 関数のテスト
# =============================================================================


class TestImportVariablesToLocalMain:
    """import_variables_to_local.main のテスト."""

    @patch("composer_local.utils.setup_logging")
    @patch("composer_local.import_variables_to_local._import_variables_to_container")
    @patch("composer_local.import_variables_to_local.create_sync_client")
    @patch("composer_local.import_variables_to_local.composer_environment.Environment.load_from_config")
    @patch("composer_local.import_variables_to_local.argparse.ArgumentParser.parse_args")
    def test_main_imports_variables(
        self, mock_args, mock_load, mock_create_sync, mock_import, mock_setup_logging, tmp_path, capsys
    ):
        """正常に Variables をインポートする."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            secret_id="test-secret",
            local_env_dir=str(local_env_dir),
            airflow_url="http://localhost:8080",
            verbose=False,
            debug=False,
        )

        mock_env = MagicMock()
        mock_load.return_value = mock_env

        mock_sync = MagicMock()
        mock_create_sync.return_value = mock_sync
        mock_sync.get_all_variables.return_value = {"key1": "val1", "key2": "val2"}

        from composer_local.import_variables_to_local import main

        main()

        mock_sync.clear_airflow_variables_in_container.assert_called_once_with(mock_env)
        mock_import.assert_called_once()
        mock_sync.clear_all_local_variables.assert_called_once()

        # variables.json が書き出されること
        variables_file = local_env_dir / "data" / "variables.json"
        assert variables_file.exists()
        data = json.loads(variables_file.read_text())
        assert data == {"key1": "val1", "key2": "val2"}

    @patch("composer_local.utils.setup_logging")
    @patch("composer_local.import_variables_to_local.create_sync_client")
    @patch("composer_local.import_variables_to_local.composer_environment.Environment.load_from_config")
    @patch("composer_local.import_variables_to_local.argparse.ArgumentParser.parse_args")
    def test_main_no_variables(
        self, mock_args, mock_load, mock_create_sync, mock_setup_logging, tmp_path, capsys
    ):
        """Variables が空の場合、メッセージを表示して終了する."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            secret_id="test-secret",
            local_env_dir=str(local_env_dir),
            airflow_url="http://localhost:8080",
            verbose=False,
            debug=False,
        )

        mock_load.return_value = MagicMock()

        mock_sync = MagicMock()
        mock_create_sync.return_value = mock_sync
        mock_sync.get_all_variables.return_value = {}

        from composer_local.import_variables_to_local import main

        main()

        captured = capsys.readouterr()
        assert "見つかりません" in captured.out

    @patch("composer_local.utils.setup_logging")
    @patch("composer_local.import_variables_to_local.create_sync_client")
    @patch("composer_local.import_variables_to_local.composer_environment.Environment.load_from_config")
    @patch("composer_local.import_variables_to_local.argparse.ArgumentParser.parse_args")
    def test_main_error_handling(
        self, mock_args, mock_load, mock_create_sync, mock_setup_logging, tmp_path
    ):
        """エラーが発生した場合、エラーメッセージが表示される."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            secret_id="test-secret",
            local_env_dir=str(local_env_dir),
            airflow_url="http://localhost:8080",
            verbose=False,
            debug=False,
        )

        mock_load.side_effect = Exception("load failed")

        from composer_local.import_variables_to_local import main

        with pytest.raises(Exception, match="load failed"):
            main()

    @patch("composer_local.utils.setup_logging")
    @patch("composer_local.import_variables_to_local.create_sync_client")
    @patch("composer_local.import_variables_to_local.composer_environment.Environment.load_from_config")
    @patch("composer_local.import_variables_to_local.argparse.ArgumentParser.parse_args")
    def test_main_none_variables_returned(
        self, mock_args, mock_load, mock_create_sync, mock_setup_logging, tmp_path, capsys
    ):
        """get_all_variables が None を返す場合（エッジケース）."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="p",
            secret_id="s",
            local_env_dir=str(local_env_dir),
            airflow_url="http://localhost:8080",
            verbose=False,
            debug=False,
        )

        mock_load.return_value = MagicMock()

        mock_sync = MagicMock()
        mock_create_sync.return_value = mock_sync
        mock_sync.get_all_variables.return_value = None

        from composer_local.import_variables_to_local import main

        main()

        captured = capsys.readouterr()
        assert "見つかりません" in captured.out
