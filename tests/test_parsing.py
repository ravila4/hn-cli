import pytest

from hn_cli.parsing import parse_duration, parse_item_id


class TestParseItemId:
    def test_accepts_int(self):
        assert parse_item_id(12345) == 12345

    def test_accepts_decimal_string(self):
        assert parse_item_id("12345") == 12345

    def test_accepts_hn_item_url(self):
        assert parse_item_id("https://news.ycombinator.com/item?id=48052537") == 48052537

    def test_accepts_hn_item_url_http(self):
        assert parse_item_id("http://news.ycombinator.com/item?id=42") == 42

    def test_accepts_hn_item_url_with_extra_query(self):
        assert parse_item_id("https://news.ycombinator.com/item?id=42&p=2") == 42

    def test_strips_whitespace(self):
        assert parse_item_id("  12345  ") == 12345

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            parse_item_id("")

    def test_rejects_non_numeric_string(self):
        with pytest.raises(ValueError):
            parse_item_id("not_a_number")

    def test_rejects_unrelated_url(self):
        with pytest.raises(ValueError):
            parse_item_id("https://example.com/foo")

    def test_rejects_hn_url_with_non_decimal_id(self):
        with pytest.raises(ValueError):
            parse_item_id("https://news.ycombinator.com/item?id=abc")

    def test_rejects_hn_url_missing_id(self):
        with pytest.raises(ValueError):
            parse_item_id("https://news.ycombinator.com/item")

    def test_rejects_zero_or_negative(self):
        with pytest.raises(ValueError):
            parse_item_id(0)
        with pytest.raises(ValueError):
            parse_item_id(-1)
        with pytest.raises(ValueError):
            parse_item_id("-1")


class TestParseDuration:
    def test_seconds(self):
        assert parse_duration("30s") == 30

    def test_minutes(self):
        assert parse_duration("30m") == 30 * 60

    def test_hours(self):
        assert parse_duration("24h") == 24 * 3600

    def test_days(self):
        assert parse_duration("7d") == 7 * 86400

    def test_weeks(self):
        assert parse_duration("2w") == 2 * 7 * 86400

    def test_years(self):
        assert parse_duration("1y") == 365 * 86400

    def test_case_insensitive(self):
        assert parse_duration("7D") == 7 * 86400

    def test_strips_whitespace(self):
        assert parse_duration("  7d  ") == 7 * 86400

    def test_zero_duration_is_allowed(self):
        assert parse_duration("0d") == 0

    @pytest.mark.parametrize("bad", ["", "7", "7x", "-7d", "d7", "abc", "1.5d"])
    def test_rejects_bad_input(self, bad):
        with pytest.raises(ValueError):
            parse_duration(bad)

    def test_error_message_lists_accepted_forms(self):
        # Agents that fed e.g. "two weeks" had to dig through source for the
        # accepted vocabulary. The error itself should now say it.
        with pytest.raises(ValueError) as exc:
            parse_duration("two weeks")
        msg = str(exc.value)
        assert "7d" in msg or "24h" in msg
        for unit in ("s", "m", "h", "d", "w", "y"):
            assert unit in msg
