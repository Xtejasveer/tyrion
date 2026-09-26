from strings_util import is_palindrome


def test_palindrome():
    assert is_palindrome("racecar") is True
    assert is_palindrome("hello") is False
    assert is_palindrome("") is True
