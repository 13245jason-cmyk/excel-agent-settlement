from html.parser import HTMLParser

from app_ui import table_html


class TableContent(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.tables = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "table":
            self.tables.append(dict(attrs))

    def handle_data(self, data):
        self.text.append(data)


def test_report_table_preserves_displayed_amounts_and_column_order():
    html = table_html([
        {"遊戲類型": "Slots", "有效投注": "1,000.00", "佣金": "25.80"},
        {"遊戲類型": "Sports", "有效投注": "500.00", "佣金": "0.00"},
    ], "遊戲明細")
    content = TableContent()
    content.feed(html)
    assert content.text == ["遊戲類型", "有效投注", "佣金", "Slots", "1,000.00", "25.80", "Sports", "500.00", "0.00"]
    assert content.tables == [{"aria-label": "遊戲明細"}]


def test_report_table_treats_labels_and_filenames_as_text():
    label = '" onclick="alert(1)'
    filename = '<img src=x onerror="alert(1)"> & report.xlsx'
    column = "<script>alert(1)</script>"
    content = TableContent()
    content.feed(table_html([{column: filename}], label))
    assert content.tables == [{"aria-label": label}]
    assert content.text == [column, filename]
    assert "script" not in content.tags and "img" not in content.tags


def test_empty_report_table_does_not_invent_rows():
    assert table_html([], "空明細") == ""
