"""Small, literal-text Markdown tables shared by reports and approvals."""
from html import escape


def table_markdown(rows: list[dict]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(key for row in rows for key in row))

    def cell(value):
        text = str(value).replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        return "".join(f"&#{ord(char)};" if char in "\\|`*_[]<>~$!#{}()" else escape(char) for char in text)

    def row(values):
        return "| " + " | ".join(cell(value) for value in values) + " |"

    return "\n".join([
        row(columns),
        "| " + " | ".join("---" for _ in columns) + " |",
        *(row(item.get(column, "") for column in columns) for item in rows),
    ])
