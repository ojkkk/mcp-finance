"""Static stock metadata regression tests."""

from mcp_finance.data import STOCK_MAPPING


def test_stock_codes_are_not_overwritten_by_wrong_company():
    assert STOCK_MAPPING["600690"] == "海尔智家"
    assert STOCK_MAPPING["601989"] == "中国重工"
