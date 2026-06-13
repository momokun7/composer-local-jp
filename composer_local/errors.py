import functools
import logging
from typing import Tuple

import click

from composer_local import constants

LOG = logging.getLogger(__name__)


class ComposerCliError(click.ClickException):
    def __init__(self, msg: str) -> None:
        msg += constants.ADD_DEBUG_ON_ERROR_INFO
        super().__init__(msg)


class ComposerCliFatalError(click.ClickException):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class ImageNotFoundError(ComposerCliError):
    def __init__(self, image_version: str) -> None:
        msg = constants.IMAGE_TAG_DOES_NOT_EXIST_ERROR.format(image_tag=image_version)
        super().__init__(msg)


class EnvironmentNotRunningError(ComposerCliError):
    def __init__(self) -> None:
        msg = constants.ENV_NOT_RUNNING
        super().__init__(msg)


class EnvironmentNotFoundError(ComposerCliError):
    def __init__(self, msg: str = "環境が見つかりません。") -> None:
        super().__init__(msg)


class InvalidConfigurationError(ComposerCliError):
    pass


class MissingRequiredParameterError(InvalidConfigurationError):
    def __init__(self, param: str) -> None:
        msg = constants.MISSING_REQUIRED_PARAM_ERROR.format(param=param)
        super().__init__(msg)


class FailedToParseConfigParamIntError(InvalidConfigurationError):
    def __init__(self, param_name: str, value: str) -> None:
        msg = constants.INVALID_INT_VALUE_ERROR.format(param_name=param_name, value=value)
        super().__init__(msg)


class FailedToParseConfigParamIntRangeError(InvalidConfigurationError):
    def __init__(self, param_name: str, value: int, int_range: Tuple[int, ...]) -> None:
        if len(int_range) == 1:
            allowed_range = f"x>={int_range[0]}"
        else:
            allowed_range = f"{int_range[0]}<=x<={int_range[1]}"
        msg = constants.INVALID_INT_RANGE_VALUE_ERROR.format(
            param_name=param_name, value=value, allowed_range=allowed_range
        )
        super().__init__(msg)


class FailedToParseConfigError(InvalidConfigurationError):
    def __init__(self, config_path: str, err: str) -> None:
        msg = constants.INVALID_CONFIGURATION_FILE_ERROR.format(config_path=config_path, error=err)
        super().__init__(msg)


class DockerAPIError(ComposerCliError):
    """Docker API との通信で発生するエラー。"""

    pass


class DockerNotAvailableError(ComposerCliError):
    def __init__(self, err: str) -> None:
        super().__init__(constants.DOCKER_NOT_AVAILABLE_ERROR.format(error=err))


class InvalidAuthError(ComposerCliError):
    def __init__(self, err: str) -> None:
        error_str = str(err)
        if error_str.endswith("."):
            error_str = error_str[:-1]
        super().__init__(constants.AUTH_INVALID_ERROR.format(error=error_str))


class DAGPathNotExistError(ComposerCliError):
    def __init__(self, dags_path: str) -> None:
        super().__init__(constants.DAGS_PATH_NOT_EXISTS_ERROR.format(dags_path=dags_path))


def catch_exceptions(func=None):
    if not func:
        return functools.partial(catch_exceptions)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (
            click.ClickException,
            click.Abort,
        ):
            raise
        except Exception as exc:
            try:
                from google.auth import exceptions as auth_exception

                if isinstance(exc, auth_exception.DefaultCredentialsError):
                    raise InvalidAuthError(str(exc)) from exc
            except ImportError:
                LOG.debug(
                    "google.auth パッケージが利用できないため、"
                    "DefaultCredentialsError の判定をスキップしました。"
                )
            # debug フラグは Click コンテキスト経由で取得する
            # (グループコールバックで設定済み)
            ctx = click.get_current_context(silent=True)
            debug = ctx.obj.get("debug", False) if ctx and ctx.obj else kwargs.get("debug", False)
            if debug:
                raise
            message = f"\n致命的なエラーが発生しました: {exc}" + constants.ADD_DEBUG_ON_ERROR_INFO
            raise ComposerCliFatalError(message) from exc

    return wrapper
