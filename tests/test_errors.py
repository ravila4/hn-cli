from hn_cli.errors import HNAPIError


def test_hnapierror_carries_status_and_url():
    err = HNAPIError(status_code=503, url="https://example.com/x", message="Service Unavailable")
    assert err.status_code == 503
    assert err.url == "https://example.com/x"
    assert err.message == "Service Unavailable"


def test_hnapierror_str_is_human_readable():
    err = HNAPIError(status_code=404, url="https://hn.algolia.com/api/v1/items/999")
    s = str(err)
    assert "404" in s
    assert "hn.algolia.com/api/v1/items/999" in s


def test_hnapierror_is_an_exception():
    with __import__("pytest").raises(HNAPIError):
        raise HNAPIError(status_code=500, url="https://example.com/x")
