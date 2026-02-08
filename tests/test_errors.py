"""composer_local.errors のユニットテスト."""

import click
import pytest

from composer_local import errors


class TestErrorHierarchy:
    """例外クラスの継承関係のテスト."""

    def test_composer_cli_fatal_error_is_click_exception(self):
        """ComposerCliFatalError は click.ClickException のサブクラスである."""
        assert issubclass(errors.ComposerCliFatalError, click.ClickException)

    def test_composer_cli_error_is_click_exception(self):
        """ComposerCliError は click.ClickException のサブクラスである."""
        assert issubclass(errors.ComposerCliError, click.ClickException)

    def test_environment_not_found_error_is_composer_cli_error(self):
        """EnvironmentNotFoundError は ComposerCliError のサブクラスである."""
        assert issubclass(
            errors.EnvironmentNotFoundError, errors.ComposerCliError
        )

    def test_environment_not_found_error_is_not_environment_not_running_error(self):
        """EnvironmentNotFoundError は EnvironmentNotRunningError のサブクラスではない."""
        assert not issubclass(
            errors.EnvironmentNotFoundError, errors.EnvironmentNotRunningError
        )

    def test_environment_not_running_error_is_composer_cli_error(self):
        """EnvironmentNotRunningError は ComposerCliError のサブクラスである."""
        assert issubclass(
            errors.EnvironmentNotRunningError, errors.ComposerCliError
        )

    def test_invalid_configuration_error_is_composer_cli_error(self):
        """InvalidConfigurationError は ComposerCliError のサブクラスである."""
        assert issubclass(
            errors.InvalidConfigurationError, errors.ComposerCliError
        )

    def test_missing_required_parameter_error_is_invalid_configuration_error(self):
        """MissingRequiredParameterError は InvalidConfigurationError のサブクラスである."""
        assert issubclass(
            errors.MissingRequiredParameterError,
            errors.InvalidConfigurationError,
        )


class TestComposerCliFatalError:
    """ComposerCliFatalError のテスト."""

    def test_message_preserved(self):
        """メッセージが保持される."""
        exc = errors.ComposerCliFatalError("テストエラー")
        assert exc.message == "テストエラー"

    def test_is_instance_of_click_exception(self):
        """インスタンスが click.ClickException でもある."""
        exc = errors.ComposerCliFatalError("テスト")
        assert isinstance(exc, click.ClickException)


class TestComposerCliError:
    """ComposerCliError のテスト."""

    def test_message_includes_debug_info(self):
        """メッセージにデバッグ情報の案内が付加される."""
        exc = errors.ComposerCliError("元のメッセージ")
        assert "元のメッセージ" in exc.message
        assert "デバッグ" in exc.message


class TestCatchExceptions:
    """catch_exceptions デコレータのテスト."""

    def test_normal_execution(self):
        """例外が発生しない場合、戻り値がそのまま返される."""

        @errors.catch_exceptions
        def normal_func():
            return "success"

        assert normal_func() == "success"

    def test_click_exception_passes_through(self):
        """click.ClickException はそのまま再送出される."""

        @errors.catch_exceptions
        def raise_click_exc():
            raise click.ClickException("click error")

        with pytest.raises(click.ClickException, match="click error"):
            raise_click_exc()

    def test_click_abort_passes_through(self):
        """click.Abort はそのまま再送出される."""

        @errors.catch_exceptions
        def raise_abort():
            raise click.Abort()

        with pytest.raises(click.Abort):
            raise_abort()

    def test_generic_exception_converted_to_fatal_error(self):
        """一般的な例外は ComposerCliFatalError に変換される."""

        @errors.catch_exceptions
        def raise_generic():
            raise RuntimeError("unexpected")

        with pytest.raises(errors.ComposerCliFatalError) as exc_info:
            raise_generic()

        assert "unexpected" in exc_info.value.message

    def test_generic_exception_in_debug_mode_reraises(self):
        """debug=True の場合、元の例外がそのまま再送出される."""

        @errors.catch_exceptions
        def raise_generic(debug=False):
            raise RuntimeError("debug error")

        with pytest.raises(RuntimeError, match="debug error"):
            raise_generic(debug=True)

    def test_composer_cli_error_passes_through(self):
        """ComposerCliError (click.ClickException のサブクラス) はそのまま再送出される."""

        @errors.catch_exceptions
        def raise_cli_error():
            raise errors.ComposerCliError("cli error")

        with pytest.raises(errors.ComposerCliError):
            raise_cli_error()

    def test_decorator_without_parentheses(self):
        """引数なしのデコレータ形式で使用可能."""

        @errors.catch_exceptions
        def func():
            return 42

        assert func() == 42

    def test_decorator_with_parentheses(self):
        """括弧付きのデコレータ形式でも使用可能."""

        @errors.catch_exceptions()
        def func():
            return 42

        assert func() == 42
