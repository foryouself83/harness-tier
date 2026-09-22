"""The reader every design-doc rule stands on: a miscounted line or a table read under
the wrong heading turns into a violation pointing at the wrong place."""

from scripts._design_md import parse, split_front

DOC = """---
title: T
---
# Top

## 1. 개요
<a id="tbl-001"></a>**TBL-001** refers to [FR-PAY-001](../srs/pay.md#fr-pay-001) and ENT-002.

<!-- repeat: TBL -->
### {{TBL-ID}} name

| 컬럼명 | 타입 |
|---|---|
| id | int |
| `x|y` | a \\| b |

```mermaid
erDiagram
  A ||--o{ B : has
```

<!-- a comment
spanning FR-NOPE-001 lines -->
## 2. 끝 ##
"""


def test_front_matter_and_line_numbers():
    front, err, body, offset = split_front(DOC)
    assert front == {"title": "T"} and err is None and offset == 3
    doc = parse(DOC)
    assert [(h.level, h.text, h.line) for h in doc.headings] == [
        (1, "Top", 4),
        (2, "1. 개요", 6),
        (3, "{{TBL-ID}} name", 10),
        (2, "2. 끝", 24),
    ]


def test_table_path_header_rows():
    doc = parse(DOC)
    (table,) = doc.tables
    assert table.path == ("Top", "1. 개요", "{{TBL-ID}} name")
    assert table.header == ["컬럼명", "타입"]
    assert table.rows == [["id", "int"], ["`x|y`", "a \\| b"]]
    assert table.line == 12


def test_anchor_link_token_placeholder_repeat():
    doc = parse(DOC)
    assert doc.anchors == [("tbl-001", 7)]
    assert doc.links == [("../srs/pay.md", "fr-pay-001", 7)]
    assert ("FR-PAY-001", 7) in doc.tokens and ("ENT-002", 7) in doc.tokens
    assert ("TBL-001", 7) in doc.tokens
    assert doc.placeholders == [("{{TBL-ID}}", 10)]
    assert doc.repeats == [("TBL", 9)]


def test_comments_hide_tokens_and_fences_are_kept_apart():
    doc = parse(DOC)
    assert all(tok != "FR-NOPE-001" for tok, _ in doc.tokens)
    (fence,) = doc.fences
    assert fence.lang == "mermaid" and fence.line == 17
    assert fence.body.startswith("erDiagram")


def test_crlf_is_read_like_lf():
    assert parse(DOC.replace("\n", "\r\n")).headings == parse(DOC).headings


def test_section_end_and_between():
    doc = parse(DOC)
    assert doc.section_end(1) == 24
    assert doc.section_end(3) == doc.last_line + 1
    assert [t.line for t in doc.tables_between(6, 24)] == [12]
    assert "TBL-001" in doc.tokens_between(6, 24)


def test_broken_front_matter_is_reported_not_raised():
    doc = parse("---\n: [\n---\n# X\n")
    assert doc.front is None and doc.front_error


def test_fence_placeholder_only_when_the_whole_body_is_one_placeholder():
    doc = parse("```mermaid\n{{다이어그램}}\n```\n")
    assert doc.placeholders == [("{{다이어그램}}", 1)]


def test_fence_hexagon_node_is_content_not_a_placeholder():
    doc = parse("```mermaid\ngraph TD\n  A{{hex}} --> B\n```\n")
    assert doc.placeholders == []
