from ai_player.ui.user_guide_render import html_items, html_list, table_rows


def test_html_items_wraps_trusted_fragments() -> None:
    assert html_items(["Plain", "<b>Rich</b>"]) == "<li>Plain</li><li><b>Rich</b></li>"


def test_html_list_uses_requested_list_type() -> None:
    assert html_list(["One", "Two"]) == "<ul><li>One</li><li>Two</li></ul>"
    assert html_list(["One"], ordered=True) == "<ol><li>One</li></ol>"


def test_table_rows_builds_cells_from_sequences() -> None:
    assert table_rows([("A", "B"), ("<code>C</code>", "D")]) == (
        "<tr><td>A</td><td>B</td></tr>\n"
        "<tr><td><code>C</code></td><td>D</td></tr>"
    )
