import pytest

from pricing import total_with_tax


def test_total_with_tax():
    assert total_with_tax(100) == pytest.approx(110.0)
