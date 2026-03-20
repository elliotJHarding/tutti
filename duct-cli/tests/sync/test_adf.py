"""Tests for ADF (Atlassian Document Format) to Markdown conversion."""

from duct.sync.adf import adf_to_markdown


class TestNoneAndEmpty:
    def test_none_returns_empty(self):
        assert adf_to_markdown(None) == ""

    def test_empty_dict_returns_empty(self):
        assert adf_to_markdown({}) == ""

    def test_empty_list_returns_empty(self):
        assert adf_to_markdown([]) == ""

    def test_doc_with_no_content(self):
        assert adf_to_markdown({"type": "doc"}) == ""

    def test_doc_with_empty_content(self):
        assert adf_to_markdown({"type": "doc", "content": []}) == ""


class TestPlainText:
    def test_simple_paragraph(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        assert adf_to_markdown(adf) == "Hello world"

    def test_multiple_paragraphs(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "First"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Second"}],
                },
            ],
        }
        assert adf_to_markdown(adf) == "First\nSecond"


class TestTextMarks:
    def test_code_mark(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "use "},
                        {"type": "text", "text": "foo()", "marks": [{"type": "code"}]},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "use `foo()`"

    def test_strong_mark(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "**bold**"

    def test_em_mark(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "italic", "marks": [{"type": "em"}]},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "*italic*"

    def test_strike_mark(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "removed", "marks": [{"type": "strike"}]},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "~~removed~~"

    def test_link_mark(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "click here",
                            "marks": [
                                {"type": "link", "attrs": {"href": "https://example.com"}}
                            ],
                        },
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "[click here](https://example.com)"

    def test_multiple_marks(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "important",
                            "marks": [{"type": "strong"}, {"type": "em"}],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "important" in result
        assert "**" in result
        assert "*" in result


class TestMention:
    def test_mention_with_text_attr(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "mention",
                            "attrs": {"id": "abc123", "text": "John Doe"},
                        }
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "@John Doe"

    def test_mention_already_prefixed(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "mention",
                            "attrs": {"id": "abc123", "text": "@Jane"},
                        }
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "@Jane"


class TestInlineNodes:
    def test_hard_break(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "line one"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "line two"},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "line one\nline two"

    def test_emoji(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "emoji", "attrs": {"shortName": ":thumbsup:"}},
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == ":thumbsup:"

    def test_inline_card(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "inlineCard",
                            "attrs": {"url": "https://jira.example.com/browse/PROJ-1"},
                        }
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "https://jira.example.com/browse/PROJ-1"


class TestHeading:
    def test_h1(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 1},
                    "content": [{"type": "text", "text": "Title"}],
                }
            ],
        }
        assert adf_to_markdown(adf) == "# Title"

    def test_h3(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 3},
                    "content": [{"type": "text", "text": "Subsection"}],
                }
            ],
        }
        assert adf_to_markdown(adf) == "### Subsection"


class TestCodeBlock:
    def test_code_block_with_language(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": "print('hi')"}],
                }
            ],
        }
        assert adf_to_markdown(adf) == "```python\nprint('hi')\n```"

    def test_code_block_no_language(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "content": [{"type": "text", "text": "some code"}],
                }
            ],
        }
        assert adf_to_markdown(adf) == "```\nsome code\n```"


class TestBlockquote:
    def test_simple_blockquote(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "quoted text"}],
                        }
                    ],
                }
            ],
        }
        assert adf_to_markdown(adf) == "> quoted text"


class TestLists:
    def test_bullet_list(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "alpha"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "beta"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "- alpha" in result
        assert "- beta" in result

    def test_ordered_list(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "first"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "second"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "1. first" in result
        assert "2. second" in result

    def test_nested_list(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "parent"}],
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {"type": "text", "text": "child"}
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert result == "- parent\n  - child"

    def test_nested_ordered_list(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "parent"}],
                                },
                                {
                                    "type": "bulletList",
                                    "content": [
                                        {
                                            "type": "listItem",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {"type": "text", "text": "child"}
                                                    ],
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert result == "1. parent\n   - child"

    def test_nested_ordered_list_double_digit(self):
        items = []
        for n in range(10):
            item = {
                "type": "listItem",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": f"item {n + 1}"}],
                    }
                ],
            }
            if n == 9:
                item["content"].append(
                    {
                        "type": "bulletList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "sub"}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                )
            items.append(item)

        adf = {
            "type": "doc",
            "content": [{"type": "orderedList", "content": items}],
        }
        result = adf_to_markdown(adf)
        lines = result.strip().split("\n")
        assert lines[-2] == "10. item 10"
        assert lines[-1] == "    - sub"


class TestMedia:
    def test_media_single(self):
        adf = {
            "type": "doc",
            "content": [{"type": "mediaSingle", "content": [{"type": "media"}]}],
        }
        assert "[media attachment]" in adf_to_markdown(adf)

    def test_media_node(self):
        adf = {
            "type": "doc",
            "content": [{"type": "media", "attrs": {"id": "abc", "type": "file"}}],
        }
        assert "[media attachment]" in adf_to_markdown(adf)


class TestRule:
    def test_horizontal_rule(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "above"}],
                },
                {"type": "rule"},
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "below"}],
                },
            ],
        }
        result = adf_to_markdown(adf)
        assert "---" in result
        assert "above" in result
        assert "below" in result


class TestTable:
    def test_simple_table_with_headers(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableHeader",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Name"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableHeader",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "Value"}],
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "foo"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "bar"}],
                                        }
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "| Name | Value |" in result
        assert "| --- | --- |" in result
        assert "| foo | bar |" in result

    def test_table_without_headers(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "a"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "b"}],
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "c"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "d"}],
                                        }
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "| a | b |" in result
        assert "| --- | --- |" in result
        assert "| c | d |" in result


class TestPanel:
    def test_panel_with_type(self):
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "attrs": {"panelType": "warning"},
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "Be careful"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_markdown(adf)
        assert "[warning]" in result
        assert "Be careful" in result


class TestListInput:
    def test_raw_list_input(self):
        """adf_to_markdown should accept a raw list of nodes."""
        nodes = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "one"}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "two"}],
            },
        ]
        result = adf_to_markdown(nodes)
        assert "one" in result
        assert "two" in result


class TestComplexDocument:
    def test_mixed_content(self):
        """Simulate a realistic Jira description with mixed node types."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": [{"type": "text", "text": "Summary"}],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Assigned to "},
                        {
                            "type": "mention",
                            "attrs": {"id": "u1", "text": "Alice"},
                        },
                        {"type": "text", "text": " - see "},
                        {
                            "type": "text",
                            "text": "the docs",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "https://docs.example.com"},
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Run "},
                        {
                            "type": "text",
                            "text": "make test",
                            "marks": [{"type": "code"}],
                        },
                        {"type": "text", "text": " to verify."},
                    ],
                },
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Step one"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Step two",
                                            "marks": [{"type": "strong"}],
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "type": "codeBlock",
                    "attrs": {"language": "bash"},
                    "content": [{"type": "text", "text": "echo hello"}],
                },
            ],
        }
        result = adf_to_markdown(adf)
        assert "## Summary" in result
        assert "@Alice" in result
        assert "[the docs](https://docs.example.com)" in result
        assert "`make test`" in result
        assert "- Step one" in result
        assert "- **Step two**" in result
        assert "```bash" in result
        assert "echo hello" in result

    def test_unknown_node_type_is_handled(self):
        """Unknown node types should not crash, just recurse into content."""
        adf = {
            "type": "doc",
            "content": [
                {
                    "type": "someNewNodeType",
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "still works"}],
                        }
                    ],
                }
            ],
        }
        assert "still works" in adf_to_markdown(adf)
