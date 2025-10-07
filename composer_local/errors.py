import functools
from typing import Optional, Tuple

import click
from google.auth import exceptions as auth_exception

from composer_local import constants


class ComposerCliError(click.ClickException):
    def __init__(self, msg):
        msg += constants.ADD_DEBUG_ON_ERROR_INFO
        super().__init__(msg)


class ComposerCliFatalError(Exception):
    pass


class ImageNotFoundError(ComposerCliError):
    def __init__(self, image_version):
        msg = constants.IMAGE_TAG_DOES_NOT_EXIST_ERROR.format(image_tag=image_version)
        super().__init__(msg)


class EnvironmentNotRunningError(ComposerCliError):
    def __init__(self):
        msg = constants.ENV_NOT_RUNNING
        super().__init__(msg)


class EnvironmentNotFoundError(EnvironmentNotRunningError):
    pass


class EnvironmentStartError(ComposerCliError):
    def __init__(self, msg: Optional[str] = None):
        if msg is None:
            msg = constants.ENVIRONMENT_FAILED_TO_START_ERROR
        super().__init__(msg)


class InvalidConfigurationError(ComposerCliError):
    pass


class MissingRequiredParameterError(InvalidConfigurationError):
    def __init__(self, param):
        msg = constants.MISSING_REQUIRED_PARAM_ERROR.format(param=param)
        super().__init__(msg)


class FailedToParseConfigParamIntError(InvalidConfigurationError):
    def __init__(self, param_name: str, value: str):
        msg = constants.INVALID_INT_VALUE_ERROR.format(param_name=param_name, value=value)
        super().__init__(msg)


class FailedToParseConfigParamIntRangeError(InvalidConfigurationError):
    def __init__(self, param_name: str, value: int, int_range: Tuple[int,]):
        if len(int_range) == 1:
            allowed_range = f"x>={int_range[0]}"
        else:
            allowed_range = f"{int_range[0]}<=x<={int_range[1]}"
        msg = constants.INVALID_INT_RANGE_VALUE_ERROR.format(
            param_name=param_name, value=value, allowed_range=allowed_range
        )
        super().__init__(msg)


class FailedToParseConfigError(InvalidConfigurationError):
    def __init__(self, config_path, err):
        msg = constants.INVALID_CONFIGURATION_FILE_ERROR.format(config_path=config_path, error=err)
        super().__init__(msg)


class DockerNotAvailableError(ComposerCliError):
    def __init__(self, err):
        super().__init__(constants.DOCKER_NOT_AVAILABLE_ERROR.format(error=err))


class InvalidAuthError(ComposerCliError):
    def __init__(self, err):
        error_str = str(err)
        if error_str.endswith("."):
            error_str = error_str[:-1]
        super().__init__(constants.AUTH_INVALID_ERROR.format(error=error_str))


class DAGPathNotExistError(ComposerCliError):
    def __init__(self, dags_path):
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
        except auth_exception.DefaultCredentialsError as err:
            raise InvalidAuthError(str(err))
        except Exception:
            message = "\nFatal exception occurred."
            raise ComposerCliFatalError(message)

    return wrapper
