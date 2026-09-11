# 发布版本离线验收

验收日期：2026-09-10（PDT）。环境：macOS arm64，CPython 3.12.11，仓库独立 `.venv`。
基线脚本：`e1ca5de`。目标来自家族文档 §6.15 第 3 项。

## 依赖与来源

固定 pdfspine 0.8.0、corespine 0.5.1、spineagent 0.3.1、rag-spine 0.13.0；
全部 21 个安装包见 `../requirements.txt`。首次 `uv pip install --offline` 因缓存缺少
pdfspine 0.8.0 失败，随后从 `https://pypi.org/simple` 使用 `--only-binary :all:` 安装。
无源码构建、editable 安装或兄弟仓扩展复用。四包实际导入位置均在 examples 的 `.venv`
中，版本元数据与目标一致，没有 direct URL/editable 安装元数据。

`release-sources.json` 记录官方 PyPI 版本元数据中匹配本机的 wheel URL 与 SHA-256。
另从该 URL 下载四个 wheel，逐一计算 SHA-256 与官方元数据完全一致，并将 wheel 中
所有非 `.dist-info` 文件与本环境已安装文件逐字节比较：pdfspine 37、corespine 27、
spineagent 44、rag-spine 250 个文件全部一致，包括 pdfspine 原生扩展。
下载 wheel 与原始运行日志保存在外置 `examples-published-e2e` 证据目录，未放入 Git。
`offline-verification.txt` 保存通过后的完整输出（随机临时目录名已归一化）。

## 实际发现与修正

原脚本在四个目标发布包下运行到 stage 2 失败：
`FactStore(":memory:")` 抛出 `TypeError: Protocols cannot be instantiated`。
rag-spine 0.13.0 把接口抽为 `FactStore` Protocol，原 SQLite 实现名为
`SqliteFactStore`。本次仅调整示例实例化，类型标注继续使用接口。
旧机器绝对路径改为从 examples 仓库根目录运行的相对路径。

## 验收结果

- 原脚本在 stage 1 已抽出 266 字符；修正后仍逐字等于 `REPORT_LINES` 五行加末尾换行，
  行序为标题、收入、地域、利润率、员工数。
- 数值问答走 structured，收入 `1320 USD_M`，引用 `acme_fy2024.pdf / page=1,line=2`。
- 叙事问答走 narrative，1 个 chunk，包含 `Greater China`，引用
  `acme_fy2024.pdf#para1-5`。
- FY2030 无事实时返回“查不到”，无引用，也未套用 FY2024 的 1320。
- scripted provider 两次调用完成工具循环，输出含检索地域及原引用。
- 计算结果 `237.6`；两个 Coordinator agent 均成功，formatter 输出符合预期。
- 共享 trace 共 10 个事件，代码序列已断言；含 `answer` 的隐私载荷抛 `TraceError`，
  拒绝前后事件数均为 10。Registry mock 探针成功。
- 禁止 Python socket 连接、发送和 DNS 的执行通过，输出
  `SPINE FAMILY E2E OK` 和 `OFFLINE RELEASE VERIFICATION OK`。
- 安装后用完整 `requirements.txt` 执行 `uv pip sync --offline --only-binary :all:`
  通过，`uv pip check` 确认 21 个包依赖兼容；Ruff 0.9.4 的格式检查及
  `E4,E7,E9,F` 静态检查通过，`git diff --check` 通过。

这些结果在示例内有失败即退出的语义检查，验证器另检查版本与来源。

## 范围局限

原旧 editable 环境已不存在，没有冒充重跑历史版本或报告历史输出 diff。
抽取对比基准是本示例预定的五行文本和同次发布包下修正前的 stage 1 输出。
本例是单页单栏，并不覆盖 0.8.0 的复杂多栏 XY-cut 或全部 RAG/agent 能力。
mock 叙事回答包含检索上下文回显，不代表真实模型质量。
socket 审计只约束 Python socket 操作；运行未调用远程模型，但不是系统级禁网证明。
本次不修改各引擎仓库、共享 family 文档副本或其状态。
