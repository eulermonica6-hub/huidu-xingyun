"""LangGraph 节点实现。

所有节点为 ``(state) -> dict`` 的部分状态更新函数，通过 :func:`build_nodes`
闭包持有模型与仓储。领域证据路线始终以结构化数据为准，LLM 只在证据包内归纳。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from ..repositories.corpus import content_terms
from ..schemas.evidence import EvidenceItem, EvidenceLayer
from ..schemas.intent import IntentResult
from ..schemas.response import (
    EvidenceCard,
    FinalResponse,
    FollowUpAction,
    GraphPath,
    VerificationResult,
)
from .context import AgentContext
from .parsing import parse_json_object
from .prompts import (
    ANSWER_SYSTEM,
    DIRECT_SYSTEM,
    INTENT_SYSTEM,
    VERIFY_SYSTEM,
    answer_user_prompt,
    verify_user_prompt,
)
from .routing import (
    merge_with_rule_hint,
    route_for_intent,
    rule_intent_hint,
    rule_only_intent,
)


def _format_evidence(items: list[EvidenceItem], limit: int | None = None) -> str:
    """把证据包格式化为 LLM 提示文本；``limit`` 用于截断大证据块（完整证据仍进证据卡）。"""
    if limit is not None and len(items) > limit:
        shown = items[:limit]
    else:
        shown = items
    lines: list[str] = []
    for index, item in enumerate(shown, start=1):
        layer = item.layer.value if hasattr(item.layer, "value") else str(item.layer)
        if layer == "C":
            head = f"[{index}][C] {item.volume} {item.article_title}".strip()
        else:
            head = f"[{index}][{layer}] {item.source} —{item.relation}→ {item.target}"
            if item.volume or item.article_title:
                head += f"（{item.volume} {item.article_title}）"
        lines.append(head)
        if item.quote:
            lines.append(f"  原文：{item.quote}")
        if item.url:
            lines.append(f"  出处：{item.url}")
    if limit is not None and len(items) > limit:
        lines.append(f"（证据共 {len(items)} 条，仅展示前 {limit} 条，按层级 A→B→C 优先）")
    return "\n".join(lines)


def _format_paths(paths: list[dict[str, Any]]) -> str:
    output: list[str] = []
    for path in paths:
        nodes = path.get("nodes", [])
        relations = path.get("relations", [])
        if not nodes:
            continue
        chain = nodes[0]
        for relation, node in zip(relations, nodes[1:]):
            chain += f" —{relation}→ {node}"
        output.append(chain)
    return "\n".join(output)


def _path_to_dict(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if not steps:
        return {"nodes": [], "relations": []}
    return {
        "nodes": [steps[0]["from_name"]] + [step["to_name"] for step in steps],
        "relations": [step["relation_label"] for step in steps],
    }


def _format_analytics(graph_results: list[dict[str, Any]]) -> str:
    block = graph_results[0] if graph_results else {}
    top = block.get("top", [])
    overview = block.get("overview", {})
    lines = [f"图谱概览：{json.dumps(overview, ensure_ascii=False)}"]
    lines.append(f"按 {block.get('metric', 'bridge_score')} 排序的节点：")
    for row in top:
        lines.append(
            f"- {row['name']}（{row['entity_type']}）：{row['metric']}={row['value']}，"
            f"degree={row['degree']}，betweenness={row['betweenness']}"
        )
    return "\n".join(lines)


def _build_clarification(state: dict[str, Any]) -> str:
    ambiguous = [e for e in state.get("resolved_entities", []) if getattr(e, "is_ambiguous", False)]
    if ambiguous:
        lines = ["请帮我确认你指的是哪一个："]
        for entity in ambiguous:
            options = "、".join(
                f"{c.name}（{c.entity_type}）" for c in entity.candidates[:5]
            )
            lines.append(f"- “{entity.name}” 可能指：{options}")
        return "\n".join(lines)
    return "该问题当前无法在语料中唯一确定，或超出本系统支持范围。请换一种问法或提供更多上下文。"


def _coverage_notice(route: str, items: list[EvidenceItem]) -> str:
    if route == "llm_direct":
        return "本回答为一般说明或系统帮助，不来自《星云大师全集》语料。"
    if route == "clarify_or_refuse":
        return "当前问题需要澄清或超出可支持范围。"
    if route == "graph_analytics":
        return "结论基于冻结图谱网络指标（桥接得分等），属结构统计分析，非关系性证据。"
    if not items:
        return "当前正式图谱与全文语料均未检索到充分证据，无法给出有据结论。"
    layers = {item.layer for item in items}
    if layers <= {EvidenceLayer.CORPUS}:
        return "以下线索来自全文检索（C 层），尚未进入正式知识图谱，请谨慎采用。"
    notes = []
    if EvidenceLayer.STABLE in layers:
        notes.append("稳定关系（A 层）")
    if EvidenceLayer.CLAIM in layers:
        notes.append("语境命题（B 层，需以限定语表达）")
    return "结论基于：" + "、".join(notes) + "。"


def _follow_ups(route: str) -> list[FollowUpAction]:
    actions = [FollowUpAction(label="查看原文", kind="open_source")]
    if route in ("graph_direct", "graph_retrieve"):
        actions.append(FollowUpAction(label="展开关系子图", kind="expand_subgraph"))
    if route in ("graph_retrieve", "corpus_retrieve"):
        actions.append(FollowUpAction(label="导出研究证据包", kind="export_package"))
    actions.append(FollowUpAction(label="提交关系纠错", kind="submit_feedback"))
    return actions


def _fallback_evidence_answer(state: dict[str, Any]) -> str:
    items = state.get("evidence_items", [])
    if not items:
        return "未在语料与图谱中检索到充分证据。"
    lines = ["（离线占位回答）依据检索到的证据归纳如下："]
    for item in items[:8]:
        layer = item.layer.value if hasattr(item.layer, "value") else str(item.layer)
        if layer == "C":
            head = f"- [C] {item.volume} {item.article_title}".strip()
        else:
            head = f"- [{layer}] {item.source} —{item.relation}→ {item.target}"
        if item.quote:
            head += f"：{item.quote[:60]}"
        lines.append(head)
    return "\n".join(lines)


def _fallback_analytics_answer(state: dict[str, Any]) -> str:
    top = (state.get("graph_results") or [{}])[0].get("top", [])
    if not top:
        return "（离线占位回答）未读取到图谱指标。"
    lines = ["（离线占位回答）按桥接得分排序的节点："]
    for row in top:
        lines.append(f"- {row['name']}（{row['entity_type']}）：bridge_score={row['value']}")
    return "\n".join(lines)


_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("Institution", ["机构", "院校", "大学", "组织", "团体", "佛光山"]),
    ("Classic", ["经典", "经"]),
    ("DoctrineTerm", ["教义", "教理"]),
    ("Concept", ["概念"]),
    ("PracticeActivity", ["实践", "活动", "法会", "弘法"]),
    ("PlaceRealm", ["地点", "地方", "道场", "寺院"]),
    ("BuddhistFigure", ["人物", "祖师"]),
]


def _neighbor_type_from_query(query: str) -> str | None:
    for entity_type, words in _TYPE_HINTS:
        if any(word in query for word in words):
            return entity_type
    return None


_BACKREF_PATTERN = re.compile(r"它|他|她|这|该|此|其|上述|前面|刚刚|刚才|上一[轮问查]")


def _has_backward_reference(query: str) -> bool:
    return bool(_BACKREF_PATTERN.search(query))


def build_nodes(ctx: AgentContext) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    bundle = ctx.bundle
    graph = ctx.graph
    corpus = ctx.corpus
    settings = ctx.settings
    paths = ctx.paths

    def normalize_input(state: dict[str, Any]) -> dict[str, Any]:
        query = " ".join((state.get("user_query") or "").split())
        return {
            "normalized_query": query,
            "errors": [],
            "revision_count": 0,
            "trace_id": uuid.uuid4().hex[:12],
            "graph_results": [],
            "claim_results": [],
            "corpus_results": [],
            "evidence_items": [],
            "graph_paths": [],
        }

    def resolve_conversation_context(state: dict[str, Any]) -> dict[str, Any]:
        # 多轮指代：若本问包含回指（它/他/该/此…），把上一轮已解析实体的名字带过来。
        query = state["normalized_query"]
        history = state.get("conversation_context") or []
        carryover_names: list[str] = []
        if _has_backward_reference(query) and history:
            last = history[-1]
            carryover_names = [
                entry.get("name") for entry in last.get("entities", []) if entry.get("name")
            ]
        return {"carryover_names": carryover_names}

    def classify_intent(state: dict[str, Any]) -> dict[str, Any]:
        query = state["normalized_query"]
        hint = rule_intent_hint(query)
        errors = list(state.get("errors") or [])
        intent = None
        if bundle is not None and bundle.router is not None:
            try:
                text = bundle.classify(
                    [SystemMessage(content=INTENT_SYSTEM), HumanMessage(content=query)]
                )
                intent = parse_json_object(text, IntentResult)
            except Exception as exc:  # noqa: BLE001 - 降级到规则先验
                errors.append(f"intent_llm_error:{type(exc).__name__}")
        if intent is None:
            intent = rule_only_intent(query, hint)
        else:
            intent = merge_with_rule_hint(intent, hint)
        return {"intent": intent, "errors": errors}

    def resolve_entities(state: dict[str, Any]) -> dict[str, Any]:
        intent = state["intent"]
        mentions = [e.mention for e in intent.entities if e.mention]
        # 原文子串提取最可靠：LLM 可能对提及做繁简转换/改写，原文提及优先补进。
        verbatim = graph.extract_mentions(state["normalized_query"])
        mentions = list(dict.fromkeys(verbatim + mentions)) if verbatim else mentions
        if not mentions:
            mentions = graph.extract_mentions(state["normalized_query"])
        carryover = state.get("carryover_names") or []
        if carryover and _has_backward_reference(state["normalized_query"]):
            mentions = list(dict.fromkeys(carryover + mentions))
        resolved = graph.resolve_entities(mentions)
        # 去重：若歧义项的候选与某个已唯一解析的实体重叠（LLM 繁简改写导致），以唯一解析为准丢弃歧义。
        unique_ids = {e.entity_id for e in resolved if e.resolved and not e.is_ambiguous}
        if unique_ids:
            resolved = [
                e
                for e in resolved
                if not (e.is_ambiguous and any(c.entity_id in unique_ids for c in e.candidates))
            ]
        # 去重：同一实体被原文提及 + LLM 提及各解析一次时，只保留一份。
        seen_ids: set[str] = set()
        deduped: list[Any] = []
        for entity in resolved:
            if entity.resolved:
                if entity.entity_id in seen_ids:
                    continue
                seen_ids.add(entity.entity_id)
            deduped.append(entity)
        return {"resolved_entities": deduped}

    def plan_route(state: dict[str, Any]) -> dict[str, Any]:
        route = route_for_intent(state["intent"], state["resolved_entities"])
        return {"route": route}

    def graph_direct(state: dict[str, Any]) -> dict[str, Any]:
        ids = [e.entity_id for e in state["resolved_entities"] if e.resolved]
        neighbor_type = _neighbor_type_from_query(state["normalized_query"])
        results: list[dict[str, Any]] = []
        for entity_id in ids:
            for rel in graph.search_relations([entity_id], neighbor_type=neighbor_type, limit=20):
                results.append(
                    {
                        "relation": rel,
                        "evidence": graph.get_relation_evidence(rel["relation_id"])[:3],
                    }
                )
        return {"graph_results": results}

    def graph_retrieve(state: dict[str, Any]) -> dict[str, Any]:
        entities = [e for e in state["resolved_entities"] if e.resolved]
        ids = [e.entity_id for e in entities]
        neighbor_type = _neighbor_type_from_query(state["normalized_query"])
        graph_results: list[dict[str, Any]] = []
        claim_results: list[dict[str, Any]] = []
        for entity_id in ids:
            for rel in graph.search_relations([entity_id], neighbor_type=neighbor_type, limit=15):
                graph_results.append(
                    {
                        "relation": rel,
                        "evidence": graph.get_relation_evidence(rel["relation_id"])[:2],
                    }
                )
            for crel in graph.claim_relations_for_entity(entity_id, limit=10):
                claim_results.append({"claim_relation": crel})

        paths: list[dict[str, Any]] = []
        if len(ids) >= 2:
            steps = graph.find_paths(ids[0], ids[-1], max_depth=3, limit=3)
            paths = [_path_to_dict(s) for s in steps]

        terms = [e.name for e in entities] or [state["normalized_query"]]
        query = " ".join(terms)
        corpus_results = corpus.search_semantic(query, k=6)
        if not corpus_results:
            corpus_results = corpus.search(query, k=6)
        return {
            "graph_results": graph_results,
            "claim_results": claim_results,
            "corpus_results": [_corpus_row(d) for d in corpus_results],
            "graph_paths": paths,
        }

    def corpus_retrieve(state: dict[str, Any]) -> dict[str, Any]:
        entities = [e for e in state["resolved_entities"] if e.resolved]
        names = [e.name for e in entities]
        terms = list(dict.fromkeys(t for t in names + content_terms(state["normalized_query"]) if t))
        query = state["normalized_query"]
        results = corpus.search_semantic(" ".join(names) if names else query, k=8)
        if not results:
            results = corpus.search_full_text(" ".join(terms), k=8)
        if not results:
            results = corpus.search_metadata(" ".join(terms), k=8)
        return {"corpus_results": [_corpus_row(d) for d in results]}

    def graph_analytics(state: dict[str, Any]) -> dict[str, Any]:
        query = state["normalized_query"]
        entity_type = None
        if "机构" in query:
            entity_type = "Institution"
        elif "经典" in query:
            entity_type = "Classic"
        top = graph.rank_entities(metric="bridge_score", entity_type=entity_type, k=10)
        return {
            "graph_results": [
                {
                    "kind": "analytics",
                    "top": top,
                    "overview": graph.overview(),
                    "metric": "bridge_score",
                    "entity_type": entity_type,
                }
            ]
        }

    def llm_direct(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    def clarify_or_refuse(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    def fuse_evidence(state: dict[str, Any]) -> dict[str, Any]:
        items: list[EvidenceItem] = []
        for gr in state.get("graph_results", []):
            if gr.get("kind") == "analytics":
                continue
            rel = gr.get("relation")
            if not rel:
                continue
            evidence = gr.get("evidence", []) or []
            if evidence:
                for ev in evidence:
                    items.append(
                        EvidenceItem(
                            evidence_id=ev["evidence_id"],
                            layer=EvidenceLayer.STABLE,
                            source=rel["source_name"],
                            relation=rel["relation_label"],
                            target=rel["target_name"],
                            document_id=ev.get("document_id", ""),
                            paragraph_uid=ev.get("paragraph_id", ""),
                            quote=ev.get("text", ""),
                            url=ev.get("source_url", ""),
                            article_support_count=ev.get("support_count", 1),
                            reliability="A",
                        )
                    )
            else:
                items.append(
                    EvidenceItem(
                        evidence_id=rel["relation_id"],
                        layer=EvidenceLayer.STABLE,
                        source=rel["source_name"],
                        relation=rel["relation_label"],
                        target=rel["target_name"],
                        quote=rel.get("example_text", ""),
                        url=rel.get("example_url", ""),
                        article_support_count=rel.get("document_count", 0),
                        reliability="A",
                    )
                )
        for cr in state.get("claim_results", []):
            crel = cr.get("claim_relation")
            if not crel:
                continue
            items.append(
                EvidenceItem(
                    evidence_id=crel["claim_relation_id"],
                    layer=EvidenceLayer.CLAIM,
                    source=crel["source_name"],
                    relation=crel["relation_label"],
                    target=crel["target_name"],
                    quote=crel.get("example_text", ""),
                    url=crel.get("example_url", ""),
                    reliability="B",
                )
            )
        for co in state.get("corpus_results", []):
            items.append(
                EvidenceItem(
                    evidence_id=f"corpus_{co['document_id']}",
                    layer=EvidenceLayer.CORPUS,
                    article_title=co.get("title", ""),
                    volume=co.get("book_title", ""),
                    document_id=co.get("document_id", ""),
                    quote=co.get("quote", ""),
                    url=co.get("source_url", ""),
                    reliability="C",
                )
            )
        seen: set[str] = set()
        deduped: list[EvidenceItem] = []
        for item in items:
            key = item.evidence_id + item.quote[:40]
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return {"evidence_items": deduped}

    def generate_answer(state: dict[str, Any]) -> dict[str, Any]:
        route = state["route"]
        query = state["normalized_query"]
        if route == "llm_direct":
            if bundle is not None and bundle.reasoner is not None:
                try:
                    return {
                        "draft_answer": bundle.generate(
                            [SystemMessage(content=DIRECT_SYSTEM), HumanMessage(content=query)]
                        )
                    }
                except Exception:  # noqa: BLE001 - 模型异常退回占位说明
                    return {"draft_answer": "（回答模型暂时不可用，请稍后重试。）"}
            return {"draft_answer": "（系统当前未配置回答模型。）"}
        if route == "clarify_or_refuse":
            return {"draft_answer": _build_clarification(state)}
        if route == "graph_analytics":
            block = _format_analytics(state.get("graph_results", []))
            if bundle is not None and bundle.reasoner is not None:
                prompt = (
                    f"用户问题：{query}\n\n图谱计算结果：\n{block}\n\n"
                    "请解释其结构意义，不得推断历史因果，也不得把中心性直接说成『思想最重要』。"
                )
                try:
                    return {
                        "draft_answer": bundle.generate(
                            [SystemMessage(content=ANSWER_SYSTEM), HumanMessage(content=prompt)]
                        )
                    }
                except Exception:  # noqa: BLE001
                    return {"draft_answer": _fallback_analytics_answer(state)}
            return {"draft_answer": _fallback_analytics_answer(state)}
        # 证据路线
        evidence_block = _format_evidence(state.get("evidence_items", []), limit=20)
        paths_block = _format_paths(state.get("graph_paths", []))
        if bundle is not None and bundle.reasoner is not None:
            try:
                return {
                    "draft_answer": bundle.generate(
                        [
                            SystemMessage(content=ANSWER_SYSTEM),
                            HumanMessage(content=answer_user_prompt(query, evidence_block, paths_block)),
                        ]
                    )
                }
            except Exception:  # noqa: BLE001 - 内容过滤/网络异常退回结构化证据摘要
                return {"draft_answer": _fallback_evidence_answer(state)}
        return {"draft_answer": _fallback_evidence_answer(state)}

    def verify_answer(state: dict[str, Any]) -> dict[str, Any]:
        route = state["route"]
        # 直接回答、澄清与图谱计算解释不套用证据逐句审校。
        if route in ("llm_direct", "clarify_or_refuse", "graph_analytics"):
            return {"verification_result": {"passes": True, "sentence_checks": [], "summary": ""}}
        draft = state.get("draft_answer", "")
        evidence_block = _format_evidence(state.get("evidence_items", []), limit=20)
        if bundle is not None and bundle.verifier is not None:
            result = None
            errors = list(state.get("errors") or [])
            try:
                text = bundle.verify(
                    [
                        SystemMessage(content=VERIFY_SYSTEM),
                        HumanMessage(content=verify_user_prompt(draft, evidence_block)),
                    ]
                )
                result = parse_json_object(text, VerificationResult)
            except Exception as exc:  # noqa: BLE001 - 审校失败不阻断
                errors.append(f"verify_error:{type(exc).__name__}")
            if result is None:
                result = VerificationResult(
                    passes=True,
                    sentence_checks=[],
                    summary="verify_parse_fallback",
                )
            checks = [
                {
                    "sentence": c.sentence,
                    "has_evidence": c.has_evidence,
                    "evidence_ids": c.evidence_ids,
                    "issue": c.issue,
                }
                for c in result.sentence_checks
            ]
            return {
                "verification_result": {
                    "passes": result.passes,
                    "sentence_checks": checks,
                    "summary": result.summary,
                },
                "errors": errors,
            }
        # 无审校模型时不设证据门控，避免离线模式无限修订。
        return {"verification_result": {"passes": True, "sentence_checks": [], "summary": ""}}

    def revise_answer(state: dict[str, Any]) -> dict[str, Any]:
        if bundle is None or bundle.reasoner is None:
            return {"revision_count": state.get("revision_count", 0) + 1}
        feedback = (state.get("verification_result") or {}).get("summary", "")
        query = state["normalized_query"]
        evidence_block = _format_evidence(state.get("evidence_items", []), limit=20)
        paths_block = _format_paths(state.get("graph_paths", []))
        prompt = answer_user_prompt(query, evidence_block, paths_block)
        prompt += f"\n\n上一稿审校反馈：{feedback}\n请修正上述问题后重新作答。"
        try:
            draft = bundle.generate(
                [SystemMessage(content=ANSWER_SYSTEM), HumanMessage(content=prompt)]
            )
        except Exception:  # noqa: BLE001 - 修订失败保留原稿
            draft = state.get("draft_answer", "")
        return {"draft_answer": draft, "revision_count": state.get("revision_count", 0) + 1}

    def format_response(state: dict[str, Any]) -> dict[str, Any]:
        route = state["route"]
        items = state.get("evidence_items", [])
        cards = []
        for item in items:
            title = item.article_title
            volume = item.volume
            if (not title or not volume) and item.document_id and corpus is not None:
                doc = corpus.get(item.document_id)
                if doc:
                    title = title or doc.get("title", "")
                    volume = volume or doc.get("book_title", "")
            cards.append(
                EvidenceCard(
                    evidence_id=item.evidence_id,
                    layer=item.layer.value if hasattr(item.layer, "value") else str(item.layer),
                    article_title=title,
                    volume=volume,
                    quote=item.quote,
                    url=item.url,
                    paragraph_uid=item.paragraph_uid,
                )
            )
        graph_paths = [
            GraphPath(nodes=p["nodes"], relations=p["relations"])
            for p in state.get("graph_paths", [])
        ]
        claims = [item.quote for item in items if item.layer == EvidenceLayer.CLAIM]
        final = FinalResponse(
            answer=state.get("draft_answer", ""),
            evidence_cards=cards,
            graph_paths=graph_paths,
            contextual_claims=claims,
            coverage_notice=_coverage_notice(route, items),
            follow_up_actions=_follow_ups(route),
            route=route,
            trace_id=state.get("trace_id", ""),
        )
        return {"final_response": final}

    def write_audit_log(state: dict[str, Any]) -> dict[str, Any]:
        intent = state.get("intent")
        entry = {
            "trace_id": state.get("trace_id"),
            "route": state.get("route"),
            "query": state.get("normalized_query"),
            "intent": intent.primary_intent.value if intent is not None else None,
            "evidence_count": len(state.get("evidence_items", [])),
            "answer_chars": len(state.get("draft_answer", "") or ""),
            "verify_passes": (state.get("verification_result") or {}).get("passes"),
            "revision_count": state.get("revision_count", 0),
            "errors": state.get("errors", []),
            "models": {
                "router": settings.router_model or settings.router_provider,
                "reasoner": settings.reasoner_model or settings.reasoner_provider,
                "verifier": settings.verifier_model or settings.verifier_provider,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        try:
            paths.logs.mkdir(parents=True, exist_ok=True)
            with (paths.logs / "audit.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return {}

    return {
        "normalize_input": normalize_input,
        "resolve_conversation_context": resolve_conversation_context,
        "classify_intent": classify_intent,
        "resolve_entities": resolve_entities,
        "plan_route": plan_route,
        "graph_direct": graph_direct,
        "graph_retrieve": graph_retrieve,
        "corpus_retrieve": corpus_retrieve,
        "graph_analytics": graph_analytics,
        "llm_direct": llm_direct,
        "clarify_or_refuse": clarify_or_refuse,
        "fuse_evidence": fuse_evidence,
        "generate_answer": generate_answer,
        "verify_answer": verify_answer,
        "revise_answer": revise_answer,
        "format_response": format_response,
        "write_audit_log": write_audit_log,
    }


def _corpus_row(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": doc["document_id"],
        "title": doc.get("title", ""),
        "book_title": doc.get("book_title", ""),
        "category": doc.get("category", ""),
        "source_url": doc.get("source_url", ""),
        "quote": doc.get("quote", ""),
    }
