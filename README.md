# spine-examples

家族端到端离线示例 `spine_family_e2e.py`，串联 corespine → pdfspine → ragspine → spineagent。

## 安装与运行

在本仓库根目录执行，使用 Python 3.12 和 uv：

```sh
uv venv --python 3.12 .venv
uv pip sync --python .venv/bin/python --index-url https://pypi.org/simple --only-binary :all: requirements.txt
.venv/bin/python verify_offline.py
```

`requirements.txt` 固定本次验收的全部依赖，包括 pdfspine 0.8.0、corespine
0.5.1、spineagent 0.3.1、rag-spine 0.13.0。安装阶段需要访问 PyPI，或在缓存完整时
给 `uv pip sync` 加 `--offline`。只装发布 wheel，不使用 editable 或兄弟仓工作树。
锁定列表在 macOS arm64 / Python 3.12 验证；其他平台需要对应 wheel。

运行阶段使用内存 SQLite、确定性 embedding、mock/scripted provider，不需要 API key
或远程模型。`verify_offline.py` 检查四个发布版本及环境来源，并阻止 Python socket
连接、发送和 DNS 查询；它不是针对原生库/子进程的系统级网络沙箱。需要完整网络隔离时，
可另在禁网环境运行同一命令。示例自身也可用 `.venv/bin/python spine_family_e2e.py` 运行。

脚本会核对 PDF 五行文本及顺序、数值/叙事回答和引用、缺失事实拒答、工具结果回流、
计算结果、编排结果、trace 顺序和隐私拒绝。临时 PDF 在退出时删除；可通过 `TMPDIR`
选择临时文件位置。验收记录与范围局限见
[发布版本验收报告](reports/published-family-e2e.md)。

## Spine 家族 / Spine family

本仓库是 Spine 家族的成员之一（角色：旁路：示例）。家族全部成员、分层、依赖方向、依赖形式与当前差距见 [`docs/spine-family.md`](docs/spine-family.md)；该文件在每个家族仓库中的副本内容相同，真源在家族根目录 `~/startup/spine/docs/spine-family.md`，用根目录 `make family-doc-sync` 同步。
