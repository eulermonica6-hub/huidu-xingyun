"""命令行入口：单次问答与简单 REPL。

用法（在项目根目录，先 ``pip install -e .`` 或设置 ``PYTHONPATH=src``）：

    python -m huidu_xingyun.cli ask "星云大师在当前稳定图中连接了哪些机构？"
    python -m huidu_xingyun.cli ask --no-llm "什么是人间佛教"
    python -m huidu_xingyun.cli repl
"""

from __future__ import annotations

import argparse
import sys

from .agent import (
    AgentContext,
    export_evidence_package,
    history_entry,
    run_agent,
    run_agent_verbose,
)
from .config import SecretLoader, get_runtime_paths, get_settings
from .models.factory import ModelBundle, ModelFactory
from .models.cache import LLMCache
from .repositories import CorpusRepository, GraphRepository
from .repositories.vector_store import VectorStore
from .schemas.response import FinalResponse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _attach_semantic(corpus: CorpusRepository, paths, loader: SecretLoader) -> None:
    """如果向量索引存在，挂接语义检索；任何失败都静默降级为关键词检索。"""
    index_path = paths.derived_root / "vector_metadata" / "document_embeddings.npy"
    if not index_path.exists():
        return
    try:
        from .repositories.embeddings import DashScopeEmbeddings, LocalBgeEmbeddings

        api_key = loader.first_key("ali")
        embedder = DashScopeEmbeddings(api_key) if api_key else LocalBgeEmbeddings()
        store = VectorStore(index_path)
        if store.count != corpus.size:
            return
        corpus.attach_semantic(store, embedder)
    except Exception:  # noqa: BLE001 - 语义后端可选，失败无感降级
        pass


def build_context(use_llm: bool = True) -> AgentContext:
    settings = get_settings()
    paths = get_runtime_paths()

    loader = SecretLoader(settings.secret_path)
    loader.load()

    graph = GraphRepository(paths).load()
    corpus = CorpusRepository(paths).load()
    _attach_semantic(corpus, paths, loader)

    bundle = ModelBundle()
    if use_llm:
        try:
            cache = LLMCache(paths.cache / "llm_cache.jsonl")
            bundle = ModelFactory(settings, loader).build_bundle(cache=cache)
        except Exception as exc:  # noqa: BLE001 - 降级为离线规则模式
            print(f"[warn] 模型初始化失败：{type(exc).__name__}，将以离线规则模式运行。")

    return AgentContext(bundle=bundle, graph=graph, corpus=corpus, settings=settings, paths=paths)


def render(final: FinalResponse) -> str:
    lines = [final.answer.rstrip()]
    if final.coverage_notice:
        lines.append(f"\n[覆盖说明] {final.coverage_notice}")
    if final.graph_paths:
        lines.append("\n[关系路径]")
        for path in final.graph_paths:
            lines.append("  " + " → ".join(path.nodes))
    if final.evidence_cards:
        lines.append("\n[证据]")
        for card in final.evidence_cards:
            header = f"  [{card.layer}] {card.volume} {card.article_title}".strip()
            lines.append(header)
            if card.quote:
                lines.append(f"    {card.quote}")
            if card.url:
                lines.append(f"    {card.url}")
    if final.follow_up_actions:
        lines.append("\n[可继续] " + "；".join(a.label for a in final.follow_up_actions))
    return "\n".join(lines)


def cmd_ask(args: argparse.Namespace) -> int:
    ctx = build_context(use_llm=not args.no_llm)
    final = run_agent(ctx, args.question)
    print(render(final))
    if args.export:
        path = export_evidence_package(final, ctx.paths)
        print(f"\n[已导出证据包] {path}")
    return 0


def cmd_repl(args: argparse.Namespace) -> int:
    ctx = build_context(use_llm=not args.no_llm)
    print("慧读星云 K-Agent 交互模式。输入问题回车；输入 /quit 退出。")
    history: list[dict] = []
    while True:
        try:
            query = input("\n你：").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            continue
        if query in {"/quit", "/exit"}:
            break
        final, state = run_agent_verbose(ctx, query, conversation_context=history)
        history.append(history_entry(query, state))
        print("\n助手：")
        print(render(final))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="huidu-xingyun", description="慧读星云 K-Agent CLI")
    parser.add_argument("--no-llm", action="store_true", help="不调用大模型，仅用规则与离线占位回答")
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="单次问答")
    ask.add_argument("question", help="要提问的问题")
    ask.add_argument("--export", action="store_true", help="把结果导出为 Markdown 证据包到 outputs/")
    ask.set_defaults(func=cmd_ask)

    repl = sub.add_parser("repl", help="交互式对话")
    repl.set_defaults(func=cmd_repl)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
