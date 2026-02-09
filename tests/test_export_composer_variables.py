"""composer_local.export_composer_variables のユニットテスト.

GCP Secret Manager API、subprocess をモック化してテストする。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from composer_local import constants


# =============================================================================
# main 関数のテスト
# =============================================================================


class TestExportComposerVariablesMain:
    """export_composer_variables.main のテスト."""

    @patch("composer_local.export_composer_variables.require_gcp_secret_manager")
    @patch("composer_local.export_composer_variables.SecretManagerSync")
    @patch("composer_local.export_composer_variables.export_variables_via_gcloud")
    @patch("composer_local.export_composer_variables.argparse.ArgumentParser.parse_args")
    def test_main_with_changes(self, mock_args, mock_export, mock_sync_cls, mock_require):
        """変更がある場合、Secret Manager が更新される."""
        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            secret_id="test-secret",
        )
        mock_export.return_value = {"key1": "value1"}

        mock_sync = MagicMock()
        mock_sync_cls.return_value = mock_sync
        mock_sync.compare_variables.return_value = {
            "has_changes": True,
            "added": {"key1": "value1"},
            "removed": {},
            "modified": {},
        }
        mock_sync.format_variables_diff.return_value = "+ key1"

        from composer_local.export_composer_variables import main

        main()

        mock_sync.update_secret.assert_called_once()
        mock_sync.format_variables_diff.assert_called_once()

    @patch("composer_local.export_composer_variables.SecretManagerSync")
    @patch("composer_local.export_composer_variables.export_variables_via_gcloud")
    @patch("composer_local.export_composer_variables.argparse.ArgumentParser.parse_args")
    def test_main_no_changes(self, mock_args, mock_export, mock_sync_cls, capsys):
        """変更がない場合、Secret Manager は更新されない."""
        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            secret_id="test-secret",
        )
        mock_export.return_value = {"key1": "value1"}

        mock_sync = MagicMock()
        mock_sync_cls.return_value = mock_sync
        mock_sync.compare_variables.return_value = {
            "has_changes": False,
            "added": {},
            "removed": {},
            "modified": {},
        }

        from composer_local.export_composer_variables import main

        main()

        mock_sync.update_secret.assert_not_called()
        captured = capsys.readouterr()
        assert "変更はありません" in captured.out

    @patch("composer_local.export_composer_variables.require_gcp_secret_manager")
    @patch("composer_local.export_composer_variables.SecretManagerSync")
    @patch("composer_local.export_composer_variables.export_variables_via_gcloud")
    @patch("composer_local.export_composer_variables.argparse.ArgumentParser.parse_args")
    def test_main_secret_not_found_creates_new(
        self, mock_args, mock_export, mock_sync_cls, mock_require
    ):
        """Secret が存在しない場合、新規作成する."""
        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            secret_id="test-secret",
        )
        mock_export.return_value = {"key1": "value1"}

        mock_sync = MagicMock()
        mock_sync_cls.return_value = mock_sync
        mock_sync.compare_variables.side_effect = Exception("Secret not found")

        # require_gcp_secret_manager のモック
        mock_secretmanager = MagicMock()
        mock_client = MagicMock()
        mock_secretmanager.SecretManagerServiceClient.return_value = mock_client
        mock_require.return_value = (mock_secretmanager, Exception)

        from composer_local.export_composer_variables import main

        main()

        mock_client.create_secret.assert_called_once()
        mock_client.add_secret_version.assert_called_once()

    @patch("composer_local.export_composer_variables.SecretManagerSync")
    @patch("composer_local.export_composer_variables.export_variables_via_gcloud")
    @patch("composer_local.export_composer_variables.argparse.ArgumentParser.parse_args")
    def test_main_unexpected_error_reraises(self, mock_args, mock_export, mock_sync_cls):
        """Secret 未検出以外のエラーは再送出される."""
        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            secret_id="test-secret",
        )
        mock_export.return_value = {"key1": "value1"}

        mock_sync = MagicMock()
        mock_sync_cls.return_value = mock_sync
        mock_sync.compare_variables.side_effect = RuntimeError("unexpected error")

        from composer_local.export_composer_variables import main

        with pytest.raises(RuntimeError, match="unexpected error"):
            main()

    @patch("composer_local.export_composer_variables.export_variables_via_gcloud")
    @patch("composer_local.export_composer_variables.argparse.ArgumentParser.parse_args")
    def test_main_export_failure_reraises(self, mock_args, mock_export):
        """Variables の取得に失敗した場合、エラーが再送出される."""
        mock_args.return_value = MagicMock(
            project="test-project",
            location="us-central1",
            env_name="test-env",
            secret_id="test-secret",
        )
        mock_export.side_effect = RuntimeError("gcloud command failed")

        from composer_local.export_composer_variables import main

        with pytest.raises(RuntimeError, match="gcloud command failed"):
            main()
