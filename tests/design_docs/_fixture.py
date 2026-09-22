"""A host where every design doc passes, so each test breaks exactly one thing."""

from pathlib import Path

from tests.design_docs._helpers import write

TDIR = ".claude/harness-tier/templates/design-docs"

SRS_README = """---
wiki_id: srs.readme
title: SRS
tags: [srs]
---
# SRS
<a id="c-001"></a>**C-001** pay
<a id="nfr-perf-001"></a>**NFR-PERF-001** fast
"""

SRS_PAY = """---
wiki_id: srs.pay
title: Pay
tags: [srs]
---
# Pay
<a id="fr-pay-001"></a>**FR-PAY-001** charge (← [C-001](README.md#c-001))
"""

SDS = """---
wiki_id: sds.readme
title: SDS
tags: [sds]
sources: {}
---
# SDS
#### billing
- Implemented requirements: [FR-PAY-001](../srs/pay.md#fr-pay-001)

```mermaid
graph TD
  A --> B
```
"""

TEMPLATES = {
    "srs": "---\ndoc: srs\ntitle: 요구사항 명세서\nstandard: ISO/IEC/IEEE 29148\n"
    "sources: [docs/srs/README.md, docs/srs/*.md]\n---\n",
    "sds": "---\ndoc: sds\ntitle: 설계 명세서\nstandard: IEEE 1016\n"
    "sources: [docs/sds/*.md]\n---\n",
    "architecture": """---
doc: architecture
title: 아키텍처 설계서
standard: ISO/IEC/IEEE 42010
id_prefix: [CMP, IF]
refs: [C, FR, NFR]
---
## 1. 개요
## 2. 컴포넌트
<!-- repeat: CMP -->
### {{CMP-ID}} {{이름}}

| 항목 | 내용 |
|---|---|

## 3. 추적표

| 요구사항 | 컴포넌트 |
|---|---|
""",
    "api": """---
doc: api
title: API 명세서
standard: OpenAPI
id_prefix: [API]
refs: [FR, CMP, TBL]
inventory: 부록 A. 코드 인벤토리
---
## 1. 개요
## 2. API 상세
<!-- repeat: API -->
### {{API-ID}} {{메서드 경로}}

| 항목 | 내용 |
|---|---|

## 부록 A. 코드 인벤토리

| 대상 | 근거 | 문서 ID |
|---|---|---|
""",
    "erd": """---
doc: erd
title: ERD
standard: SI
id_prefix: [ENT]
refs: [FR]
inventory: 부록 A. 코드 인벤토리
---
## 1. 개요
## 2. 엔터티

| 엔터티ID | 이름 |
|---|---|

## 부록 A. 코드 인벤토리

| 대상 | 근거 | 문서 ID |
|---|---|---|
""",
    "table": """---
doc: table
title: 테이블 명세서
standard: SI
id_prefix: [TBL]
refs: [FR, ENT]
inventory: 부록 A. 코드 인벤토리
---
## 1. 개요
## 2. 테이블 상세
<!-- repeat: TBL -->
### {{TBL-ID}} {{물리명}}

| 컬럼명 | 타입 | FK |
|---|---|---|

## 부록 A. 코드 인벤토리

| 대상 | 근거 | 문서 ID |
|---|---|---|
""",
}


def _front(name: str, title: str, related: str = "[srs.readme]") -> str:
    return (
        f"---\nwiki_id: deliverables.{name}\ntitle: {title}\ntags: [deliverable, {name}]\n"
        f"related: {related}\nsources: {{}}\n"
        "revisions:\n  - {version: '1.0', date: 2026-09-21, summary: first}\n---\n"
    )


DOCS_MD = {
    "architecture": _front("architecture", "아키텍처 설계서")
    + """## 1. 개요
## 2. 컴포넌트
### <a id="cmp-001"></a>CMP-001 billing

| 항목 | 내용 |
|---|---|
| 책임 | [FR-PAY-001](../srs/pay.md#fr-pay-001), [NFR-PERF-001](../srs/README.md#nfr-perf-001) |

## 3. 추적표

| 요구사항 | 컴포넌트 |
|---|---|
| FR-PAY-001 | [CMP-001](#cmp-001) |
""",
    "api": _front("api", "API 명세서")
    + """## 1. 개요
## 2. API 상세
### <a id="api-001"></a>API-001 POST /pay

| 항목 | 내용 |
|---|---|
| 컴포넌트 | [CMP-001](architecture.md#cmp-001) |
| 요구사항 | FR-PAY-001 |

## 부록 A. 코드 인벤토리

```bash
grep -rn "@app.post" src
```

| 대상 | 근거 | 문서 ID |
|---|---|---|
| POST /pay | src/app.py | API-001 |
""",
    "erd": _front("erd", "ERD")
    + """## 1. 개요
## 2. 엔터티

| 엔터티ID | 이름 |
|---|---|
| <a id="ent-001"></a>ENT-001 | payment (FR-PAY-001) |

## 부록 A. 코드 인벤토리

```bash
grep -rn "class .*Model" src
```

| 대상 | 근거 | 문서 ID |
|---|---|---|
| Payment | src/models.py | ENT-001 |
""",
    "table": _front("table", "테이블 명세서")
    + """## 1. 개요
## 2. 테이블 상세
### <a id="tbl-001"></a>TBL-001 payment (ENT-001)

| 컬럼명 | 타입 | FK |
|---|---|---|
| id | int | - |

## 부록 A. 코드 인벤토리

```bash
grep -rn "CREATE TABLE" migrations
```

| 대상 | 근거 | 문서 ID |
|---|---|---|
| payment | src/models.py | TBL-001 |
""",
}


def make_host(root: Path) -> Path:
    write(root, "docs/srs/README.md", SRS_README)
    write(root, "docs/srs/pay.md", SRS_PAY)
    write(root, "docs/sds/README.md", SDS)
    write(root, "src/app.py", "app = 1\n")
    write(root, "src/models.py", "class Payment: ...\n")
    for name, text in TEMPLATES.items():
        write(root, f"{TDIR}/{name}.template.md", text)
    for name, text in DOCS_MD.items():
        write(root, f"docs/deliverables/{name}.md", text)
    return root
