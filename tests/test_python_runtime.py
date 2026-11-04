import pytest

from python_runtime import require_python39_for_real


@pytest.mark.parametrize("version", [(3, 9, 0), (3, 9, 23)])
def test_real_allows_python39(version):
    require_python39_for_real(version)


@pytest.mark.parametrize("version", [(3, 8, 20), (3, 10, 14), (3, 11, 9), (3, 13, 1)])
def test_real_rejects_other_versions(version):
    with pytest.raises(RuntimeError, match="Python 3.9"):
        require_python39_for_real(version)
