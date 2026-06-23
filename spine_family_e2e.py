"""Spine 家族端到端演示 —— 一条贯穿三个独立构建的包的隐私 trace 缝。

流水线:
    pdfspine(Rust+Python 扩展) -> ragspine(RAG) -> spineagent(agent)
全部由 **同一个** corespine 共享核串起来。

主角(本 demo 的核心信息):
    * 同一个 corespine `InProcessPrivacyTraceSink` 实例,贯穿三个包的每一个阶段;
    * 同一个 corespine `LLMProvider` 协议(ChatCompletion 形状),被 ragspine 的
      MockProvider、spineagent 的 scripted provider、corespine 自带 MockProvider 共同实现;
    * corespine 是「薄」共享核 —— 三个包互不知道对方,只共享 corespine 的词汇。

完全离线运行:无网络、无 API key、无重依赖。

如何运行(从 /Users/linhan/workspace/spine 目录):
    examples/.venv/bin/python examples/spine_family_e2e.py
"""

from __future__ import annotations

# --- stdlib ---
import shutil
import tempfile
from pathlib import Path

# --- third-party: Spine 家族四个独立包 ---
# corespine: 薄共享核(零依赖,仅标准库)
from corespine import InProcessPrivacyTraceSink, MockProvider, Registry, TraceError
from corespine.llm.provider import ChatCompletion, Choice, FunctionCall, ResponseMessage
from corespine.llm.provider import ToolCall as LlmToolCall

# pdfspine: Rust abi3 扩展,PyMuPDF 兼容的离线 PDF 库
import pdfspine

# ragspine: 离线 RAG —— 数值 FactStore + 叙事 ChunkStore
from ragspine.storage.fact_store import Fact, FactStore
from ragspine.agent.llm_provider import MockProvider as RagMockProvider  # 实现 corespine LLMProvider 缝
from ragspine.agent.agent import answer_question
from ragspine.retrieval.chunking.chunk_store import ChunkStore
from ragspine.retrieval.chunking.chunking import DocumentMeta
from ragspine.retrieval.lexical.retrieval import NarrativeIndex
from ragspine.retrieval.link.narrative_link import NarrativeIndexRetriever
from ragspine.retrieval.vector.embedding_backends import make_embedding_backend

# spineagent: 纯离线 agent 库(依赖 corespine)
from spineagent import (
    CalcTool,
    Coordinator,
    FunctionAgent,
    FunctionCallingAgent,
    LlmAgent,
    SyntaxToolPolicy,
    ToolUsingAgent,
    function_tool,
)


def banner(s: str) -> None:
    print("\n" + "=" * 70 + f"\n{s}\n" + "=" * 70)


# ONE 共享 sink —— 本 demo 的明星,贯穿三个包的每一个阶段。
sink = InProcessPrivacyTraceSink()

# 演示语料 PDF 的文本(STAGE 0 写出,STAGE 1 读回)。
REPORT_LINES: list[str] = [
    "ACME Corporation FY2024 Annual Report",
    "Total revenue for fiscal year 2024 was 1320 million USD.",
    "ACME primarily operates in the Greater China region.",
    "Net profit margin reached 18 percent in fiscal year 2024.",
    "The company employs over 5000 people across its operations.",
]


def stage0_author_pdf(pdf_path: Path) -> None:
    """STAGE 0 —— 用 pdfspine 现场写出一份自包含的演示语料 PDF。"""
    banner("STAGE 0 — pdfspine AUTHOR: 现场生成自包含演示语料 PDF")
    doc = pdfspine.open()  # 新建空 PDF
    page = doc.new_page()  # 默认 A4
    y = 72.0
    for line in REPORT_LINES:
        page.insert_text((72, y), line, fontsize=12)
        y += 24.0
    doc.save(str(pdf_path))
    page_count = len(doc)
    doc.close()
    print(f"已写出演示 PDF: {pdf_path}  (pages={page_count})")
    # corespine 缝:pdfspine 阶段在共享 sink 上记一条(仅元数据)。
    sink.emit("pdf.author", page_count=page_count)


def stage1_extract_pdf(pdf_path: Path) -> str:
    """STAGE 1 —— 用 pdfspine 抽取文本。

    pdfspine 是 Rust 扩展,对 RAG / agent 一无所知 —— corespine 是唯一共享词汇。
    """
    banner("STAGE 1 — pdfspine EXTRACT: 抽取 PDF 文本")
    doc = pdfspine.open(str(pdf_path))
    text = "\n".join(p.get_text() for p in doc)
    page_count = len(doc)
    doc.close()
    print(f"page_count = {page_count}")
    print(f"char_count = {len(text)}")
    print("---- 抽取文本 ----")
    print(text)
    print("------------------")
    # corespine 缝:跨包边界,仍是同一个 sink,仅记元数据。
    sink.emit("pdf.extract", page_count=page_count, char_count=len(text))
    return text


def stage2_rag(extracted_text: str) -> tuple[FactStore, NarrativeIndexRetriever, ChunkStore]:
    """STAGE 2 —— ragspine 灌库 + 接地回答(数值 + 叙事两条路)。"""
    banner("STAGE 2 — ragspine INGEST + RAG ANSWER")

    # 2a. 播种数值 FactStore(provenance 指向 STAGE-0 的 PDF)。
    store = FactStore(":memory:")
    store.init_schema()
    store.upsert_facts(
        [
            Fact(
                metric_code="REVENUE",
                entity="ACME_CN",
                geography="CN",
                channel="TOTAL",
                period_type="FY",
                period="2024",
                value=1320.0,
                unit="USD_M",
                source_doc_id="acme_fy2024.pdf",
                source_locator="page=1,line=2",
            )
        ]
    )
    print("[2a] 已播种 1 条数值 Fact (REVENUE / ACME_CN / FY2024 = 1320 USD_M)")
    sink.emit("rag.facts.ingest", fact_count=1)

    # 2b. 把 STAGE-1 抽取文本灌入叙事 ChunkStore(离线确定性 embedder,零网络)。
    cs = ChunkStore(":memory:")
    cs.init_schema()
    idx = NarrativeIndex(cs, embedding_backend=make_embedding_backend("deterministic"))
    n_chunks = idx.ingest(
        extracted_text,
        DocumentMeta(
            doc_id="acme_fy2024.pdf",
            title="ACME FY2024",
            topic="FIN",
            entity="ACME_CN",
            geography="CN",
            period="2024",
            language="en",
            sensitivity="INTERNAL",
        ),
    )
    print(f"[2b] 已把抽取文本灌入叙事索引,chunk_count = {n_chunks}")
    sink.emit("rag.narrative.ingest", chunk_count=n_chunks)

    # 2c. 接地回答。RagMockProvider 实现 corespine LLMProvider 缝(chat(messages,*,tools)->ChatCompletion)。
    retriever = NarrativeIndexRetriever(idx)
    provider = RagMockProvider()  # ← 共享缝:这就是一个 corespine LLMProvider

    def ask(question: str, *, narrative: bool) -> None:
        kwargs = {"narrative_retriever": retriever} if narrative else {}
        res = answer_question(question, store, provider, **kwargs)
        print(f"\nQ: {question}")
        print(f"  route   = {res.route}")
        print(f"  answer  = {res.answer}")
        print(f"  sources = {res.sources}")
        # corespine 缝:绝不传答案正文,只传元数据;route 字符串作为 *值* 是允许的(键名非禁用)。
        sink.emit(
            "rag.answer",
            route_code=res.route,
            has_sources=bool(res.sources),
            source_count=len(res.sources),
        )

    # 数值问题 -> 命中 FactStore,接地、带引用。
    ask("What was ACME_CN FY2024 REVENUE?", narrative=False)
    # 叙事问题 -> 从灌入的 PDF 文本检索,接地、带引用。
    ask("Which region does ACME primarily operate in?", narrative=True)
    # 诚实拒答:无匹配 fact(FY2030)时拒绝,而非编造。
    ask("What was ACME_CN FY2030 REVENUE?", narrative=False)

    return store, retriever, cs


def stage3_agents(store: FactStore, retriever: NarrativeIndexRetriever) -> None:
    """STAGE 3 —— spineagent 编排:agent 层通过工具驱动 ragspine,全在共享 sink 上。"""
    banner("STAGE 3 — spineagent ORCHESTRATION")

    # 3a. 定义一个 @function_tool,函数体回调 ragspine —— 闭合 agent->RAG 的环。
    @function_tool
    def query_report(question: str) -> str:
        """Answer a question about the ACME annual report from the RAG store."""
        res = answer_question(question, store, RagMockProvider(), narrative_retriever=retriever)
        return res.answer

    # 3b. 确定性 scripted provider —— 实现 corespine LLMProvider 缝。
    # 它说的是和 ragspine MockProvider、任意真实 Anthropic/OpenAI provider 完全相同的
    # corespine ChatCompletion 形状。
    class ScriptedReportModel:
        """两轮脚本:turn1 触发 tool_calls;turn2 从对话里读回工具结果并收尾。

        turn2 故意从 messages 中读取上一轮 {"role":"tool"} 的内容(即 query_report
        回调 ragspine 得到的接地答案),证明工具结果确实流回了模型 —— 这正是真实
        provider 会做的「依据工具输出作答」。
        """

        def __init__(self) -> None:
            self._calls = 0
            self._tool_call = LlmToolCall(
                "c1",
                FunctionCall(
                    "query_report",
                    '{"question": "Which region does ACME primarily operate in?"}',
                ),
            )

        def chat(self, messages: list[dict], *, tools: object = None) -> ChatCompletion:
            self._calls += 1
            if self._calls == 1:
                # turn 1:要求调用 query_report 工具。
                return ChatCompletion(
                    choices=(
                        Choice(
                            0,
                            ResponseMessage("assistant", None, (self._tool_call,)),
                            "tool_calls",
                        ),
                    )
                )
            # turn 2:从对话历史读回工具结果(接地答案),据此收尾。
            tool_output = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "tool"),
                "",
            )
            return ChatCompletion(
                choices=(
                    Choice(0, ResponseMessage("assistant", f"依据 ACME 报告(经 RAG 工具): {tool_output}")),
                )
            )

    print("[3a/3b] FunctionCallingAgent: scripted provider -> 调用 query_report 工具 -> 接地回答")
    agent = FunctionCallingAgent("report-agent", ScriptedReportModel(), [query_report])
    result = agent.step("Where does ACME operate?")
    print(f"  output = {result.output}")

    # 3c. 纯离线工具循环(无 LLM):SyntaxToolPolicy 路由 "<tool>: <arg>",$prev 串接上一步输出。
    print("\n[3c] 纯离线工具循环(无 LLM):net profit ~ revenue * margin = 1320 * 0.18")
    calc_out = ToolUsingAgent("calc", SyntaxToolPolicy(), [CalcTool()]).step(
        "calc: 1320 * 0.18\n", trace=sink
    )
    print(f"  output = {calc_out.output}")

    # 3d. Coordinator 编排多个 agent,全在共享 sink 上。
    print("\n[3d] Coordinator 顺序编排: summarizer(LlmAgent) + formatter(FunctionAgent)")
    coord = Coordinator(
        [
            LlmAgent("summarizer", MockProvider(), system="summarize"),  # corespine MockProvider
            FunctionAgent("formatter", lambda t: f"[REPORT] {t}"),
        ],
        trace=sink,
    )
    results = coord.run_sequential("ACME FY2024 revenue 1320M USD, margin 18%")
    for r in results:
        print(f"  {r.agent}: ok={r.ok} output={r.output}")


def finale() -> None:
    """FINALE —— 打印共享 trace + 证明隐私属性。"""
    banner("FINALE — 共享 trace 与隐私证明")

    # 一个 sink,贯穿三个包,顺序记录了所有阶段的 trace code。
    print("sink.codes() (三个包在同一个 sink 上的全部有序 trace code):")
    print(f"  {sink.codes()}")

    # 隐私属性:试图泄漏答案正文 -> 被拒,且不留痕。
    before = len(sink.events)
    print("\n尝试 sink.emit('leak.attempt', answer='secret 1320') ...")
    try:
        sink.emit("leak.attempt", answer="secret 1320")
        print("  !! 不应到达这里")
    except TraceError as e:
        after = len(sink.events)
        print(f"  被 TraceError 拒绝: {e}")
        print(f"  事件数未变: before={before} after={after} (拒绝任何正文,只记元数据)")

    # 用到的 corespine 缝总结。
    print(
        "\ncorespine 缝总结: "
        "LLMProvider Protocol (ragspine MockProvider + spineagent scripted provider + "
        "corespine MockProvider 都说 ChatCompletion), "
        "InProcessPrivacyTraceSink (一个 sink,三个包), "
        "Registry (三个包内部均使用)。"
    )

    # 顺手证明 Registry 缝可用(corespine 机制,三个包内部都靠它接后端)。
    reg: Registry[MockProvider] = Registry("llm-provider")
    reg.register("mock", lambda **kw: MockProvider(**kw))
    probe = reg.make("Mock", prefix="probe")  # 大小写不敏感
    completion: ChatCompletion = probe.chat([{"role": "user", "content": "hi"}])
    print(f"Registry 探针: make('Mock') -> {completion.choices[0].message.content!r}")


def main() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="spine_e2e_"))
    pdf_path = tmpdir / "acme_fy2024.pdf"
    try:
        stage0_author_pdf(pdf_path)
        extracted_text = stage1_extract_pdf(pdf_path)
        store, retriever, cs = stage2_rag(extracted_text)
        try:
            stage3_agents(store, retriever)
        finally:
            store.close()
            cs.close()
        finale()
        print("\nSPINE FAMILY E2E OK")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
