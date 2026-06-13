"""
composer-local CLI ツール

ローカル Composer 環境（Docker）を操作するためのコマンド群を提供します。
- 環境の起動/停止/削除
- ログ表示や Airflow コマンドの実行
- Cloud Composer からの Variables・設定同期
"""

import logging
import pathlib
import shutil
from typing import List, Optional

import click

from composer_local import composer_settings, console, constants, errors, files, utils, version
from composer_local import environment as composer_environment

LOG = logging.getLogger(__name__)


class LogsMaxLines(click.ParamType):
    name = "max_lines"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        if value == "all":
            return value
        try:
            number = int(value)
            if number < 1:
                raise ValueError("Not a positive number.")
            return number
        except ValueError:
            self.fail(f"{value!r} is not a positive integer or 'all' keyword", param, ctx)


@click.group(name="composer-local")
@click.version_option(version=version.__version__, prog_name="composer-local")
@click.option("--verbose", is_flag=True, default=False, help="詳細なログを表示する")
@click.option("--debug", is_flag=True, default=False, help="デバッグログを表示する")
@click.pass_context
def cli(ctx, verbose, debug):
    """ローカル Composer 環境を管理する CLI ツールです。

    Docker を使用して Cloud Composer 互換の Airflow 環境を
    ローカルで作成・起動・管理できます。

    基本的な使い方:
      composer-local start ENV
      composer-local logs ENV --follow
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug
    utils.setup_logging(verbose, debug)


option_port = click.option(
    "--web-server-port",
    "--port",
    type=click.IntRange(min=1, max=65535),
    help="Airflow Web サーバーのポート",
    show_default="設定ファイルから読み込み",
    metavar="PORT",
)


required_environment = click.argument(
    "environment", required=True, metavar="LOCAL_ENVIRONMENT_NAME"
)
optional_environment = click.argument(
    "environment", required=False, metavar="LOCAL_ENVIRONMENT_NAME"
)


@cli.command()
@optional_environment
@option_port
@click.option(
    "--image-version",
    default=None,
    help=f"Composer イメージ バージョン（参考: {constants.COMPOSER_VERSIONING_DOCS_LINK}）",
    show_default="composer_settings.COMPOSER_IMAGE_VERSION",
    metavar="COMPOSER_VERSION",
)
@click.option(
    "-p",
    "--project",
    default=None,
    help="使用する Google Cloud プロジェクト ID",
    metavar="PROJECT_ID",
)
@click.option(
    "--dags-path",
    default=None,
    help="DAGs フォルダのパス（無ければ作成されます）",
    show_default="カレントディレクトリの 'dags'",
    metavar="PATH",
    type=click.Path(file_okay=False),
)
@click.option(
    "--database",
    "database_engine",
    default=constants.DatabaseEngine.postgresql,
    show_default=True,
    type=click.Choice(constants.DatabaseEngine.choices(), case_sensitive=False),
    metavar="DATABASE_ENGINE",
)
@errors.catch_exceptions()
def start(
    environment: Optional[str],
    web_server_port: Optional[int],
    image_version: Optional[str],
    project: Optional[str],
    dags_path: Optional[str],
    database_engine: str,
) -> None:
    """環境を起動する。環境が存在しない場合は自動作成する。"""
    env_name = environment or composer_settings.LOCAL_ENV_NAME
    env_dir = pathlib.Path("composer", env_name)
    if not (env_dir / "config.json").is_file():
        print(f"{constants.ANSI_BLUE}環境が存在しません。作成しています...{constants.ANSI_RESET}")
        utils.assert_environment_name_is_valid(env_name)
        env = composer_environment.Environment(
            image_version=image_version or composer_settings.COMPOSER_IMAGE_VERSION,
            project_id=utils.resolve_project_id(project),
            location=composer_settings.COMPOSER_LOCATION or "asia-northeast1",
            env_dir_path=env_dir,
            port=web_server_port,
            dags_path=dags_path or str(pathlib.Path.cwd() / composer_settings.DAGS_PATH),
            database_engine=database_engine,
        )
        env.create()
    env_path = files.resolve_environment_path(env_name)
    env = composer_environment.Environment.load_from_config(env_path, web_server_port)
    env.start_foreground()


@cli.command()
@optional_environment
@errors.catch_exceptions()
def stop(environment: Optional[str]) -> None:
    print(f"{constants.ANSI_YELLOW}環境を停止しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.stop()
    print(f"{constants.ANSI_GREEN}環境が停止しました。{constants.ANSI_RESET}")


@cli.command()
@optional_environment
@errors.catch_exceptions()
def status(environment: Optional[str]) -> None:
    """環境の一覧と詳細を表示する。"""
    current_path = pathlib.Path.cwd().resolve()
    envs = files.get_environment_directories()
    if not envs:
        console.get_console().print(constants.ENVIRONMENTS_NOT_FOUND.format(path=current_path))
        return
    environments_status = composer_environment.get_environments_status(envs)
    console.get_console().print(constants.ENVIRONMENTS_FOUND.format(path=current_path))
    console.get_console().print(utils.get_environment_status_table(environments_status))
    if environment or len(envs) == 1:
        env_path = files.resolve_environment_path(environment)
        env = composer_environment.Environment.load_from_config(env_path, None)
        env.describe()


@cli.command()
@optional_environment
@click.option("-f", "--follow", is_flag=True, default=False, help="ログを追尾表示する")
@click.option(
    "-l",
    "--max-lines",
    default="all",
    type=LogsMaxLines(),
    help="表示する最大行数",
    metavar="MAX_LINES",
)
@errors.catch_exceptions()
def logs(environment: Optional[str], max_lines, follow: bool) -> None:
    print(f"{constants.ANSI_BLUE}ログを表示しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.logs(follow, max_lines)


@cli.command(name="run", context_settings=dict(ignore_unknown_options=True))
@required_environment
@click.argument("command", nargs=-1, required=True, metavar="COMMAND", type=click.UNPROCESSED)
@click.pass_context
@errors.catch_exceptions()
def run(ctx, environment: Optional[str], command: List[str]):
    """コンテナ内で airflow コマンドを実行する。"""
    if ctx.obj.get("verbose", False):
        print(
            f"{constants.ANSI_BLUE}Airflowコマンドを実行しています: "
            f"{' '.join(command)}{constants.ANSI_RESET}"
        )
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.run_airflow_command([*command])


@cli.command()
@optional_environment
@click.option(
    "--settings",
    "settings_only",
    is_flag=True,
    default=False,
    help="Variables ではなく Composer の設定を composer_settings.py に同期する",
)
@click.option(
    "--secret-id",
    default=None,
    metavar="SECRET_ID",
    help="指定時は Secret Manager 経由で Variables を同期する",
)
@click.option("-p", "--project", default=None, metavar="PROJECT_ID", help="GCP プロジェクト ID")
@click.option(
    "-l",
    "--location",
    default=composer_settings.COMPOSER_LOCATION,
    show_default=True,
    metavar="LOCATION",
)
@click.option(
    "-e",
    "--env-name",
    "env_name",
    default=composer_settings.COMPOSER_ENV_NAME,
    show_default=True,
    metavar="ENV_NAME",
    help="同期元の Cloud Composer 環境名",
)
@errors.catch_exceptions()
def sync(
    environment: Optional[str],
    settings_only: bool,
    secret_id: Optional[str],
    project: Optional[str],
    location: str,
    env_name: str,
):
    """Cloud Composer から Variables（既定）または設定を同期する。"""
    from composer_local import gcp_sync

    resolved_project = project or composer_settings.PROJECT_ID or gcp_sync.get_project_id()
    if not resolved_project:
        raise click.UsageError(
            "GCP プロジェクト ID を解決できませんでした。--project を指定してください。"
        )
    if not env_name and not settings_only:
        raise click.UsageError(
            "Cloud Composer 環境名が未設定です。--env-name を指定するか "
            "composer_settings.py に COMPOSER_ENV_NAME を設定してください。"
        )

    if settings_only:
        print(
            f"{constants.ANSI_BLUE}Cloud Composer の設定を同期しています...{constants.ANSI_RESET}"
        )
        settings_path = pathlib.Path(__file__).parent / "composer_settings.py"
        gcp_sync.sync_composer_settings(
            project_id=resolved_project,
            location=location,
            env_name=env_name,
            settings_file=settings_path,
        )
        print(
            f"{constants.ANSI_GREEN}設定の同期が完了しました: {settings_path}{constants.ANSI_RESET}"
        )
        return

    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    print(f"{constants.ANSI_BLUE}Variables を同期しています...{constants.ANSI_RESET}")
    if secret_id:
        gcp_sync.sync_vars_via_secret_manager(
            env, env_path, resolved_project, location, env_name, secret_id
        )
    else:
        gcp_sync.sync_vars_direct(env, env_path, resolved_project, location, env_name)
    print(f"{constants.ANSI_GREEN}Variables の同期が完了しました。{constants.ANSI_RESET}")


@cli.command()
@optional_environment
@click.option(
    "--skip-confirmation",
    is_flag=True,
    default=False,
    help="削除前の確認を省略する",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="実行中でも強制的に削除する",
)
@errors.catch_exceptions()
def remove(environment: Optional[str], skip_confirmation: bool, force: bool) -> None:
    print(f"{constants.ANSI_YELLOW}環境を削除しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    if not skip_confirmation:
        click.confirm(
            constants.REMOVE_ENV_CONFIRMATION_PROMPT.format(env_path=env_path), abort=True
        )
    try:
        env = composer_environment.Environment.load_from_config(env_path, None)
    except errors.InvalidConfigurationError:
        console.get_console().print(
            f"{constants.ANSI_YELLOW}警告: 設定ファイルが破損しています。{constants.ANSI_RESET}"
        )
        if force:
            # 設定ファイルが破損しているため Environment オブジェクトを
            # 生成できず、Docker SDK 経由での操作ができない。
            # フォールバックとして docker CLI を直接呼び出し、
            # コンテナを強制削除する。
            import subprocess

            env_name = env_path.name
            container_names = [
                f"{constants.CONTAINER_NAME}-{env_name}",
                f"{constants.DB_CONTAINER_NAME}-{env_name}",
            ]
            for name in container_names:
                try:
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
                except Exception:
                    pass
    else:
        env.remove(force, force_error=click.UsageError(constants.USE_FORCE_TO_REMOVE_ERROR))
    shutil.rmtree(env_path)
    print(f"{constants.ANSI_GREEN}環境の削除が完了しました。{constants.ANSI_RESET}")
