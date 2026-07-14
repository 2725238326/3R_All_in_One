from pathlib import Path

import pytest

from runners.dream3r_runner import configure_dream3r_import_path


@pytest.mark.parametrize("package_parent", [Path("."), Path("code"), Path("src")])
def test_configure_dream3r_import_path_supports_common_repo_layouts(tmp_path, package_parent):
    package_root = tmp_path / package_parent
    package_dir = package_root / "dream3r"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")

    assert configure_dream3r_import_path(tmp_path) == package_root


def test_configure_dream3r_import_path_reports_checked_locations(tmp_path):
    with pytest.raises(RuntimeError, match="Dream3R Python 包未找到") as exc_info:
        configure_dream3r_import_path(tmp_path)

    assert str(tmp_path / "dream3r" / "__init__.py") in str(exc_info.value)
