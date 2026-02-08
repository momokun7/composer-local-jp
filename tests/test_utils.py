"""composer_local.utils のユニットテスト."""

import logging
from unittest.mock import patch

import pytest

from composer_local import constants, errors, utils


class TestAssertEnvironmentNameIsValid:
    """assert_environment_name_is_valid のテスト."""

    # --- 正常ケース ---

    def test_valid_name_lowercase(self):
        """英小文字のみの有効な環境名."""
        utils.assert_environment_name_is_valid("myenv")

    def test_valid_name_uppercase(self):
        """英大文字を含む有効な環境名."""
        utils.assert_environment_name_is_valid("MyEnv")

    def test_valid_name_with_digits(self):
        """数字を含む有効な環境名."""
        utils.assert_environment_name_is_valid("env123")

    def test_valid_name_with_hyphen(self):
        """ハイフンを含む有効な環境名."""
        utils.assert_environment_name_is_valid("my-env")

    def test_valid_name_with_underscore(self):
        """アンダースコアを含む有効な環境名."""
        utils.assert_environment_name_is_valid("my_env")

    def test_valid_name_minimum_length(self):
        """最小長（3文字）の有効な環境名."""
        utils.assert_environment_name_is_valid("abc")

    def test_valid_name_maximum_length(self):
        """最大長（40文字）の有効な環境名."""
        utils.assert_environment_name_is_valid("a" * 40)

    def test_valid_name_mixed(self):
        """英数字・ハイフン・アンダースコアを混在させた有効な環境名."""
        utils.assert_environment_name_is_valid("My_Env-123")

    # --- 異常ケース: 短すぎ ---

    def test_too_short_empty(self):
        """空文字列でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("")

    def test_too_short_one_char(self):
        """1文字でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("a")

    def test_too_short_two_chars(self):
        """2文字でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("ab")

    # --- 異常ケース: 長すぎ ---

    def test_too_long(self):
        """41文字でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("a" * 41)

    # --- 異常ケース: 無効文字 ---

    def test_invalid_char_space(self):
        """スペースを含む環境名でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("my env")

    def test_invalid_char_dot(self):
        """ドットを含む環境名でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("my.env")

    def test_invalid_char_slash(self):
        """スラッシュを含む環境名でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("my/env")

    def test_invalid_char_at(self):
        """@ を含む環境名でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("my@env")

    def test_invalid_char_japanese(self):
        """日本語文字を含む環境名でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.assert_environment_name_is_valid("環境名test")


class TestGetAirflowComposerVersions:
    """get_airflow_composer_versions のテスト."""

    # --- 正常ケース ---

    def test_composer2_airflow2(self):
        """Composer 2.x 系 + Airflow 2.x 系の標準的なバージョン文字列."""
        airflow_v, composer_v = utils.get_airflow_composer_versions(
            "composer-2.9.7-airflow-2.9.3"
        )
        assert airflow_v == "2.9.3"
        assert composer_v == "2.9.7"

    def test_composer3_airflow2(self):
        """Composer 3 + Airflow 2.x 系のバージョン文字列."""
        airflow_v, composer_v = utils.get_airflow_composer_versions(
            "composer-3-airflow-2.10.2"
        )
        assert airflow_v == "2.10.2"
        assert composer_v == "3"

    def test_with_build_suffix(self):
        """ビルドサフィックス付きのバージョン文字列."""
        airflow_v, composer_v = utils.get_airflow_composer_versions(
            "composer-2.9.7-airflow-2.9.3-build.1"
        )
        assert airflow_v == "2.9.3-build.1"
        assert composer_v == "2.9.7"

    # --- 異常ケース ---

    def test_invalid_format_empty(self):
        """空文字列でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.get_airflow_composer_versions("")

    def test_invalid_format_random_string(self):
        """ランダムな文字列でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.get_airflow_composer_versions("invalid-version")

    def test_invalid_format_missing_airflow(self):
        """airflow 部分が欠けた文字列でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.get_airflow_composer_versions("composer-2.9.7")

    def test_invalid_format_missing_composer(self):
        """composer 部分が欠けた文字列でエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.get_airflow_composer_versions("airflow-2.9.3")

    def test_invalid_format_zero_prefix(self):
        """Composer バージョンが 0 始まりでエラー."""
        with pytest.raises(errors.ComposerCliError):
            utils.get_airflow_composer_versions(
                "composer-0.1.0-airflow-2.9.3"
            )


class TestResolveProjectId:
    """resolve_project_id のテスト."""

    def test_returns_local_dev_when_none(self):
        """project_id が None の場合 'local-dev' を返すこと."""
        assert utils.resolve_project_id(None) == "local-dev"

    def test_returns_given_value_when_provided(self):
        """project_id が指定されている場合はそのまま返すこと."""
        assert utils.resolve_project_id("my-project") == "my-project"

    def test_returns_empty_string_when_empty(self):
        """空文字列が渡された場合はそのまま返すこと（None ではないため）."""
        assert utils.resolve_project_id("") == ""


class TestGetImageVersionTag:
    """get_image_version_tag のテスト."""

    def test_composer3_keeps_dots_in_airflow_version(self):
        """Composer 3 の場合、airflow_v のドットがそのまま保持されること."""
        result = utils.get_image_version_tag("2.10.2", "3")
        assert result == "composer-3-airflow-2.10.2"

    def test_composer2_replaces_dots_with_hyphens(self):
        """Composer 2.x.x の場合、airflow_v のドットがハイフンに置換されること."""
        result = utils.get_image_version_tag("2.9.3", "2.9.7")
        assert result == "composer-2.9.7-airflow-2-9-3"

    def test_composer2_single_digit(self):
        """Composer 2 系のバリエーション確認."""
        result = utils.get_image_version_tag("2.10.5", "2.11.0")
        assert result == "composer-2.11.0-airflow-2-10-5"


class TestIsWindowsOs:
    """is_windows_os のテスト."""

    @patch("composer_local.utils.os.name", "nt")
    def test_returns_true_on_windows(self):
        """os.name が 'nt' の場合 True を返すこと."""
        assert utils.is_windows_os() is True

    @patch("composer_local.utils.os.name", "posix")
    def test_returns_false_on_posix(self):
        """os.name が 'posix' の場合 False を返すこと."""
        assert utils.is_windows_os() is False


class TestWrapStatusInColor:
    """wrap_status_in_color のテスト."""

    def test_running_status_is_green(self):
        """RUNNING ステータスが緑色でラップされること."""
        result = utils.wrap_status_in_color(constants.ContainerStatus.RUNNING)
        assert "green" in result
        assert "running" in result.lower()

    def test_non_running_status_is_red(self):
        """RUNNING 以外のステータスが赤色でラップされること."""
        result = utils.wrap_status_in_color("stopped")
        assert "red" in result
        assert "stopped" in result

    def test_created_status_is_red(self):
        """CREATED ステータスが赤色でラップされること."""
        result = utils.wrap_status_in_color(constants.ContainerStatus.CREATED)
        assert "red" in result


class TestGetLogLevel:
    """get_log_level のテスト."""

    def test_debug_flag_returns_debug(self):
        """debug=True のとき DEBUG レベルを返すこと."""
        assert utils.get_log_level(verbose=False, debug=True) == logging.DEBUG

    def test_verbose_flag_returns_info(self):
        """verbose=True, debug=False のとき INFO レベルを返すこと."""
        assert utils.get_log_level(verbose=True, debug=False) == logging.INFO

    def test_no_flags_returns_warning(self):
        """どちらも False のとき WARNING レベルを返すこと."""
        assert utils.get_log_level(verbose=False, debug=False) == logging.WARNING

    def test_debug_takes_priority_over_verbose(self):
        """debug=True かつ verbose=True のとき DEBUG が優先されること."""
        assert utils.get_log_level(verbose=True, debug=True) == logging.DEBUG


class TestGetExternalLogLevel:
    """get_external_log_level のテスト."""

    def test_debug_flag_returns_debug(self):
        """debug=True のとき DEBUG レベルを返すこと."""
        assert utils.get_external_log_level(debug=True) == logging.DEBUG

    def test_no_debug_returns_warning(self):
        """debug=False のとき WARNING レベルを返すこと."""
        assert utils.get_external_log_level(debug=False) == logging.WARNING
