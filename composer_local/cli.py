"""
composer-local CLI ツール

ローカル Composer 環境（Docker）を操作するためのコマンド群を提供します。
- 環境の作成/起動/停止/再起動/削除
- ログ表示や Airflow コマンドの実行
- Secret Manager からの Variables 同期
"""

import logging
import pathlib
import shutil
from typing import List, Optional, Union

import click
import rich.markdown

from composer_local import composer_settings, console, constants
from composer_local import environment as composer_environment
from composer_local import errors, files, secret_manager_sync, utils, version
from composer_local.sync_settings import sync_composer_settings

LOG = logging.getLogger(__name__)


def apply_cli_option_format(name):
    return f"--{name.replace('_', '-')}"


class MutuallyExclusiveOption(click.Option):
    def __init__(self, *args, **kwargs):
        self.mutual = kwargs.pop("mutual")
        option_names = ", ".join(apply_cli_option_format(name) for name in self.mutual)
        kwargs["help"] = (
            f"{kwargs.get('help', '')}. Option is mutually exclusive with {option_names}."
        ).strip()
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        current_opt: bool = self.name in opts
        for mutex_opt in self.mutual:
            if mutex_opt in opts:
                if current_opt:
                    raise click.UsageError(
                        "Illegal usage: "
                        f"'{apply_cli_option_format(self.name)}' cannot be used together with "
                        f"'{apply_cli_option_format(mutex_opt)}'.",
                        ctx=ctx,
                    )
                else:
                    self.prompt = None
        return super().handle_parse_result(ctx, opts, args)


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
def cli():
    pass


verbose_mode = click.option("--verbose", is_flag=True, default=False, help="詳細なログを表示する")
debug_mode = click.option("--debug", is_flag=True, default=False, help="デバッグログを表示する")

option_port = click.option(
    "--web-server-port",
    "--port",
    type=click.IntRange(min=0, max=65536),
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
option_location = click.option(
    "-l",
    "--location",
    default=composer_settings.COMPOSER_LOCATION,
    show_default=True,
    help="ロケーションの ID または完全修飾 ID",
    metavar="LOCATION",
)


@cli.command()
@click.option(
    "--from-source-environment",
    cls=MutuallyExclusiveOption,
    mutual=["from_image_version"],
    help="複製元にする Composer 環境名",
    metavar="REMOTE_ENV_NAME",
)
@click.option(
    "--from-image-version",
    cls=MutuallyExclusiveOption,
    mutual=["from_source_environment"],
    help=f"Composer イメージ バージョン（参考: {constants.COMPOSER_VERSIONING_DOCS_LINK}）",
    metavar="COMPOSER_VERSION",
)
@click.option(
    "-p",
    "--project",
    help="使用する Google Cloud プロジェクト ID",
    show_default="Cloud CLI の設定値を使用",
    metavar="PROJECT_ID",
)
@option_location
@option_port
@click.option(
    "--dags-path",
    help="DAGs フォルダのパス（無ければ作成されます）",
    show_default="環境ディレクトリ配下の 'dags'",
    metavar="PATH",
    type=click.Path(file_okay=False),
)
@click.option(
    "--database-engine",
    "--database",
    help="Airflow メタデータ用のデータベース エンジン",
    default=constants.DatabaseEngine.postgresql,
    show_default=True,
    type=click.Choice(constants.DatabaseEngine.choices(), case_sensitive=False),
    metavar="DATABASE_ENGINE",
)
@required_environment
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def create(
    from_source_environment: str,
    from_image_version: str,
    project: Optional[str],
    location: str,
    web_server_port: Optional[int],
    environment: str,
    verbose: bool,
    debug: bool,
    database_engine: str,
    dags_path: Optional[pathlib.Path] = None,
):
    utils.setup_logging(verbose, debug)
    print(f"{constants.ANSI_BLUE}環境を作成しています...{constants.ANSI_RESET}")
    utils.assert_environment_name_is_valid(environment)
    if not from_source_environment and not from_image_version:
        raise click.UsageError(
            "環境の生成元が未指定です。--from-source-environment または --from-image-version を指定してください。"
        )
    project = utils.resolve_project_id(project)
    # 本ツールでは production プロジェクトは対象外
    if project and "production" in project.lower():
        raise click.UsageError(
            "ローカル Composer は本番プロジェクトを対象にできません: "
            f"{project}。代わりにステージング プロジェクトを使用してください。"
        )
    env_dir = pathlib.Path("composer", environment)
    if env_dir.is_dir():
        click.confirm(
            f"環境 '{env_dir}' は既に存在します。上書きしますか？",
            abort=True,
        )
        LOG.info("既存のローカル環境を上書きします。")

    if from_source_environment:
        env = composer_environment.Environment.from_source_environment(
            source_environment=from_source_environment,
            project=project,
            location=location,
            env_dir_path=env_dir,
            web_server_port=web_server_port,
            dags_path=dags_path,
            database_engine=database_engine,
        )
    else:
        env = composer_environment.Environment(
            image_version=from_image_version,
            project_id=project,
            location=location,
            env_dir_path=env_dir,
            port=web_server_port,
            dags_path=dags_path,
            database_engine=database_engine,
        )
    env.create()
    print(f"{constants.ANSI_GREEN}環境のセットアップを実行しています...{constants.ANSI_RESET}")

@cli.command()
@optional_environment
@option_port
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def start(environment: Optional[str], web_server_port: Optional[int], verbose: bool, debug: bool):
    utils.setup_logging(verbose, debug)
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, web_server_port)
    env.start_foreground()
    print(f"{constants.ANSI_GREEN}環境が起動しました。{constants.ANSI_RESET}")


@cli.command()
@optional_environment
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def stop(environment: Optional[str], verbose: bool, debug: bool):
    utils.setup_logging(verbose, debug)
    print(f"{constants.ANSI_YELLOW}環境を停止しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.stop()
    print(f"{constants.ANSI_GREEN}環境が停止しました。{constants.ANSI_RESET}")


@cli.command()
@optional_environment
@verbose_mode
@debug_mode
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
def logs(
    environment: Optional[str], max_lines: Union[str, int], follow: bool, verbose: bool, debug: bool
):
    utils.setup_logging(verbose, debug)
    print(f"{constants.ANSI_BLUE}ログを表示しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.logs(follow, max_lines)


@verbose_mode
@debug_mode
@cli.command(name="list")
@errors.catch_exceptions()
def list_command(verbose: bool, debug: bool):
    utils.setup_logging(verbose, debug)
    current_path = pathlib.Path.cwd().resolve()
    envs = files.get_environment_directories()
    environments_status = composer_environment.get_environments_status(envs)
    if environments_status:
        console.get_console().print(constants.ENVIRONMENTS_FOUND.format(path=current_path))
        table = utils.get_environment_status_table(environments_status)
        console.get_console().print(table)
        console.get_console().print(constants.LIST_COMMAND_EPILOG)
    else:
        console.get_console().print(constants.ENVIRONMENTS_NOT_FOUND.format(path=current_path))


@cli.command()
@optional_environment
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def describe(environment: Optional[str], verbose: bool, debug: bool):
    utils.setup_logging(verbose, debug)
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.describe()


@cli.command()
@optional_environment
@verbose_mode
@debug_mode
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
def remove(
    environment: Optional[str], verbose: bool, debug: bool, skip_confirmation: bool, force: bool
):
    utils.setup_logging(verbose, debug)
    print(f"{constants.ANSI_YELLOW}環境を削除しています...{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    if not skip_confirmation:
        click.confirm(
            constants.REMOVE_ENV_CONFIRMATION_PROMPT.format(env_path=env_path), abort=True
        )
    try:
        env = composer_environment.Environment.load_from_config(env_path, None)
    except errors.InvalidConfigurationError:
        md = rich.markdown.Markdown(constants.MALFORMED_CONFIG_REMOVING_CONTAINER)
        console.get_console().print(md)
    else:
        env.remove(force, force_error=click.UsageError(constants.USE_FORCE_TO_REMOVE_ERROR))
    shutil.rmtree(env_path)
    print(f"{constants.ANSI_GREEN}環境の削除が完了しました。{constants.ANSI_RESET}")


@cli.command(context_settings=dict(ignore_unknown_options=True))
@required_environment
@verbose_mode
@debug_mode
@click.argument("command", nargs=-1, required=True, metavar="COMMAND", type=click.UNPROCESSED)
@errors.catch_exceptions()
def run_airflow_cmd(environment: Optional[str], command: List[str], verbose: bool, debug: bool):
    utils.setup_logging(verbose, debug)
    # Contextual, friendly messages (default quiet)
    try:
        subcmd = command[0] if command else ""
        if subcmd == "users" and len(command) >= 2 and command[1] == "create":
            print(f"{constants.ANSI_BLUE}Web UI 用の管理者ユーザーを作成しています...{constants.ANSI_RESET}")
        elif (
            subcmd == "connections"
            and len(command) >= 4
            and command[1] == "add"
            and command[2] == "google_cloud_default"
        ):
            print(f"{constants.ANSI_BLUE}Google Cloud 接続を設定しています...{constants.ANSI_RESET}")
        elif verbose:
            cmd_str = ' '.join(command)
            print(f"{constants.ANSI_BLUE}Airflowコマンドを実行しています: {cmd_str}{constants.ANSI_RESET}")
    except Exception:
        # Fallback to verbose banner only
        if verbose:
            cmd_str = ' '.join(command)
            print(f"{constants.ANSI_BLUE}Airflowコマンドを実行しています: {cmd_str}{constants.ANSI_RESET}")
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)
    env.run_airflow_command([*command])


@cli.command(name="sync-vars")
@optional_environment
@click.option(
    "-p",
    "--project",
    help="使用する Google Cloud プロジェクト ID",
    show_default="Cloud CLI またはローカル環境設定の値",
    metavar="PROJECT_ID",
)
@click.option(
    "--secret-id",
    default=composer_settings.SECRET_ID,
    help="Airflow Variables の JSON を格納する Secret の ID",
    show_default=True,
    metavar="SECRET_ID",
)
@click.option(
    "--airflow-url",
    default=composer_settings.AIRFLOW_URL,
    help="ローカル Airflow の URL",
    show_default=True,
    metavar="URL",
)
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def sync_vars(
    environment: Optional[str],
    project: Optional[str],
    secret_id: str,
    airflow_url: str,  # 現在未使用だが、将来の拡張のため残す
    verbose: bool,
    debug: bool,
):
    """Secret Manager からローカル Airflow 環境へ Variables を同期する。

    - 指定（または推定）された GCP プロジェクトの Secret Manager から
      'secret_id' の最新バージョンを取得
    - 取得した JSON をローカル環境配下 data/variables.json に保存
    - Airflow が起動中であれば即時に `airflow variables import` を実行
      未起動であれば起動時に自動インポートされる
    """
    utils.setup_logging(verbose, debug)
    env_path = files.resolve_environment_path(environment)
    env = composer_environment.Environment.load_from_config(env_path, None)

    # Force staging usage for local composer
    resolved_project = project or env.project_id or utils.get_project_id()
    if resolved_project and "staging" not in resolved_project.lower():
        raise click.UsageError(
            "ローカル Composer はステージングのみに対応しています。"
            f"解決されたプロジェクト '{resolved_project}' はステージングではありません。"
        )
    # Prefer environment config if it clearly indicates staging
    if env.project_id and "staging" in env.project_id.lower():
        resolved_project = env.project_id
    if not resolved_project:
        raise click.UsageError(
            "GCP プロジェクト ID を解決できませんでした。--project を指定してください。"
        )

    console.get_console().print("Secret Manager から Variables を同期します...")
    console.get_console().print(f"プロジェクト: {resolved_project}")
    console.get_console().print(f"シークレット ID: {secret_id}")

    try:
        sync_client = secret_manager_sync.create_sync_client(
            project_id=resolved_project,
            local_env_path=env_path,
        )
        # ensure single-secret id is used
        sync_client.secret_id = secret_id

        # Secret ManagerからVariablesを同期（削除→インポートを統合処理）
        sync_client.sync_to_local_airflow(env)

        # Try to import into running local Airflow immediately;
        # otherwise leave for auto-import on next start
        variables_json_path = env_path / "data" / "variables.json"
        try:
            from composer_local import constants as _c

            if variables_json_path.is_file():
                try:
                    # If app is running, import now
                    status = env.status()
                    if str(status).lower() == str(_c.ContainerStatus.RUNNING):
                        console.get_console().print(
                            "起動中の Airflow へ Variables をインポートします..."
                        )
                        env.run_airflow_command(
                            [
                                "variables",
                                "import",
                                "/home/airflow/gcs/data/variables.json",
                            ]
                        )
                        # Remove after successful import
                        try:
                            variables_json_path.unlink()
                            console.get_console().print(
                                "一時ファイル variables.json を削除しました"
                            )
                        except Exception:
                            pass
                    else:
                        console.get_console().print(
                            "ローカル Airflow が起動していません。次回起動時に自動インポートされます。"
                        )
                except Exception as ie:
                    console.get_console().print(f"Variables のインポートに失敗しました: {ie}")
        except Exception:
            pass

        console.get_console().print("Variables の同期が完了しました！")

    except Exception as e:
        console.get_console().print(f"Variables の同期でエラーが発生しました: {e}")
        raise


@cli.command(name="sync-settings")
@click.option(
    "-p",
    "--project",
    help="GCP project id",
    required=True,
    metavar="PROJECT_ID",
)
@click.option(
    "-l",
    "--location",
    default=composer_settings.COMPOSER_LOCATION,
    show_default=True,
    metavar="LOCATION",
)
@click.option(
    "-e",
    "--env",
    "env_name",
    default=composer_settings.COMPOSER_ENV_NAME,
    show_default=True,
    metavar="ENV_NAME",
)
@verbose_mode
@debug_mode
@errors.catch_exceptions()
def sync_settings(project: str, location: str, env_name: str, verbose: bool, debug: bool):
    """Sync composer_local/composer_settings.py from Cloud Composer settings."""
    utils.setup_logging(verbose, debug)
    msg = "Cloud Composer の設定を composer_settings.py に同期しています..."
    print(f"{constants.ANSI_BLUE}{msg}{constants.ANSI_RESET}")
    settings_path = pathlib.Path(__file__).parent / "composer_settings.py"
    sync_composer_settings(
        project_id=project,
        location=location,
        env_name=env_name,
        settings_file=settings_path,
    )
    print(f"{constants.ANSI_GREEN}設定の同期が完了しました: {settings_path}{constants.ANSI_RESET}")
