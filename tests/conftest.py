"""composer-local-jp テスト用の共通フィクスチャ."""

import pathlib

import pytest


@pytest.fixture
def tmp_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """テスト用の一時ディレクトリを提供する."""
    return tmp_path


@pytest.fixture
def tmp_dags_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """テスト用の DAGs ディレクトリを作成して提供する."""
    dags = tmp_path / "dags"
    dags.mkdir()
    return dags


@pytest.fixture
def tmp_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """テスト用の一時ファイルを作成して提供する."""
    f = tmp_path / "tempfile.txt"
    f.write_text("test")
    return f
