"""composer_local.constants のユニットテスト."""

import enum

from composer_local import constants


class TestDatabaseEngine:
    """DatabaseEngine のテスト."""

    def test_choices_returns_expected_list(self):
        """choices() が ["sqlite3", "postgresql"] を返す."""
        assert constants.DatabaseEngine.choices() == ["sqlite3", "postgresql"]

    def test_is_enum_subclass(self):
        """DatabaseEngine は enum.Enum のサブクラスである."""
        assert issubclass(constants.DatabaseEngine, enum.Enum)

    def test_is_str_enum(self):
        """DatabaseEngine は str のサブクラスでもある."""
        assert issubclass(constants.DatabaseEngine, str)

    def test_sqlite3_value(self):
        """sqlite3 の値が "sqlite3" である."""
        assert constants.DatabaseEngine.sqlite3.value == "sqlite3"

    def test_postgresql_value(self):
        """postgresql の値が "postgresql" である."""
        assert constants.DatabaseEngine.postgresql.value == "postgresql"

    def test_member_count(self):
        """メンバーが 2 つだけ存在する."""
        assert len(constants.DatabaseEngine) == 2


class TestContainerStatus:
    """ContainerStatus のテスト."""

    def test_running_value(self):
        """ContainerStatus.RUNNING が "running" である."""
        assert constants.ContainerStatus.RUNNING == "running"
        assert constants.ContainerStatus.RUNNING.value == "running"

    def test_created_value(self):
        """ContainerStatus.CREATED が "created" である."""
        assert constants.ContainerStatus.CREATED == "created"
        assert constants.ContainerStatus.CREATED.value == "created"

    def test_is_enum_subclass(self):
        """ContainerStatus は enum.Enum のサブクラスである."""
        assert issubclass(constants.ContainerStatus, enum.Enum)

    def test_is_str_enum(self):
        """ContainerStatus は str のサブクラスでもある."""
        assert issubclass(constants.ContainerStatus, str)

    def test_string_comparison(self):
        """文字列との直接比較が可能."""
        assert constants.ContainerStatus.RUNNING == "running"
        assert "running" == constants.ContainerStatus.RUNNING


class TestImageVersionPattern:
    """IMAGE_VERSION_PATTERN 定数のテスト."""

    def test_pattern_is_defined(self):
        """IMAGE_VERSION_PATTERN が定義されている."""
        assert hasattr(constants, "IMAGE_VERSION_PATTERN")
        assert isinstance(constants.IMAGE_VERSION_PATTERN, str)
        assert len(constants.IMAGE_VERSION_PATTERN) > 0
