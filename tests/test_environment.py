"""composer_local.environment のユニットテスト.

Docker に依存しない部分（EnvironmentConfig, Environment のプロパティ）をテストする。
Environment.__init__ で docker.from_env() が呼ばれるため、テスト時はモック化する。
"""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from composer_local import composer_settings, constants, errors
from composer_local.environment import Environment, EnvironmentConfig


# =============================================================================
# ヘルパー: config.json を一時ディレクトリに書き出す
# =============================================================================


def _write_config(tmp_path: pathlib.Path, config: dict) -> pathlib.Path:
    """config.json を tmp_path に書き出し、そのディレクトリパスを返す."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    return tmp_path


def _minimal_config(**overrides) -> dict:
    """必須パラメータを全て含む最小限の config 辞書を返す."""
    base = {
        "composer_project_id": "test-project",
        "composer_image_version": "composer-2.9.7-airflow-2.9.3",
        "composer_location": "us-central1",
        "dags_path": "/tmp/dags",
        "dag_dir_list_interval": 10,
        "database_engine": "postgresql",
    }
    base.update(overrides)
    return base


# =============================================================================
# EnvironmentConfig._get_int のテスト
# =============================================================================


class TestEnvironmentConfigGetInt:
    """_get_int メソッドのテスト."""

    def test_valid_int_within_range(self, tmp_path):
        """正常な整数値（範囲内）が正しく返されること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval=30))
        env_cfg = EnvironmentConfig(cfg, port=8080)
        assert env_cfg.dag_dir_list_interval == 30

    def test_valid_int_at_lower_bound(self, tmp_path):
        """下限値 (0) が正しく返されること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval=0))
        env_cfg = EnvironmentConfig(cfg, port=8080)
        assert env_cfg.dag_dir_list_interval == 0

    def test_negative_value_raises_range_error(self, tmp_path):
        """負の値は範囲外エラーになること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval=-1))
        with pytest.raises(errors.FailedToParseConfigParamIntRangeError):
            EnvironmentConfig(cfg, port=8080)

    def test_non_integer_string_raises_parse_error(self, tmp_path):
        """整数に変換できない文字列はパースエラーになること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval="abc"))
        with pytest.raises(errors.FailedToParseConfigParamIntError):
            EnvironmentConfig(cfg, port=8080)

    def test_float_string_raises_parse_error(self, tmp_path):
        """小数文字列は整数パースエラーになること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval="3.14"))
        with pytest.raises(errors.FailedToParseConfigParamIntError):
            EnvironmentConfig(cfg, port=8080)

    def test_string_number_is_accepted(self, tmp_path):
        """文字列形式の整数は正しく変換されること."""
        cfg = _write_config(tmp_path, _minimal_config(dag_dir_list_interval="42"))
        env_cfg = EnvironmentConfig(cfg, port=8080)
        assert env_cfg.dag_dir_list_interval == 42


# =============================================================================
# EnvironmentConfig._resolve_port のテスト
# =============================================================================


class TestEnvironmentConfigResolvePort:
    """_resolve_port メソッドのテスト."""

    def test_explicit_port_argument_takes_priority(self, tmp_path):
        """引数で明示的に指定された port が最優先されること."""
        cfg = _write_config(tmp_path, _minimal_config(port=9090))
        env_cfg = EnvironmentConfig(cfg, port=7070)
        assert env_cfg.port == 7070

    def test_config_json_port_used_when_no_argument(self, tmp_path):
        """引数 port が None のとき config.json の port が使われること."""
        cfg = _write_config(tmp_path, _minimal_config(port=9090))
        env_cfg = EnvironmentConfig(cfg, port=None)
        assert env_cfg.port == 9090

    def test_default_port_when_neither_argument_nor_config(self, tmp_path):
        """引数も config.json にも port がない場合、デフォルト値が使われること."""
        cfg = _write_config(tmp_path, _minimal_config())
        env_cfg = EnvironmentConfig(cfg, port=None)
        assert env_cfg.port == composer_settings.LOCAL_PORT

    def test_config_port_out_of_range_raises_error(self, tmp_path):
        """config.json の port が範囲外の場合エラーになること."""
        cfg = _write_config(tmp_path, _minimal_config(port=99999))
        with pytest.raises(errors.FailedToParseConfigParamIntRangeError):
            EnvironmentConfig(cfg, port=None)

    def test_config_port_non_integer_raises_error(self, tmp_path):
        """config.json の port が非整数の場合エラーになること."""
        cfg = _write_config(tmp_path, _minimal_config(port="not_a_number"))
        with pytest.raises(errors.FailedToParseConfigParamIntError):
            EnvironmentConfig(cfg, port=None)


# =============================================================================
# EnvironmentConfig: config.json ロード（from_config_json 相当）
# =============================================================================


class TestEnvironmentConfigLoad:
    """EnvironmentConfig のロード処理テスト."""

    def test_valid_config_loads_successfully(self, tmp_path):
        """正常な config.json が正しくロードされること."""
        cfg = _write_config(tmp_path, _minimal_config())
        env_cfg = EnvironmentConfig(cfg, port=8080)
        assert env_cfg.project_id == "test-project"
        assert env_cfg.image_version == "composer-2.9.7-airflow-2.9.3"
        assert env_cfg.location == "us-central1"
        assert env_cfg.dags_path == "/tmp/dags"
        assert env_cfg.dag_dir_list_interval == 10
        assert env_cfg.database_engine == "postgresql"

    def test_missing_project_id_raises_error(self, tmp_path):
        """必須パラメータ composer_project_id が欠けているとエラーになること."""
        config = _minimal_config()
        del config["composer_project_id"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_missing_image_version_raises_error(self, tmp_path):
        """必須パラメータ composer_image_version が欠けているとエラーになること."""
        config = _minimal_config()
        del config["composer_image_version"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_missing_location_raises_error(self, tmp_path):
        """必須パラメータ composer_location が欠けているとエラーになること."""
        config = _minimal_config()
        del config["composer_location"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_missing_dags_path_raises_error(self, tmp_path):
        """必須パラメータ dags_path が欠けているとエラーになること."""
        config = _minimal_config()
        del config["dags_path"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_missing_dag_dir_list_interval_raises_error(self, tmp_path):
        """必須パラメータ dag_dir_list_interval が欠けているとエラーになること."""
        config = _minimal_config()
        del config["dag_dir_list_interval"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_missing_database_engine_raises_error(self, tmp_path):
        """必須パラメータ database_engine が欠けているとエラーになること."""
        config = _minimal_config()
        del config["database_engine"]
        cfg = _write_config(tmp_path, config)
        with pytest.raises(errors.MissingRequiredParameterError):
            EnvironmentConfig(cfg, port=8080)

    def test_config_file_not_found_raises_error(self, tmp_path):
        """config.json が存在しない場合エラーになること."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        with pytest.raises(errors.ComposerCliError):
            EnvironmentConfig(empty_dir, port=8080)

    def test_invalid_json_raises_error(self, tmp_path):
        """JSON として不正な config.json はパースエラーになること."""
        config_path = tmp_path / "config.json"
        config_path.write_text("{invalid json}")
        with pytest.raises(errors.FailedToParseConfigError):
            EnvironmentConfig(tmp_path, port=8080)


# =============================================================================
# Environment プロパティ（Docker 不要な部分）のテスト
# =============================================================================


@pytest.fixture
def mock_docker_client():
    """Docker クライアントをモック化するフィクスチャ."""
    with patch("composer_local.environment.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_docker.errors = MagicMock()
        mock_docker.types = MagicMock()
        yield mock_client


@pytest.fixture
def sample_env(tmp_path, mock_docker_client):
    """テスト用の Environment インスタンスを作成するフィクスチャ."""
    env_dir = tmp_path / "test-env"
    env_dir.mkdir()
    dags_dir = env_dir / "dags"
    dags_dir.mkdir()
    return Environment(
        env_dir_path=env_dir,
        project_id="test-project",
        image_version="composer-2.9.7-airflow-2.9.3",
        location="us-central1",
        dags_path=str(dags_dir),
        dag_dir_list_interval=15,
        database_engine=constants.DatabaseEngine.postgresql,
        port=9090,
    )


class TestEnvironmentContainerName:
    """container_name プロパティのテスト."""

    def test_container_name_format(self, sample_env):
        """container_name が '{CONTAINER_NAME}-{env_name}' の形式であること."""
        expected = f"{constants.CONTAINER_NAME}-test-env"
        assert sample_env.container_name == expected

    def test_container_name_contains_prefix(self, sample_env):
        """container_name が定数プレフィックスを含むこと."""
        assert sample_env.container_name.startswith(constants.CONTAINER_NAME)

    def test_container_name_contains_env_name(self, sample_env):
        """container_name が環境名を含むこと."""
        assert sample_env.container_name.endswith("-test-env")


class TestEnvironmentDbContainerName:
    """db_container_name プロパティのテスト."""

    def test_db_container_name_format(self, sample_env):
        """db_container_name が '{DB_CONTAINER_NAME}-{env_name}' の形式であること."""
        expected = f"{constants.DB_CONTAINER_NAME}-test-env"
        assert sample_env.db_container_name == expected

    def test_db_container_name_contains_prefix(self, sample_env):
        """db_container_name が定数プレフィックスを含むこと."""
        assert sample_env.db_container_name.startswith(constants.DB_CONTAINER_NAME)

    def test_db_container_name_contains_env_name(self, sample_env):
        """db_container_name が環境名を含むこと."""
        assert sample_env.db_container_name.endswith("-test-env")


class TestEnvironmentDockerNetworkName:
    """docker_network_name プロパティのテスト."""

    def test_docker_network_name_format(self, sample_env):
        """docker_network_name が '{DOCKER_NETWORK_NAME}-{env_name}' の形式であること."""
        expected = f"{constants.DOCKER_NETWORK_NAME}-test-env"
        assert sample_env.docker_network_name == expected


class TestEnvironmentDefaultAirflowEnv:
    """_default_airflow_env メソッドのテスト."""

    def test_returns_dict(self, sample_env):
        """戻り値が辞書であること."""
        result = sample_env._default_airflow_env()
        assert isinstance(result, dict)

    def test_contains_airflow_home(self, sample_env):
        """AIRFLOW_HOME が含まれること."""
        result = sample_env._default_airflow_env()
        assert "AIRFLOW_HOME" in result
        assert result["AIRFLOW_HOME"] == "/home/airflow/airflow"

    def test_contains_dags_folder(self, sample_env):
        """AIRFLOW__CORE__DAGS_FOLDER が含まれること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__CORE__DAGS_FOLDER"] == "/home/airflow/gcs/dags"

    def test_contains_data_folder(self, sample_env):
        """AIRFLOW__CORE__DATA_FOLDER が含まれること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__CORE__DATA_FOLDER"] == "/home/airflow/gcs/data"

    def test_contains_plugins_folder(self, sample_env):
        """AIRFLOW__CORE__PLUGINS_FOLDER が含まれること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__CORE__PLUGINS_FOLDER"] == "/home/airflow/gcs/plugins"

    def test_load_examples_is_false(self, sample_env):
        """LOAD_EXAMPLES が false であること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__CORE__LOAD_EXAMPLES"] == "false"

    def test_dag_dir_list_interval_matches(self, sample_env):
        """DAG_DIR_LIST_INTERVAL が環境設定と一致すること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL"] == "15"

    def test_base_url_contains_port(self, sample_env):
        """BASE_URL がポート番号を含むこと."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__WEBSERVER__BASE_URL"] == "http://localhost:9090"

    def test_navbar_color_is_set(self, sample_env):
        """NAVBAR_COLOR が設定されていること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__WEBSERVER__NAVBAR_COLOR"] == "#e4007f"

    def test_composer_image_version_matches(self, sample_env):
        """COMPOSER_IMAGE_VERSION が環境設定と一致すること."""
        result = sample_env._default_airflow_env()
        assert result["COMPOSER_IMAGE_VERSION"] == "composer-2.9.7-airflow-2.9.3"

    def test_sql_alchemy_conn_contains_db_container_name(self, sample_env):
        """SQL_ALCHEMY_CONN が db_container_name を含むこと."""
        result = sample_env._default_airflow_env()
        conn = result["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
        assert sample_env.db_container_name in conn

    def test_sql_alchemy_conn_uses_postgres_settings(self, sample_env):
        """SQL_ALCHEMY_CONN が composer_settings の PostgreSQL 設定を使用すること."""
        result = sample_env._default_airflow_env()
        conn = result["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
        assert composer_settings.POSTGRES_USER in conn
        assert composer_settings.POSTGRES_DB in conn

    def test_standalone_dag_processor_false_for_composer2(self, sample_env):
        """Composer 2 では STANDALONE_DAG_PROCESSOR が False であること."""
        result = sample_env._default_airflow_env()
        assert result["AIRFLOW__SCHEDULER__STANDALONE_DAG_PROCESSOR"] == "False"

    def test_standalone_dag_processor_true_for_composer3(self, tmp_path, mock_docker_client):
        """Composer 3 では STANDALONE_DAG_PROCESSOR が True であること."""
        env_dir = tmp_path / "c3-env"
        env_dir.mkdir()
        dags_dir = env_dir / "dags"
        dags_dir.mkdir()
        env = Environment(
            env_dir_path=env_dir,
            project_id="test-project",
            image_version="composer-3-airflow-2.10.2",
            location="us-central1",
            dags_path=str(dags_dir),
            dag_dir_list_interval=10,
            database_engine=constants.DatabaseEngine.postgresql,
            port=8080,
        )
        result = env._default_airflow_env()
        assert result["AIRFLOW__SCHEDULER__STANDALONE_DAG_PROCESSOR"] == "True"

    def test_contains_host_user_name(self, sample_env):
        """COMPOSER_HOST_USER_NAME が含まれること."""
        result = sample_env._default_airflow_env()
        assert "COMPOSER_HOST_USER_NAME" in result
        # 値が空でないこと（実行ユーザー名が入る）
        assert result["COMPOSER_HOST_USER_NAME"] != ""


class TestEnvironmentDbEnv:
    """_db_env メソッドのテスト."""

    def test_returns_dict(self, sample_env):
        """戻り値が辞書であること."""
        result = sample_env._db_env()
        assert isinstance(result, dict)

    def test_contains_pgdata(self, sample_env):
        """PGDATA が含まれること."""
        result = sample_env._db_env()
        assert "PGDATA" in result
        assert result["PGDATA"] == "/var/lib/postgresql/data/pgdata"

    def test_contains_postgres_user(self, sample_env):
        """POSTGRES_USER が composer_settings の値と一致すること."""
        result = sample_env._db_env()
        assert result["POSTGRES_USER"] == composer_settings.POSTGRES_USER

    def test_contains_postgres_password(self, sample_env):
        """POSTGRES_PASSWORD が composer_settings の値と一致すること."""
        result = sample_env._db_env()
        assert result["POSTGRES_PASSWORD"] == composer_settings.POSTGRES_PASSWORD

    def test_contains_postgres_db(self, sample_env):
        """POSTGRES_DB が composer_settings の値と一致すること."""
        result = sample_env._db_env()
        assert result["POSTGRES_DB"] == composer_settings.POSTGRES_DB

    def test_has_exactly_four_keys(self, sample_env):
        """_db_env が正確に 4 つのキーを返すこと."""
        result = sample_env._db_env()
        assert len(result) == 4


class TestEnvironmentPort:
    """Environment の port プロパティのテスト."""

    def test_explicit_port(self, tmp_path, mock_docker_client):
        """明示的に指定された port が使われること."""
        env_dir = tmp_path / "port-test"
        env_dir.mkdir()
        dags_dir = env_dir / "dags"
        dags_dir.mkdir()
        env = Environment(
            env_dir_path=env_dir,
            project_id="test-project",
            image_version="composer-2.9.7-airflow-2.9.3",
            location="us-central1",
            dags_path=str(dags_dir),
            port=12345,
        )
        assert env.port == 12345

    def test_default_port_when_none(self, tmp_path, mock_docker_client):
        """port が None のときデフォルト値が使われること."""
        env_dir = tmp_path / "port-default"
        env_dir.mkdir()
        dags_dir = env_dir / "dags"
        dags_dir.mkdir()
        env = Environment(
            env_dir_path=env_dir,
            project_id="test-project",
            image_version="composer-2.9.7-airflow-2.9.3",
            location="us-central1",
            dags_path=str(dags_dir),
            port=None,
        )
        assert env.port == composer_settings.LOCAL_PORT
