<p align="center">
  <h1 align="center">📄 PayCheck</h1>
  <p align="center"><strong>中国银行 PDF 对账单 → CSV 转换工具 + 本地账单工作台</strong></p>
  <p align="center">PDF 渲染 → OCR → 结构化 CSV；三源账单 SQLite 导入 → HTML 展示、收支属性与标签管理（Python 标准库 HTTP 服务，无 Web 框架）</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/version-1.1.0-blueviolet" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/GPU-CUDA%2012.6-orange?logo=nvidia" alt="CUDA">
</p>

---

## 简介

本项目包含两个工具：

- **boc-pdf2csv**：中国银行（BOC）PDF 对账单 → 标准 CSV 的命令行转换工具。
- **paycheck**（别名 paycheck-workbench）：本地账单工作台（标准库 HTTP 服务）：BOC / 支付宝 / 微信三源原始账单导入 SQLite 后 HTML 展示，收支属性与标签统一在「总账户」视图管理（见「账单工作台」）。

整体工作流：**原始账单导入（数据源视图，只读）→ 总账户做收支与标签管理（三源合并视图）**。

boc-pdf2csv 处理管线：

```
PDF → 高清图片 (PyMuPDF) → OCR 识别 (PaddleOCR) → 版面解析 → 交易去重排序 → CSV
```

- 文件夹内每个 PDF 输出同名 CSV，同名 CSV 已存在则自动跳过
- 自动剔除重复交易（按 日期 + 金额 + 对方账户名）
- 自动按日期 + 时间排序
- 输出 UTF-8 BOM 编码的 13 列标准 CSV
- 默认强制使用 GPU（CUDA）推理，无 GPU 时可显式 `--device cpu`
- 无任何前后端框架依赖，纯命令行使用

## 安装

```bash
# 使用 uv（推荐，自动从 Paddle 官方源安装 CPU 版；含工作台 paycheck 全部依赖）
uv sync

# 安装 GPU 加速版（可选，CUDA 12.6）
uv sync --extra gpu
```

> 也可用 pip 安装：`pip install -e .`（CPU 版需自行指定 paddlepaddle 源）。

GPU 版 paddle 不内置 CUDA 运行库，Windows 上还需安装 NVIDIA 的 pip 包提供
cudart / cublas / cudnn DLL（程序会自动把它们加入 DLL 搜索路径）：

```bash
uv pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## 使用

```bash
# 基本用法：文件夹内每个 PDF → 同名 CSV（已存在则跳过）
uv run boc-pdf2csv ./statements/

# 强制重新导出：同名 CSV 已存在时覆盖而不是跳过
uv run boc-pdf2csv ./statements/ --force

# 调整渲染精度（低配机器可用 2.0）
uv run boc-pdf2csv ./statements/ --scale 2.0

# 延长超时（大批量文件）
uv run boc-pdf2csv ./statements/ --timeout 120

# 无 GPU 机器使用 CPU 推理（默认强制 GPU）
uv run boc-pdf2csv ./statements/ --device cpu

# 查看版本 / 帮助
uv run boc-pdf2csv --version
uv run boc-pdf2csv --help

# 详细日志
uv run boc-pdf2csv ./statements/ --verbose

# 通过 Python 模块调用
uv run python -m boc_pdf2csv ./statements/
```

> 以上示例基于推荐的 uv 安装方式；`pip install -e .` 安装后可直接运行 `boc-pdf2csv`（不带 `uv run` 前缀）。

`2025-01.pdf` 转换后得到同目录下的 `2025-01.csv`；若该 CSV 已存在则默认跳过此 PDF，删除对应 CSV 或加 `--force` 可重新转换（`--force` 会覆盖已有 CSV）。

默认强制使用 GPU 推理；未检测到 GPU 时直接报错（不会静默回退 CPU），无 GPU 的机器需显式加 `--device cpu`。

### 作为 Python API 使用

```python
from boc_pdf2csv import process_folder, process_pdf

# 批量处理文件夹：每个 PDF → 同名 CSV（已存在则跳过），返回汇总
result = process_folder("./statements/")
result.processed  # {PDF 路径: CSV 路径}
result.skipped    # 跳过的 PDF（同名 CSV 已存在）
result.failed     # 处理失败的 PDF

# 处理单个 PDF
csv_content = process_pdf("./statements/2025-01.pdf", output_path="2025-01.csv")

# 推理设备默认强制 GPU（device='gpu'），无 GPU 时显式指定 CPU
csv_content = process_pdf("./statements/2025-01.pdf", device="cpu")

# 文件夹批量处理默认跳过已有同名 CSV，force=True 时覆盖重新导出
result = process_folder("./statements/", force=True)
```

## CSV 输出格式

输出为 UTF-8 BOM 编码的 13 列标准 CSV：

| 列名 | 说明 |
|------|------|
| date | 记账日期 |
| time | 记账时间 |
| tx_type | 交易类型（支出/收入） |
| amount | 金额（正数） |
| counterparty | 对方账户名 |
| channel | 交易渠道 |
| balance | 余额 |
| memo | 附言 |
| tx_name | 交易名称 |
| currency | 币别 |
| branch | 网点名称 |
| cp_account | 对方卡号/账号 |
| cp_bank | 对方开户行 |

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 输入路径不存在或非目录 |
| 2 | 未找到 PDF 文件 |
| 3 | 处理失败（全部 PDF 处理出错） |
| 4 | 未提取到任何交易记录 |

## 项目结构

```
src/
├── boc_pdf2csv/           # PDF → CSV 转换工具
│   ├── cli.py             # 命令行入口 (argparse)
│   ├── pdf_render.py      # PDF → 高清图片
│   ├── ocr_engine.py      # PaddleOCR 识别引擎
│   ├── layout.py          # OCR 版面解析 → 交易行
│   ├── pipeline.py        # 管线编排：单 PDF / 批量文件夹
│   ├── csv_writer.py      # 交易 → 13 列 CSV
│   ├── __main__.py        # python -m 入口
│   └── __init__.py        # 公开 API
└── paycheck_workbench/    # 账单工作台
    ├── cli.py             # 命令行入口 (argparse)
    ├── db.py              # SQLite 存储层：明细表 / 导入 / 筛选 / 覆盖 / 标签
    ├── server.py          # 标准库 HTTP 服务 + JSON API
    ├── sources.py         # 三源列定义、逻辑列与去重键
    ├── total.py           # 总账户统一映射 / 有效属性 / 标签 / 分页
    ├── parsing/           # BOC / 支付宝 / 微信解析器（表头定位）
    ├── static/            # 单页前端 index.html
    ├── __main__.py        # python -m 入口
    └── __init__.py
tests/                     # pytest：解析层 / 存储层 / HTTP 服务 / 总账户 / 标签
```

## 依赖

| 依赖 | 用途 |
|------|------|
| PaddleOCR + paddlepaddle + torch | OCR 识别引擎（合计约 2GB） |
| PyMuPDF | PDF 渲染为高清图片 |
| opencv-python + Pillow + numpy | 图像处理 |
| tqdm | 进度条 |
| openpyxl | 微信账单 XLSX 解析（工作台） |

## 许可证

[MIT](LICENSE)


---

## 账单工作台（paycheck）

本地 Web 工具：BOC / 支付宝 / 微信三源账单的 HTML 展示 + SQLite 导入（Python 标准库 HTTP 服务，无 Web 框架）。

```bash
# 启动并自动打开浏览器（默认库文件 paycheck.db，相对启动目录；端口 8765，仅绑定本机）
uv run paycheck --open
# 自定义库文件与端口
uv run paycheck --db ./my.db --port 8765
# 自定义 BOC PDF 转换目录（默认 <库文件目录>/boc_csv）
uv run paycheck --convert-dir ./boc_csv
# 或通过模块运行
uv run python -m paycheck_workbench
```

> 同上：pip 安装后可直接运行 `paycheck`（不带 `uv run` 前缀）；旧入口 `paycheck-workbench` 保留为别名，仍可使用。

功能：

- 左侧导航栏：总账户为一级主视图、默认首页（打开应用即进入），数据源 BOC/支付宝/微信为二级分组视图（各带笔数徽标），任一视图点导航项直达；「数据源」分组下方为筛选区块（字段纵向排列，标题行可折叠，折叠且存在激活筛选时显示激活筛选数徽标）；主区顶部有视图标题行说明当前视图职责（总账户：三源合并视图，在这里标记收支与标签；数据源：原始账单，导入与查看）
- 三数据源视图（BOC CSV / 支付宝 GBK CSV / 微信 XLSX，兼容 CSV 变体）：原始账单只读（职责=导入与查看），自动跳过文件信息头定位表头；「导入账单」入口仅数据源视图可见，总账户空态（三源皆空）引导「去数据源导入」
- 解析预览（列样例、日期范围、收/支分布）+ 去重比对（新增/重复跳过）→ 确认后写入 SQLite，重复导入幂等
- 导入入口支持一次选择多个文件（多选/拖拽，按当前视图限定类型）：逐文件统计 + 合并去重比对，确认后逐文件写入并显示进度与结果，类型不符的文件明确提示且不写入
- BOC 页 PDF 转换（顶栏「转换 PDF」/ BOC 空态次按钮）：选 PDF（多选/文件夹）→ 后台转换（进度轮询、可收起后台继续）→ 结果视图 → 一键导入（复用导入预览与去重比对）；转换出的 CSV 与 PDF 同名存入转换目录，不导入也可直接取用
- 明细表格：排序、分页、行展开详情、列显隐；汇总卡片随筛选联动（收入/支出/不计收支/期末余额或笔数）
- 筛选区块（左侧导航栏「数据源」分组下方，标题行可折叠）：日期快捷档位、收/支多选、分类多选（总账户视图为来源多选）、属性与标签（仅总账户）、金额区间、重置筛选；筛选状态按视图记忆；关键词搜索在主区工具栏（300ms 防抖）
- 三张表 `boc_transactions` / `alipay_transactions` / `wechat_transactions`：源明细列全量入库 + `source_file` / `imported_at` / `dedup_key`（UNIQUE）
- 「总账户」主视图（品牌色 #7C4DFF）：三源映射为统一字段的一张全部账单表（收支混排、时间倒序、标准分页，与数据源视图同一套组件），无任何自动识别/自动标注；顶部汇总卡片为计入口径：收入合计 / 支出合计 / 净收支 / 计入笔数（副文本显示「不计入 N 笔」）
- 收支属性（手动管理）：方向约束铁律——方向=收入的行只能是收入或不计，方向=支出的行只能是支出或不计，永不反向；不计收支/中性行默认不计、可改为计入（计入方向按金额符号定：正=收入、负=支出）。有效属性 = 覆盖 > 原始方向；「不计」行整行置灰，属性列点击即切换计入↔不计。属性标记仅作用于总账户视图（写入旁表），不改动数据源原始账单，数据源视图始终展示原始收/支
- 批量操作：勾选 ≥1 行出现批量操作栏（设为计入 / 设为不计 / 打标签… / 清除选择）；筛选结果多于当前页时提供「选择全部筛选结果」全量模式，操作作用于整个筛选结果
- 标签组：自建标签（名称唯一、自动 8 色循环），标签管理弹窗支持创建/改名/删除（删除仅解除关联，不影响账单）；行标签多对多、重复打幂等，标签列 chips 带组颜色（chip × 可移除单行标签）；筛选区块「标签」多选筛选（命中任一勾选标签即显示，无标签行仅全部未勾选时显示）
- 旁表存储（三源明细表不加列）：`total_overrides`（source + row_id 联合主键、counted、updated_at，稀疏，只存用户动过的行）、`tag_groups`（名称唯一 + 8 色循环）、`row_tags`（行 ↔ 标签组多对多）；覆盖/标签/属性互相独立，导入流程零改动（覆盖挂在行 id 上，重复导入不丢）
- 总账户 API：`PUT /api/total/overrides`（批量设属性，ids / filter 两种 scope）、`GET/POST /api/tags`、`PUT/DELETE /api/tags/{id}`、`PUT /api/tags/apply`（批量打/移除标签）；`/api/rows`、`/api/summary` 的 total 分支为标准 `page` 分页与计入口径结构

## 开发

```bash
uv sync          # 安装全部依赖
uv run pytest    # 运行测试（解析层/存储层/HTTP 服务/总账户/标签）
```
