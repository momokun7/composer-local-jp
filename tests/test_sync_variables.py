"""composer_local.sync_variables のユニットテスト.

GCP API、Docker API、subprocess をモック化してテストする。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from composer_local import constants


# =============================================================================
# main 関数のテスト
# =============================================================================


class TestSyncVariablesMain:
    """sync_variables.main のテスト."""

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_with_running_container(
        self, mock_args, mock_export, mock_load, tmp_path
    ):
        """Airflow が起動中の場合、Variables がインポートされる."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"key1": "val1", "key2": "val2"}

        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_load.return_value = mock_env

        from composer_local.sync_variables import main

        main()

        # run_airflow_command が呼ばれること
        mock_env.run_airflow_command.assert_called_once()

        # インポート後に variables.json が削除されること（unlink(missing_ok=True)）
        variables_file = local_env_dir / "data" / "variables.json"
        assert not variables_file.exists()

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_with_stopped_container(
        self, mock_args, mock_export, mock_load, tmp_path, capsys
    ):
        """Airflow が停止中の場合、Variables がファイルとして保存される."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"key1": "val1"}

        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"
        mock_load.return_value = mock_env

        from composer_local.sync_variables import main

        main()

        # variables.json が残っていること
        variables_file = local_env_dir / "data" / "variables.json"
        assert variables_file.exists()

        captured = capsys.readouterr()
        assert "次回起動時" in captured.out

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_load_env_failure_saves_to_file(
        self, mock_args, mock_export, mock_load, tmp_path, capsys
    ):
        """環境のロードに失敗した場合でも、Variables がファイルに保存される."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"key1": "val1"}

        mock_load.side_effect = Exception("load failed")

        from composer_local.sync_variables import main

        main()

        # variables.json がファイルとして保存されること
        variables_file = local_env_dir / "data" / "variables.json"
        assert variables_file.exists()

        captured = capsys.readouterr()
        assert "次回起動時" in captured.out

    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_export_failure(self, mock_args, mock_export, tmp_path):
        """gcloud コマンドの失敗はそのまま伝播する."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="p",
            location="l",
            env_name="e",
            local_env_dir=str(local_env_dir),
        )
        mock_export.side_effect = RuntimeError("gcloud failed")

        from composer_local.sync_variables import main

        with pytest.raises(RuntimeError, match="gcloud failed"):
            main()

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_variables_file_uses_ensure_ascii_false(
        self, mock_args, mock_export, mock_load, tmp_path
    ):
        """日本語を含む Variables が正しく保存される（ensure_ascii=False）."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="p",
            location="l",
            env_name="e",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"name": "テスト値"}

        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"
        mock_load.return_value = mock_env

        from composer_local.sync_variables import main

        main()

        variables_file = local_env_dir / "data" / "variables.json"
        content = variables_file.read_text()
        # ensure_ascii=False のため、日本語がそのまま保存される
        assert "テスト値" in content

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_creates_data_directory(
        self, mock_args, mock_export, mock_load, tmp_path
    ):
        """data ディレクトリが存在しない場合に作成される."""
        local_env_dir = tmp_path / "composer" / "new-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="p",
            location="l",
            env_name="e",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"key": "val"}

        mock_env = MagicMock()
        mock_env.status.return_value = "stopped"
        mock_load.return_value = mock_env

        from composer_local.sync_variables import main

        main()

        data_dir = local_env_dir / "data"
        assert data_dir.exists()

    @patch("composer_local.sync_variables.composer_environment.Environment.load_from_config")
    @patch("composer_local.sync_variables.export_variables_via_gcloud")
    @patch("composer_local.sync_variables.argparse.ArgumentParser.parse_args")
    def test_main_running_container_import_count_message(
        self, mock_args, mock_export, mock_load, tmp_path, capsys
    ):
        """起動中の Airflow にインポートした件数が表示される."""
        local_env_dir = tmp_path / "composer" / "test-env"
        local_env_dir.mkdir(parents=True)

        mock_args.return_value = MagicMock(
            project="p",
            location="l",
            env_name="e",
            local_env_dir=str(local_env_dir),
        )
        mock_export.return_value = {"a": "1", "b": "2", "c": "3"}

        mock_env = MagicMock()
        mock_env.status.return_value = constants.ContainerStatus.RUNNING
        mock_load.return_value = mock_env

        from composer_local.sync_variables import main

        main()

        captured = capsys.readouterr()
        assert "3" in captured.out
        assert "インポート" in captured.out
