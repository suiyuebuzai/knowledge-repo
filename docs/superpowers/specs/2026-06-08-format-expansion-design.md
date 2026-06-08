# 文档格式扩展设计文档

**日期：** 2026-06-08  
**状态：** 已批准，待实现  
**定位：** 将知识库支持的文档格式从 3 种（.pdf/.docx/.txt）扩展至 11 种，覆盖 Excel、PowerPoint、CSV、HTML、Markdown 等常见办公文档类型；同时在索引完成后添加页面弹窗提示。

---

## 背景

当前 `chunker.py` 只支持 `.pdf`/`.docx`/`.txt`，`.md` 只能扫描不能索引。企业环境中大量文档为 Excel 表格、PPT 演示、CSV 数据文件和 HTML 网页，无法通过现有流程进入知识库。

---

## 改动范围

| 文件 | 改动 |
|------|------|
| `chunker.py` | 新增 6 个 loader 函数，更新 `load_and_chunk()` 分发逻辑 |
| `ingest.py` | 更新 `SUPPORTED` 和 `FIND_SUPPORTED` 两个常量 |
| `web_app.py` | 上传路由格式白名单同步扩展 |
| `templates/upload.html` | `accept` 属性和格式提示文字同步扩展 |
| `templates/find.html` | 扩展名 checkbox 按类型分组，新增新格式，`doIndex()` 末尾加弹窗 |

---

## 新增格式与依赖

| 格式 | 解析库 | 是否需要安装 |
|------|--------|------------|
| `.md` | 内置（复用 `_load_txt`） | 否 |
| `.xlsx` | `openpyxl` | `pip install openpyxl` |
| `.xls` | `xlrd` | `pip install xlrd` |
| `.pptx` | `python-pptx` | `pip install python-pptx` |
| `.csv` | 内置 `csv` | 否 |
| `.html` / `.htm` | 内置 `html.parser` | 否 |

安装后总支持格式：`.pdf` `.docx` `.txt` `.md` `.xlsx` `.xls` `.pptx` `.csv` `.html` `.htm`

---

## chunker.py 提取逻辑（结构感知方案）

所有新格式提取完文本后，交给现有 `_chunk_text()` 按 CHUNK_SIZE/OVERLAP 切分，不改变 chunk 的下游接口。

### `.md`
直接复用 `_load_txt()`：

```python
def _load_md(file_path: str) -> str:
    return _load_txt(file_path)
```

### `.xlsx` / `.xls`
每个 Sheet 单独提取，首行作为字段名前缀拼入每行：

```
表名：销售数据
产品名称: iPhone | 数量: 100 | 金额: 99000
产品名称: iPad   | 数量: 50  | 金额: 24500

表名：库存数据
仓库: 北京 | 数量: 500
```

实现：`openpyxl.load_workbook(read_only=True, data_only=True)` 遍历所有 Sheet，跳过空行，首行为 header，后续行拼 `"field: value | ..."` 格式。`.xls` 使用 `xlrd.open_workbook()` 相同逻辑。

### `.pptx`
每张幻灯片提取标题 + 所有文本框内容：

```
--- 第1页：季度总结 ---
本季度营收增长 15%，主要来自华南区域的...

--- 第2页：下一步计划 ---
1. 扩大渠道覆盖  2. 优化成本结构
```

实现：`python_pptx.Presentation()` 遍历 `slides`，每页取 `slide.shapes` 中 `has_text_frame` 的形状，标题形状优先拼在页头。

### `.csv`
首行作为字段名，逐行拼接 `"字段: 值 | ..."` 格式：

```
姓名: 张三 | 部门: 研发 | 薪资: 20000
姓名: 李四 | 部门: 市场 | 薪资: 18000
```

实现：`csv.reader()`，`errors='replace'` 处理编码问题，自动探测分隔符（`,` / `\t`）。

### `.html` / `.htm`
用内置 `html.parser` 剥离标签，保留块级元素换行结构，过滤 `<script>` 和 `<style>` 内容：

```python
class _TextExtractor(HTMLParser):
    # 收集文本，遇到 h1-h6/p/div/li/br 插入换行
    # skip_tags = {"script", "style", "head"}
```

---

## 格式常量更新

### ingest.py
```python
SUPPORTED = {
    ".pdf", ".docx", ".txt", ".md",
    ".xlsx", ".xls", ".pptx",
    ".csv", ".html", ".htm",
}
FIND_SUPPORTED = SUPPORTED  # 扫描与索引完全对齐
```

### web_app.py（上传路由白名单）
```python
UPLOAD_SUPPORTED = {
    ".pdf", ".docx", ".txt", ".md",
    ".xlsx", ".xls", ".pptx",
    ".csv", ".html", ".htm",
}
```

---

## 前端更新

### find.html — checkbox 分组
```
扩展名：
文档  ☑ PDF  ☑ DOCX  ☑ TXT  ☑ MD
表格  ☑ XLSX  ☑ XLS  ☑ CSV
演示  ☑ PPTX
网页  ☑ HTML
```

### find.html — 索引完成弹窗
在 `doIndex()` 收到 `event: done` 后，调用：
```javascript
alert(`索引完成\n✓ 成功：${d.success} 个文件\n✗ 失败：${d.failed} 个文件`);
```
仅在 `d.total > 0` 时弹出。弹窗在进度区域已显示详情后触发，不影响已有 UI。

### upload.html — accept 属性
```html
<input type="file" name="files" multiple
  accept=".pdf,.docx,.txt,.md,.xlsx,.xls,.pptx,.csv,.html,.htm">
```
格式提示文字改为"支持 .pdf / .docx / .txt / .md / .xlsx / .xls / .pptx / .csv / .html"。

---

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| xlrd 未安装但用户上传 .xls | `load_and_chunk` 抛 `ImportError`，上传页/索引进度显示错误信息 |
| openpyxl 未安装但用户上传 .xlsx | 同上 |
| python-pptx 未安装但用户上传 .pptx | 同上 |
| Excel/CSV 文件编码异常 | `errors='replace'` 容错，不中断整个文件解析 |
| HTML 文件提取后文本为空 | 正常生成 0 个 chunk，不报错 |

---

## 不做的事情

- 不支持 `.doc`（旧版 Word 二进制格式，需 LibreOffice/win32com，依赖重）
- 不支持 `.ppt`（旧版 PPT，同上）
- 不做 Excel 公式求值（`data_only=True` 只取缓存值）
- 不做 HTML 图片 alt 文字提取
