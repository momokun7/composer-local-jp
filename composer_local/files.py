import logging
import pathlib
from typing import List, Optional

from composer_local import console, constants, errors

LOG = logging.getLogger(__name__)


def resolve_environment_path(env_name: Optional[str]) -> pathlib.Path:
    env_dir = (pathlib.Path.cwd() / "composer").resolve()
    if not env_dir.is_dir():
        raise errors.ComposerCliError(
            constants.ENVIRONMENT_DIR_NOT_FOUND_ERROR.format(env_dir=env_dir)
        )

    envs = get_available_environments(env_dir)
    LOG.info(
        "Found following local environments:\n    %s",
        "\n    ".join(str(env) for env in envs),
    )
    if not envs:
        raise errors.ComposerCliError(constants.ENVIRONMENT_DIR_EMPTY_ERROR.format(env_dir=env_dir))

    if env_name:
        LOG.info("Searching for provided local environment name: %s", env_name)
        env_path = env_dir / env_name
        if not env_path.is_dir():
            raise errors.ComposerCliError(
                constants.ENVIRONMENT_PATH_NOT_FOUND_ERROR.format(env_path=env_path)
            )
        return env_path
    else:
        if len(envs) > 1:
            env_names = sorted(str(env.name) for env in envs)
            env_names = "\n    ".join(env_names)
            raise errors.ComposerCliError(
                constants.ENVIRONMENT_NOT_SELECTED_ERROR.format(
                    env_dir=env_dir, env_names=env_names
                )
            )
        LOG.info(
            "Environment path not provided, defaulting to only existing environment path: %s",
            envs[0],
        )
        return envs[0]


def get_environment_directories() -> List[pathlib.Path]:
    env_dir = (pathlib.Path.cwd() / "composer").resolve()
    if not env_dir.is_dir():
        return []
    return get_available_environments(env_dir)


def resolve_dags_path(dags_path: Optional[str], env_dir: pathlib.Path) -> str:
    if dags_path is None:
        console.get_console().print(constants.DAGS_PATH_NOT_PROVIDED_WARN)
        dags_path = env_dir / "dags"
    else:
        dags_path = pathlib.Path(dags_path)
    return str(dags_path.resolve())


def create_environment_directories(env_dir: pathlib.Path, dags_path: str):
    env_dirs = ("data", "plugins")
    LOG.info(
        "Creating environment directories %s in %s environment directory.",
        env_dirs,
        env_dir,
    )
    env_dir.mkdir(exist_ok=True, parents=True)
    for sub_dir in env_dirs:
        (env_dir / sub_dir).mkdir(exist_ok=True)
    dags_path = pathlib.Path(dags_path)
    if not dags_path.is_dir():
        console.get_console().print(constants.CREATING_DAGS_PATH_WARN.format(dags_path=dags_path))
        dags_path.mkdir(parents=True)


def get_available_environments(composer_dir: pathlib.Path):
    return [
        path
        for path in composer_dir.iterdir()
        if path.is_dir() and (path / "config.json").is_file()
    ]


def assert_dag_path_exists(path: str) -> None:
    if pathlib.Path(path).is_dir():
        return
    raise errors.DAGPathNotExistError(path)
