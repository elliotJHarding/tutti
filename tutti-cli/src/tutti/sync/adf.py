"""Convert Atlassian Document Format (ADF) JSON to Markdown.

ADF is the rich text format used by Jira for descriptions, comments, and other
text fields. This module walks the nested node tree and produces readable markdown.
"""

from __future__ import annotations


def adf_to_markdown(adf: dict | list | None) -> str:
    """Convert an ADF document to a markdown string.

    Accepts the top-level ADF dict (with type "doc"), a raw content list,
    or None. Returns an empty string for None/empty input.
    """
    if adf is None:
        return ""
    if isinstance(adf, list):
        return "".join(_convert_node(n) for n in adf)
    if isinstance(adf, dict):
        return _convert_node(adf).strip()
    return ""


def _convert_node(node: dict) -> str:
    """Dispatch on node type and return the markdown representation."""
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type", "")
    content = node.get("content") or []

    match node_type:
        case "doc":
            return _walk_children(content)

        case "text":
            return _convert_text(node)

        case "mention":
            attrs = node.get("attrs") or {}
            name = attrs.get("text", "unknown")
            # Jira sometimes prefixes the mention text with @
            if name.startswith("@"):
                return name
            return f"@{name}"

        case "hardBreak":
            return "\n"

        case "emoji":
            attrs = node.get("attrs") or {}
            return attrs.get("shortName") or attrs.get("text") or ""

        case "inlineCard":
            attrs = node.get("attrs") or {}
            return attrs.get("url", "")

        case "paragraph":
            return f"{_walk_children(content)}\n"

        case "heading":
            attrs = node.get("attrs") or {}
            level = attrs.get("level", 1)
            prefix = "#" * level
            return f"{prefix} {_walk_children(content)}\n"

        case "codeBlock":
            attrs = node.get("attrs") or {}
            lang = attrs.get("language", "")
            inner = _walk_children(content)
            return f"```{lang}\n{inner}\n```\n"

        case "blockquote":
            inner = _walk_children(content)
            lines = inner.split("\n")
            # Strip trailing empty element from a final newline
            if lines and lines[-1] == "":
                lines = lines[:-1]
            quoted = "\n".join(f"> {line}" if line else ">" for line in lines)
            return f"{quoted}\n"

        case "bulletList":
            return _convert_list_items(content, ordered=False)

        case "orderedList":
            return _convert_list_items(content, ordered=True)

        case "listItem":
            return _walk_children(content)

        case "mediaSingle" | "media":
            return "[media attachment]\n"

        case "rule":
            return "---\n"

        case "table":
            return _convert_table(content)

        case "tableRow":
            return _walk_children(content)

        case "tableCell" | "tableHeader":
            return _walk_children(content)

        case "panel":
            attrs = node.get("attrs") or {}
            panel_type = attrs.get("panelType", "info")
            inner = _walk_children(content)
            return f"[{panel_type}] {inner}"

        case _:
            return _walk_children(content)


def _walk_children(content: list) -> str:
    """Recursively process a list of child nodes."""
    return "".join(_convert_node(child) for child in content)


def _convert_text(node: dict) -> str:
    """Convert a text node, applying any marks (code, strong, em, link)."""
    text = node.get("text", "")
    marks = node.get("marks") or []

    for mark in marks:
        mark_type = mark.get("type", "")
        match mark_type:
            case "code":
                text = f"`{text}`"
            case "strong":
                text = f"**{text}**"
            case "em":
                text = f"*{text}*"
            case "link":
                attrs = mark.get("attrs") or {}
                href = attrs.get("href", "")
                text = f"[{text}]({href})"
            case "strike":
                text = f"~~{text}~~"

    return text


def _convert_list_items(content: list, *, ordered: bool) -> str:
    """Convert list item nodes into markdown list syntax."""
    result = []
    for i, item in enumerate(content):
        if not isinstance(item, dict):
            continue
        inner_content = item.get("content") or []
        parts = []
        nested_lists = []
        for child in inner_content:
            if not isinstance(child, dict):
                continue
            if child.get("type") in ("bulletList", "orderedList"):
                nested_lists.append(child)
            else:
                parts.append(_convert_node(child))

        text = "".join(parts).strip()
        prefix = f"{i + 1}. " if ordered else "- "
        result.append(f"{prefix}{text}\n")

        for nested in nested_lists:
            nested_md = _convert_node(nested)
            # Indent nested list items
            for line in nested_md.split("\n"):
                if line:
                    result.append(f"  {line}\n")

    return "".join(result)


def _convert_table(rows: list) -> str:
    """Convert ADF table rows into a markdown table."""
    if not rows:
        return ""

    parsed_rows: list[list[str]] = []
    header_row_count = 0

    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "tableRow":
            continue
        cells = row.get("content") or []
        row_cells = []
        is_header = False
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            if cell.get("type") == "tableHeader":
                is_header = True
            cell_text = _walk_children(cell.get("content") or []).strip()
            row_cells.append(cell_text)
        if is_header and not parsed_rows:
            header_row_count = 1
        parsed_rows.append(row_cells)

    if not parsed_rows:
        return ""

    # Determine column count from widest row
    col_count = max(len(r) for r in parsed_rows)
    # Pad rows to equal length
    for row in parsed_rows:
        while len(row) < col_count:
            row.append("")

    lines = []
    for i, row in enumerate(parsed_rows):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if i == 0 and header_row_count:
            divider = "| " + " | ".join("---" for _ in row) + " |"
            lines.append(divider)

    # If there was no header row, still add a divider after the first row
    if not header_row_count and len(parsed_rows) > 1:
        line = lines[0]
        divider = "| " + " | ".join("---" for _ in parsed_rows[0]) + " |"
        lines.insert(1, divider)

    return "\n".join(lines) + "\n"
