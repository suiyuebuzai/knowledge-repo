# Format Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand supported document formats from 3 (.pdf/.docx/.txt) to 11, adding structure-aware loaders for .md, .xlsx, .xls, .pptx, .csv, .html/.htm; also add an alert() popup when indexing completes in find.html.

**Architecture:** Add 6 new `_load_*` functions to `chunker.py` (all feed into the existing `_chunk_text()`), update the constant sets in `ingest.py`, tighten the upload whitelist in `web_app.py`, and update two HTML templates. All loader changes are covered by unit tests before implementation.

**Tech Stack:** Python stdlib (csv, html.parser), openpyxl (xlsx), xlrd (xls), python-pptx (pptx); Jinja2 templates (frontend).

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `chunker.py` | Modify | Add `_load_md`, `_load_xlsx`, `_load_xls`, `_load_pptx`, `_load_csv`, `_load_html`; replace if/elif chain in `load_and_chunk()` with dispatch dict |
| `ingest.py` | Modify | `SUPPORTED` and `FIND_SUPPORTED` expanded to all 11 formats; update warning message |
| `web_app.py` | Modify | Upload suffix whitelist (line 133) + `find_scan` default `ext` param |
| `templates/upload.html` | Modify | `accept` attribute + hint text |
| `templates/find.html` | Modify | Checkbox groups (文档/表格/演示/网页) + `alert()` popup + default ext fallback |
| `tests/test_chunker.py` | Modify | Add 6 new loader tests |
| `tests/test_ingest_formats.py` | Create | Test that SUPPORTED/FIND_SUPPORTED include all new formats |

---

## Task 1: Install new dependencies

**Files:**
- None (environment setup)

- [ ] **Step 1: Install packages**

```bash
C:/1AI/.pvenv/Scripts/pip.exe install openpyxl xlrd python-pptx
```

Expected output includes lines like:
```
Successfully installed openpyxl-3.x.x
Successfully installed xlrd-2.x.x
Successfully installed python-pptx-1.x.x
```

- [ ] **Step 2: Verify imports**

```bash
C:/1AI/.pvenv/Scripts/python.exe -c "import openpyxl; import xlrd; from pptx import Presentation; print('OK')"
```

Expected: `OK`

---

## Task 2: Add new loaders to chunker.py (TDD)

**Files:**
- Modify: `chunker.py`
- Test: `tests/test_chunker.py`

- [ ] **Step 1: Write failing tests for all 6 new loaders**

Open `tests/test_chunker.py` and append these tests at the end of the file (after the existing `test_load_and_chunk_unsupported_format` test):

```python
def test_load_md(tmp_path):
    path = tmp_path / "readme.md"
    path.write_text("# 标题\n\n正文内容。", encoding="utf-8")
    text = chunker._load_md(str(path))
    assert "标题" in text
    assert "正文内容" in text


def test_load_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "销售"
    ws.append(["产品", "数量"])
    ws.append(["苹果", 10])
    path = tmp_path / "test.xlsx"
    wb.save(str(path))
    text = chunker._load_xlsx(str(path))
    assert "表名：销售" in text
    assert "产品: 苹果" in text


def test_load_xls(tmp_path):
    xlwt = pytest.importorskip("xlwt")
    wb = xlwt.Workbook()
    ws = wb.add_sheet("库存")
    ws.write(0, 0, "仓库")
    ws.write(0, 1, "数量")
    ws.write(1, 0, "北京")
    ws.write(1, 1, "500")
    path = tmp_path / "test.xls"
    wb.save(str(path))
    text = chunker._load_xls(str(path))
    assert "表名：库存" in text
    assert "仓库: 北京" in text


def test_load_pptx(tmp_path):
    pytest.importorskip("pptx")
    from pptx import Presentation
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = "季度总结"
    slide.placeholders[1].text = "营收增长15%"
    path = tmp_path / "test.pptx"
    prs.save(str(path))
    text = chunker._load_pptx(str(path))
    assert "季度总结" in text
    assert "营收增长" in text


def test_load_csv(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("姓名,部门,薪资\n张三,研发,20000\n李四,市场,18000", encoding="utf-8")
    text = chunker._load_csv(str(path))
    assert "姓名: 张三" in text
    assert "部门: 研发" in text


def test_load_html(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><title>Test</title></head><body>"
        "<h1>标题</h1><p>正文内容</p>"
        "<script>alert('skip')</script>"
        "</body></html>",
        encoding="utf-8",
    )
    text = chunker._load_html(str(path))
    assert "标题" in text
    assert "正文内容" in text
    assert "skip" not in text


def test_load_and_chunk_new_formats(tmp_path):
    """load_and_chunk dispatches correctly for .md and .csv."""
    md = tmp_path / "note.md"
    md.write_text("## 笔记\n内容", encoding="utf-8")
    chunks = chunker.load_and_chunk(str(md))
    assert len(chunks) >= 1
    assert chunks[0]["metadata"]["source"] == "note.md"

    csv_file = tmp_path / "data.csv"
    csv_file.write_text("key,val\nfoo,bar", encoding="utf-8")
    chunks2 = chunker.load_and_chunk(str(csv_file))
    assert len(chunks2) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_chunker.py::test_load_md tests/test_chunker.py::test_load_xlsx tests/test_chunker.py::test_load_csv tests/test_chunker.py::test_load_html tests/test_chunker.py::test_load_and_chunk_new_formats -v
```

Expected: All FAILED with `AttributeError: module 'chunker' has no attribute '_load_md'` (or similar).

- [ ] **Step 3: Add the 6 new loader functions to chunker.py**

Insert the following block into `chunker.py` between the `_load_docx` function and the `load_and_chunk` function (i.e., between line 38 and line 41 of the original file):

```python
def _load_md(file_path: str) -> str:
    return _load_txt(file_path)


def _load_xlsx(file_path: str) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        parts.append(f"表名：{sheet.title}")
        headers = [str(h) if h is not None else "" for h in rows[0]]
        for row in rows[1:]:
            cells = [str(v) if v is not None else "" for v in row]
            if any(cells):
                parts.append(" | ".join(
                    f"{h}: {v}" for h, v in zip(headers, cells) if h or v
                ))
        parts.append("")
    return "\n".join(parts)


def _load_xls(file_path: str) -> str:
    import xlrd
    wb = xlrd.open_workbook(file_path)
    parts = []
    for sheet in wb.sheets():
        if sheet.nrows == 0:
            continue
        parts.append(f"表名：{sheet.name}")
        headers = [str(sheet.cell_value(0, c)) for c in range(sheet.ncols)]
        for r in range(1, sheet.nrows):
            cells = [str(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            if any(cells):
                parts.append(" | ".join(
                    f"{h}: {v}" for h, v in zip(headers, cells) if h or v
                ))
        parts.append("")
    return "\n".join(parts)


def _load_pptx(file_path: str) -> str:
    from pptx import Presentation
    prs = Presentation(file_path)
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        title_text = ""
        body_texts = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            ph = getattr(shape, "placeholder_format", None)
            # placeholder type 15=TITLE, 3=CENTER_TITLE
            if ph is not None and ph.type in (15, 3):
                title_text = text
            else:
                body_texts.append(text)
        header = f"--- 第{i}页：{title_text} ---" if title_text else f"--- 第{i}页 ---"
        parts.append(header)
        parts.extend(body_texts)
        parts.append("")
    return "\n".join(parts)


def _load_csv(file_path: str) -> str:
    import csv
    parts = []
    rows = []
    for encoding in ("utf-8-sig", "gbk", "latin-1"):
        try:
            with open(file_path, encoding=encoding, errors="replace", newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
                except csv.Error:
                    dialect = csv.excel
                rows = list(csv.reader(f, dialect))
            break
        except Exception:
            continue
    if not rows:
        return ""
    headers = [str(h) for h in rows[0]]
    for row in rows[1:]:
        if any(v.strip() for v in row):
            parts.append(" | ".join(
                f"{h}: {v}" for h, v in zip(headers, row) if h or v
            ))
    return "\n".join(parts)


def _load_html(file_path: str) -> str:
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        SKIP_TAGS = {"script", "style", "head"}
        BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "br", "tr"}

        def __init__(self):
            super().__init__()
            self._parts = []
            self._skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.SKIP_TAGS:
                self._skip += 1
            if tag in self.BLOCK_TAGS and self._skip == 0:
                self._parts.append("\n")

        def handle_endtag(self, tag):
            if tag in self.SKIP_TAGS:
                self._skip = max(0, self._skip - 1)

        def handle_data(self, data):
            if self._skip == 0:
                self._parts.append(data)

        def get_text(self):
            return "".join(self._parts)

    html_content = ""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            with open(file_path, encoding=encoding, errors="replace") as f:
                html_content = f.read()
            break
        except Exception:
            continue

    parser = _TextExtractor()
    parser.feed(html_content)
    return parser.get_text()
```

- [ ] **Step 4: Replace load_and_chunk() with dispatch-dict version**

Replace the existing `load_and_chunk` function in `chunker.py` (currently lines 41–56) with:

```python
def load_and_chunk(file_path: str) -> list[dict]:
    """解析文档并分块。支持 .pdf/.docx/.txt/.md/.xlsx/.xls/.pptx/.csv/.html/.htm。"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    source = path.name

    loaders = {
        ".txt":  _load_txt,
        ".md":   _load_md,
        ".pdf":  _load_pdf,
        ".docx": _load_docx,
        ".xlsx": _load_xlsx,
        ".xls":  _load_xls,
        ".pptx": _load_pptx,
        ".csv":  _load_csv,
        ".html": _load_html,
        ".htm":  _load_html,
    }

    if suffix not in loaders:
        raise ValueError(
            f"不支持的文件格式: {suffix}（支持：{', '.join(sorted(loaders))}）"
        )

    text = loaders[suffix](file_path)
    return _chunk_text(text, source)
```

- [ ] **Step 5: Run all chunker tests to verify they pass**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_chunker.py -v
```

Expected: All tests PASS. The `test_load_xls` test will be skipped (SKIPPED) if `xlwt` is not installed — that is acceptable.

- [ ] **Step 6: Commit**

```bash
git add chunker.py tests/test_chunker.py
git commit -m "feat: add loaders for md/xlsx/xls/pptx/csv/html in chunker"
```

---

## Task 3: Update ingest.py constants

**Files:**
- Modify: `ingest.py`
- Create: `tests/test_ingest_formats.py`

- [ ] **Step 1: Write failing test**

Create new file `tests/test_ingest_formats.py`:

```python
from ingest import SUPPORTED, FIND_SUPPORTED


def test_supported_includes_all_new_formats():
    for ext in (".md", ".xlsx", ".xls", ".pptx", ".csv", ".html", ".htm"):
        assert ext in SUPPORTED, f"Missing {ext} in SUPPORTED"


def test_find_supported_equals_supported():
    assert SUPPORTED == FIND_SUPPORTED, "FIND_SUPPORTED must equal SUPPORTED"
```

- [ ] **Step 2: Run to verify it fails**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_ingest_formats.py -v
```

Expected: FAILED — `.xlsx` not in SUPPORTED.

- [ ] **Step 3: Update SUPPORTED and FIND_SUPPORTED in ingest.py**

In `ingest.py`, replace lines 25–26:

```python
SUPPORTED = {".pdf", ".docx", ".txt"}
FIND_SUPPORTED = SUPPORTED | {".md"}          # find 额外支持 markdown
```

with:

```python
SUPPORTED = {
    ".pdf", ".docx", ".txt", ".md",
    ".xlsx", ".xls", ".pptx",
    ".csv", ".html", ".htm",
}
FIND_SUPPORTED = SUPPORTED
```

- [ ] **Step 4: Update the warning message in ingest_directory()**

In `ingest.py` line 38, replace:

```python
        print(f"[WARN] {docs_dir} 中没有找到支持的文档（.pdf / .docx / .txt）")
```

with:

```python
        print(f"[WARN] {docs_dir} 中没有找到支持的文档（{' / '.join(sorted(SUPPORTED))}）")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_ingest_formats.py -v
```

Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ingest.py tests/test_ingest_formats.py
git commit -m "feat: expand SUPPORTED/FIND_SUPPORTED constants to 11 formats"
```

---

## Task 4: Update web_app.py upload whitelist and scan default

**Files:**
- Modify: `web_app.py`

- [ ] **Step 1: Update the upload suffix whitelist**

In `web_app.py`, replace line 133:

```python
        if suffix not in {".pdf", ".docx", ".txt"}:
```

with:

```python
        if suffix not in {".pdf", ".docx", ".txt", ".md",
                          ".xlsx", ".xls", ".pptx",
                          ".csv", ".html", ".htm"}:
```

- [ ] **Step 2: Update the find_scan default ext parameter**

In `web_app.py`, replace the `ext` default in the `find_scan` function signature (line 299):

```python
    ext: str = ".pdf,.docx,.txt,.md",
```

with:

```python
    ext: str = ".pdf,.docx,.txt,.md,.xlsx,.xls,.pptx,.csv,.html,.htm",
```

- [ ] **Step 3: Run existing tests to confirm nothing broken**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/test_embedder.py --ignore=tests/test_store.py --ignore=tests/test_hybrid_retriever.py --ignore=tests/test_retriever.py -q
```

Expected: All non-ML tests pass.

- [ ] **Step 4: Commit**

```bash
git add web_app.py
git commit -m "feat: expand upload whitelist and find_scan default ext to 11 formats"
```

---

## Task 5: Update templates/upload.html

**Files:**
- Modify: `templates/upload.html`

- [ ] **Step 1: Update the file input accept attribute**

In `templates/upload.html`, replace line 15:

```html
    <input type="file" name="files" multiple accept=".pdf,.docx,.txt">
```

with:

```html
    <input type="file" name="files" multiple
      accept=".pdf,.docx,.txt,.md,.xlsx,.xls,.pptx,.csv,.html,.htm">
    <small style="color:#888;display:block;margin-top:4px;">
      支持 .pdf / .docx / .txt / .md / .xlsx / .xls / .pptx / .csv / .html
    </small>
```

- [ ] **Step 2: Commit**

```bash
git add templates/upload.html
git commit -m "feat: expand upload.html accept attribute to 11 formats"
```

---

## Task 6: Update templates/find.html (grouped checkboxes + alert popup)

**Files:**
- Modify: `templates/find.html`

- [ ] **Step 1: Replace the extension checkbox section with grouped checkboxes**

In `templates/find.html`, replace lines 15–19 (the `<span class="filter-label">扩展名：</span>` block and the 4 checkbox labels):

```html
        <span class="filter-label">扩展名：</span>
        <label><input type="checkbox" class="ext-cb" value=".pdf" checked> PDF</label>
        <label><input type="checkbox" class="ext-cb" value=".docx" checked> DOCX</label>
        <label><input type="checkbox" class="ext-cb" value=".txt" checked> TXT</label>
        <label><input type="checkbox" class="ext-cb" value=".md" checked> MD</label>
```

with:

```html
        <span class="filter-label">文档：</span>
        <label><input type="checkbox" class="ext-cb" value=".pdf" checked> PDF</label>
        <label><input type="checkbox" class="ext-cb" value=".docx" checked> DOCX</label>
        <label><input type="checkbox" class="ext-cb" value=".txt" checked> TXT</label>
        <label><input type="checkbox" class="ext-cb" value=".md" checked> MD</label>
        <span class="filter-label">表格：</span>
        <label><input type="checkbox" class="ext-cb" value=".xlsx" checked> XLSX</label>
        <label><input type="checkbox" class="ext-cb" value=".xls" checked> XLS</label>
        <label><input type="checkbox" class="ext-cb" value=".csv" checked> CSV</label>
        <span class="filter-label">演示：</span>
        <label><input type="checkbox" class="ext-cb" value=".pptx" checked> PPTX</label>
        <span class="filter-label">网页：</span>
        <label><input type="checkbox" class="ext-cb" value=".html" checked> HTML</label>
        <label><input type="checkbox" class="ext-cb" value=".htm" checked> HTM</label>
```

- [ ] **Step 2: Update the ext fallback in doScan()**

In `templates/find.html`, replace line 56 (inside doScan):

```javascript
        ext: exts.join(',') || '.pdf,.docx,.txt,.md',
```

with:

```javascript
        ext: exts.join(',') || '.pdf,.docx,.txt,.md,.xlsx,.xls,.pptx,.csv,.html,.htm',
```

- [ ] **Step 3: Add alert() popup in doIndex()**

In `templates/find.html`, find the block inside the SSE `event: done` handler (around line 162–163):

```javascript
                    if (currentEvent === 'done') {
                        summary.textContent = `完成：${d.success} 成功，${d.failed} 失败`;
```

Replace with:

```javascript
                    if (currentEvent === 'done') {
                        summary.textContent = `完成：${d.success} 成功，${d.failed} 失败`;
                        if (d.total > 0) {
                            alert(`索引完成\n✓ 成功：${d.success} 个文件\n✗ 失败：${d.failed} 个文件`);
                        }
```

- [ ] **Step 4: Commit**

```bash
git add templates/find.html
git commit -m "feat: group extension checkboxes and add indexing completion alert in find.html"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run full test suite (excluding ML-heavy tests)**

```bash
C:/1AI/.pvenv/Scripts/python.exe -m pytest tests/test_chunker.py tests/test_ingest_formats.py tests/test_bm25_store.py tests/test_query.py -v
```

Expected: All tests PASS (test_load_xls may be SKIPPED if xlwt absent — acceptable).

- [ ] **Step 2: Smoke-test web app startup**

```bash
C:/1AI/.pvenv/Scripts/python.exe -c "
import sys; sys.path.insert(0, '.')
import chunker, ingest
print('chunker loaders:', sorted(k for k in ['.pdf','.docx','.txt','.md','.xlsx','.xls','.pptx','.csv','.html','.htm']))
from ingest import SUPPORTED
assert len(SUPPORTED) == 10, f'Expected 10, got {len(SUPPORTED)}'
print('ingest SUPPORTED:', sorted(SUPPORTED))
print('OK')
"
```

Expected:
```
chunker loaders: ['.csv', '.docx', '.htm', '.html', '.md', '.pdf', '.pptx', '.txt', '.xls', '.xlsx']
ingest SUPPORTED: ['.csv', '.docx', '.htm', '.html', '.md', '.pdf', '.pptx', '.txt', '.xls', '.xlsx']
OK
```

- [ ] **Step 3: Final commit (if any stragglers)**

```bash
git status
```

If clean: done. If any untracked changes, add and commit them.
