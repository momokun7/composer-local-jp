"""composer_local.sync_settings のユニットテスト.

GCP Composer API をモック化してテストする。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from composer_local import errors
from composer_local.sync_settings import (
    _compose_env_resource_name,
    fetch_composer_env_details,
    sync_composer_settings,
    write_composer_settings,
)


# =============================================================================
# _compose_env_resource_name のテスト
# =============================================================================


class TestComposeEnvResourceName:
    """_compose_env_resource_name 関数のテスト."""

    def test_basic_resource_name(self):
        """基本的なリソース名が正しくフォーマットされる."""
        result = _compose_env_resource_name("my-project", "us-central1", "my-env")
        assert result == "projects/my-project/locations/us-central1/environments/my-env"

    def test_different_location(self):
        """異なるロケーションでも正しくフォーマットされる."""
        result = _compose_env_resource_name("proj", "asia-east1", "env")
        assert result == "projects/proj/locations/asia-east1/environments/env"

    def test_special_characters_in_names(self):
        """ハイフンやアンダースコアを含む名前でも正しくフォーマットされる."""
        result = _compose_env_resource_name("my-project-123", "us-west1", "my_env_name")
        assert result == "projects/my-project-123/locations/us-west1/environments/my_env_name"


# =============================================================================
# fetch_composer_env_details のテスト
# =============================================================================


class TestFetchComposerEnvDetails:
    """fetch_composer_env_details 関数のテスト."""

    @patch("composer_local.sync_settings.require_gcp_composer")
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

    @patch("composer_local.sync_settings.require_gcp_composer")
    def test_returns_details_with_empty_python_version(self, mock_require):
        """python_version が空の場合も正しく処理される."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1

        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client

        mock_env = MagicMock()
        mock_env.config.software_config.image_version = "composer-2.9.7-airflow-2.9.3"
        mock_env.config.software_config.python_version = ""
        mock_client.get_environment.return_value = mock_env

        result = fetch_composer_env_details("proj", "loc", "env")
        assert result["python_version"] == ""

    @patch("composer_local.sync_settings.require_gcp_composer")
    def test_returns_details_with_none_python_version(self, mock_require):
        """python_version が None の場合、空文字列になる."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1

        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client

        mock_env = MagicMock()
        mock_env.config.software_config.image_version = "composer-2.9.7-airflow-2.9.3"
        # getattr で None が返る場合をシミュレート
        type(mock_env.config.software_config).python_version = property(lambda s: None)
        mock_client.get_environment.return_value = mock_env

        result = fetch_composer_env_details("proj", "loc", "env")
        assert result["python_version"] == ""

    @patch("composer_local.sync_settings.require_gcp_composer")
    def test_api_error_raises_composer_error(self, mock_require):
        """API エラーが ComposerCliError に変換される."""
        mock_service_v1 = MagicMock()
        mock_require.return_value = mock_service_v1

        mock_client = MagicMock()
        mock_service_v1.EnvironmentsClient.return_value = mock_client

        mock_client.get_environment.side_effect = Exception("API error")

        with pytest.raises(errors.ComposerCliError, match="取得に失敗"):
            fetch_composer_env_details("proj", "loc", "env")

    @patch("composer_local.sync_settings.require_gcp_composer")
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


# =============================================================================
# write_composer_settings のテスト
# =============================================================================


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
        assert settings_path.exists()
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
        content = settings_path.read_text()
        assert 'COMPOSER_PYTHON_VERSION = ""' in content

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


# =============================================================================
# sync_composer_settings のテスト
# =============================================================================


class TestSyncComposerSettings:
    """sync_composer_settings 関数のテスト."""

    @patch("composer_local.sync_settings.fetch_composer_env_details")
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

        assert settings_path.exists()
        content = settings_path.read_text()
        assert 'COMPOSER_ENV_NAME = "prod-env"' in content
        assert 'COMPOSER_LOCATION = "asia-east1"' in content
        assert 'COMPOSER_IMAGE_VERSION = "composer-3-airflow-2.10.5"' in content

    @patch("composer_local.sync_settings.fetch_composer_env_details")
    def test_sync_passes_correct_arguments(self, mock_fetch, tmp_path):
        """正しい引数が fetch_composer_env_details に渡される."""
        mock_fetch.return_value = {
            "env_name": "env",
            "location": "loc",
            "image_version": "v",
            "python_version": "",
        }

        settings_path = tmp_path / "settings.py"
        sync_composer_settings("project-id", "us-west1", "env-name", settings_path)

        mock_fetch.assert_called_once_with("project-id", "us-west1", "env-name")

    @patch("composer_local.sync_settings.fetch_composer_env_details")
    def test_sync_with_fetch_error(self, mock_fetch, tmp_path):
        """fetch_composer_env_details がエラーの場合、そのまま伝播する."""
        mock_fetch.side_effect = errors.ComposerCliError("fetch failed")

        settings_path = tmp_path / "settings.py"
        with pytest.raises(errors.ComposerCliError, match="fetch failed"):
            sync_composer_settings("p", "l", "e", settings_path)
