"""composer_local.utils のユニットテスト."""

import pytest

from composer_local import errors, utils


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
