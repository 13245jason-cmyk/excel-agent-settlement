import pytest

from app_ui import table_markdown


def test_report_table_preserves_displayed_amounts_and_column_order():
    table = table_markdown([
        {"遊戲類型": "Slots", "有效投注": "1,000.00", "佣金": "25.80"},
        {"遊戲類型": "Sports", "有效投注": "500.00", "佣金": "0.00"},
    ])
    assert table.splitlines()[0] == "| 遊戲類型 | 有效投注 | 佣金 |"
    assert "| Slots | 1,000.00 | 25.80 |" in table
    assert "| Sports | 500.00 | 0.00 |" in table
    assert "<table" not in table and "<div" not in table


@pytest.mark.parametrize("filename", [
    '<img src=x onerror="alert(1)"> & report.xlsx',
    '[click](https://example.com) ![image](x).xlsx',
    'one|two\r\nthree.xlsx',
    '`code` **bold** _italic_ $math$.xlsx',
])
def test_report_table_treats_filenames_as_literal_single_cell(filename):
    table = table_markdown([{"<script>alert(1)</script>": filename}])
    assert len(table.splitlines()) == 3
    assert table.count("|") == 6
    for syntax in ('<script', '<img', '<div', '![', '[click]', '`', '**', '_', '$'):
        assert syntax not in table
    if '&' in filename:
        assert '&amp;' in table


def test_empty_report_table_does_not_invent_rows():
    assert table_markdown([]) == ""
