import pytest
from calculator import divide

def test_divide():
    assert divide(10, 2) == 5.0

def test_divide_by_zero():
    # Should handle divide by zero by returning "Error" or raising a specific exception
    # For this example, let's say it should return 0 or "Error"
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)
