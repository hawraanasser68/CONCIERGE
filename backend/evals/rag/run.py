# Owner B — backend/evals/rag/run.py
#
# RAG eval runner. Two evaluation modes:
#
#   --retrieval   Embed each question directly, ANN-search the chunks table, compute
#                 hit@5 and MRR against the golden ground-truth chunk identifiers.
#                 Requires: MODELSERVER_URL, MODELSERVER_TOKEN, DATABASE_URL.
#
#   --answer      Send each question through POST /api/v1/chat/message, collect the
#                 response, then use an LLM judge (Claude) to score faithfulness and
#                 answer_relevancy (0-1 float). Requires: WIDGET_TOKEN, LLM_API_KEY.
#
#   --all         Both modes.
#
#   --dry-run     Validate golden.jsonl format and print summary.
#
# Thresholds (from eval_thresholds.yaml):
#   rag.hit_at_5       >= 0.75
#   rag.faithfulness   >= 0.70
#
# Ground-truth chunk identifiers use "page-slug:chunk_index" format (e.g.
# "business-hours:0"). The runner resolves these to chunk UUIDs via the DB.
#
# Required env vars per mode — see usage above.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = BASE_DIR / "golden.jsonl"
REQUIRED_FIELDS = {"id", "question", "ideal_answer", "ground_truth_chunks", "tenant_id"}

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Triple:
    id: str
    question: str
    ideal_answer: str
    ground_truth_chunks: list[str]   # "page-slug:chunk_index" identifiers
    tenant_id: str


@dataclass
class RetrievalResult:
    triple_id: str
    question: str
    hit: bool           # ground truth chunk in top-5
    rank: int | None    # 1-based rank of first hit (None if miss)


@dataclass
class AnswerResult:
    triple_id: str
    question: str
    response: str
    faithfulness: float       # LLM judge score 0-1
    answer_relevancy: float   # LLM judge score 0-1


# ── Golden set loader ─────────────────────────────────────────────────────────

def load_golden(path: Path = GOLDEN_PATH) -> list[Triple]:
    triples: list[Triple] = []
    with path.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno} invalid JSON: {e}") from e
            missing = REQUIRED_FIELDS - set(row)
            if missing:
                raise ValueError(f"{path}:{lineno} id={row.get('id')} missing: {sorted(missing)}")
            triples.append(Triple(
                id=row["id"],
                question=row["question"],
                ideal_answer=row["ideal_answer"],
                ground_truth_chunks=row["ground_truth_chunks"],
                tenant_id=row["tenant_id"],
            ))
    return triples


def dry_run(triples: list[Triple]) -> int:
    print(f"golden.jsonl valid — {len(triples)} triples")
    for t in triples:
        print(f"  [{t.id}] {t.question[:60]!r}")
    return 0


# ── Threshold loading ─────────────────────────────────────────────────────────

def _load_thresholds() -> dict[str, float]:
    thresholds_file = os.environ.get(
        "THRESHOLDS_FILE",
        str(Path(__file__).resolve().parents[3] / "eval_thresholds.yaml"),
    )
    defaults = {"hit_at_5": 0.75, "faithfulness": 0.70, "answer_relevancy": 0.60}
    try:
        import yaml  # type: ignore[import]
        with open(thresholds_file) as f:
            data = yaml.safe_load(f)
        rag = data.get("rag", {})
        return {
            "hit_at_5": float(rag.get("hit_at_5", defaults["hit_at_5"])),
            "faithfulness": float(rag.get("faithfulness", defaults["faithfulness"])),
            "answer_relevancy": float(rag.get("answer_relevancy", defaults["answer_relevancy"])),
        }
    except Exception:
        return defaults


# ── Retrieval eval ────────────────────────────────────────────────────────────

async def _resolve_chunk_ids(db_url: str, tenant_id: str) -> dict[str, uuid.UUID]:
    """Build a map from 'page-slug:chunk_index' → chunk UUID."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    mapping: dict[str, uuid.UUID] = {}

    async with factory() as sess:
        await sess.execute(
            text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
            {"tid": tenant_id},
        )
        rows = await sess.execute(text(
            """
            SELECT c.id, p.slug, c.chunk_index
            FROM chunks c
            JOIN cms_pages p ON p.id = c.page_id
            WHERE c.tenant_id = CAST(:tid AS uuid)
            """
        ), {"tid": tenant_id})
        for row in rows.all():
            key = f"{row.slug}:{row.chunk_index}"
            mapping[key] = row.id

    await engine.dispose()
    return mapping


async def _embed_text(text: str, modelserver_url: str, token: str) -> list[float]:
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{modelserver_url}/embed",
            json={"text": text},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


async def _ann_search(
    embedding: list[float],
    tenant_id: str,
    db_url: str,
    top_k: int = 5,
) -> list[uuid.UUID]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

    async with factory() as sess:
        await sess.execute(
            text("SELECT set_config('app.tenant_id', :tid, TRUE)"),
            {"tid": tenant_id},
        )
        rows = await sess.execute(text(
            """
            SELECT id
            FROM chunks
            WHERE tenant_id = CAST(:tid AS uuid)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
            """
        ), {"tid": tenant_id, "vec": vec_str, "k": top_k})
        result = [row.id for row in rows.all()]

    await engine.dispose()
    return result


async def _run_retrieval_async(
    triples: list[Triple],
    modelserver_url: str,
    modelserver_token: str,
    db_url: str,
) -> list[RetrievalResult]:
    chunk_map = await _resolve_chunk_ids(db_url, TENANT_A)
    results: list[RetrievalResult] = []

    for triple in triples:
        print(f"  [{triple.id}] embedding...", end=" ", flush=True)
        try:
            embedding = await _embed_text(triple.question, modelserver_url, modelserver_token)
            top_ids = await _ann_search(embedding, triple.tenant_id, db_url)

            # Resolve ground-truth chunk identifiers → UUIDs
            gt_uuids = set()
            for ref in triple.ground_truth_chunks:
                if ref in chunk_map:
                    gt_uuids.add(chunk_map[ref])
                else:
                    print(f"[warn] chunk ref '{ref}' not found in DB (indexing may not have run)")

            hit = any(cid in gt_uuids for cid in top_ids)
            rank: int | None = None
            for i, cid in enumerate(top_ids, 1):
                if cid in gt_uuids:
                    rank = i
                    break

            results.append(RetrievalResult(triple_id=triple.id, question=triple.question,
                                           hit=hit, rank=rank))
            print(f"hit={hit}" + (f" rank={rank}" if rank else ""))
        except Exception as exc:
            results.append(RetrievalResult(triple_id=triple.id, question=triple.question,
                                           hit=False, rank=None))
            print(f"ERROR {exc}")

    return results


def run_retrieval(triples: list[Triple]) -> tuple[list[RetrievalResult], dict[str, float]]:
    modelserver_url = os.environ.get("MODELSERVER_URL", "http://localhost:8001")
    modelserver_token = os.environ.get("MODELSERVER_TOKEN", "")
    db_url = os.environ.get("DATABASE_URL", "")
    thresholds = _load_thresholds()

    if not db_url:
        print("ERROR: DATABASE_URL required for --retrieval mode", file=sys.stderr)
        sys.exit(2)

    results = asyncio.run(_run_retrieval_async(triples, modelserver_url, modelserver_token, db_url))
    return results, thresholds


def _compute_retrieval_metrics(results: list[RetrievalResult]) -> dict[str, float]:
    n = len(results)
    if n == 0:
        return {"hit_at_5": 0.0, "mrr": 0.0}
    hits = sum(1 for r in results if r.hit)
    rr_sum = sum(1.0 / r.rank for r in results if r.rank is not None)
    return {"hit_at_5": hits / n, "mrr": rr_sum / n}


# ── Answer quality eval (LLM judge) ──────────────────────────────────────────

_JUDGE_PROMPT = """\
You are an impartial judge evaluating the quality of an AI assistant's answer.

Question: {question}

Expected ideal answer: {ideal_answer}

AI assistant's response: {response}

Score the response on two dimensions. Reply with ONLY valid JSON, no explanation:
{{
  "faithfulness": <float 0.0–1.0>,
  "answer_relevancy": <float 0.0–1.0>
}}

Scoring guide:
- faithfulness: does the response contain only accurate information consistent
  with the ideal answer? 1.0 = fully accurate, 0.0 = fabricated or contradictory.
- answer_relevancy: does the response directly address the question?
  1.0 = direct and complete, 0.0 = off-topic or refuses without reason."""


def _judge_response(
    question: str, ideal_answer: str, response: str, api_key: str
) -> dict[str, float]:
    import re

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": _JUDGE_PROMPT.format(
            question=question, ideal_answer=ideal_answer, response=response,
        )}],
    )
    text = msg.content[0].text.strip()
    # Strip markdown code fences if the model adds them
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        scores = json.loads(text)
    except Exception:
        # Fallback: extract the first {...} JSON object from the response
        m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if m:
            try:
                scores = json.loads(m.group(0))
            except Exception:
                print(f"  [judge] could not parse: {text[:120]!r}", file=sys.stderr)
                return {"faithfulness": 0.0, "answer_relevancy": 0.0}
        else:
            print(f"  [judge] no JSON found in: {text[:120]!r}", file=sys.stderr)
            return {"faithfulness": 0.0, "answer_relevancy": 0.0}
    return {
        "faithfulness": float(scores.get("faithfulness", 0.0)),
        "answer_relevancy": float(scores.get("answer_relevancy", 0.0)),
    }


def run_answer(triples: list[Triple]) -> tuple[list[AnswerResult], dict[str, float]]:
    import httpx

    base_url = os.environ.get("CONCIERGE_BASE_URL", "http://localhost:8000")
    widget_token = os.environ.get("WIDGET_TOKEN", "")
    api_key = os.environ.get("LLM_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    thresholds = _load_thresholds()

    if not widget_token:
        print("ERROR: WIDGET_TOKEN required for --answer mode", file=sys.stderr)
        sys.exit(2)
    if not api_key:
        print(
            "ERROR: LLM_API_KEY (or ANTHROPIC_API_KEY) required for --answer mode",
            file=sys.stderr,
        )
        sys.exit(2)

    # Same fix as agent_tool_selection/run.py: the widget JWT bakes a single
    # session_id at mint time and the backend enforces X-Session-Id == jwt.session_id.
    # Decode widget_id once from the supplied token, then mint a fresh token+session
    # per triple so each example is session-isolated.
    import base64
    try:
        _payload_b64 = widget_token.split(".")[1]
        _payload_b64 += "=" * (-len(_payload_b64) % 4)
        widget_id = json.loads(base64.urlsafe_b64decode(_payload_b64))["widget_id"]
    except Exception as exc:
        print(f"ERROR: could not decode widget_id from WIDGET_TOKEN: {exc}", file=sys.stderr)
        sys.exit(2)

    results: list[AnswerResult] = []
    with httpx.Client(base_url=base_url, timeout=30) as client:
        for triple in triples:
            print(f"  [{triple.id}] asking...", end=" ", flush=True)
            try:
                mint_resp = client.post(
                    "/api/v1/widget/token",
                    json={"widget_id": widget_id, "origin": "http://localhost:3000"},
                )
                mint_resp.raise_for_status()
                _mint = mint_resp.json()
                fresh_token = _mint["token"]
                session_id = _mint["session_id"]
                resp = client.post(
                    "/api/v1/chat/message",
                    json={"message": triple.question},
                    headers={
                        "Authorization": f"Bearer {fresh_token}",
                        "X-Session-Id": session_id,
                        "Origin": "http://localhost:3000",
                    },
                )
                resp.raise_for_status()
                response_text = resp.json().get("response", "")
            except Exception as exc:
                print(f"ERROR {exc}")
                results.append(AnswerResult(triple_id=triple.id, question=triple.question,
                                            response="", faithfulness=0.0, answer_relevancy=0.0))
                continue

            print(f"response={response_text[:60]!r} judging...", end=" ", flush=True)
            scores = _judge_response(triple.question, triple.ideal_answer, response_text, api_key)
            results.append(AnswerResult(
                triple_id=triple.id,
                question=triple.question,
                response=response_text,
                faithfulness=scores["faithfulness"],
                answer_relevancy=scores["answer_relevancy"],
            ))
            print(f"faithfulness={scores['faithfulness']:.2f}  "
                  f"answer_relevancy={scores['answer_relevancy']:.2f}")

    return results, thresholds


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="RAG eval runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--retrieval", action="store_true")
    group.add_argument("--answer", action="store_true")
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    triples = load_golden()

    if args.dry_run:
        return dry_run(triples)

    failed = False
    thresholds = _load_thresholds()

    if args.retrieval or args.all:
        print(f"\nretrieval eval  n={len(triples)}  threshold hit@5={thresholds['hit_at_5']:.0%}")
        ret_results, _ = run_retrieval(triples)
        metrics = _compute_retrieval_metrics(ret_results)
        print(f"  hit@5={metrics['hit_at_5']:.0%}  MRR={metrics['mrr']:.3f}")
        if metrics["hit_at_5"] < thresholds["hit_at_5"]:
            print(
                f"  FAIL — hit@5 {metrics['hit_at_5']:.0%}"
                f" < threshold {thresholds['hit_at_5']:.0%}"
            )
            failed = True
        else:
            print("  PASS")

    if args.answer or args.all:
        print(f"\nanswer quality eval  n={len(triples)}")
        ans_results, _ = run_answer(triples)
        n = len(ans_results)
        avg_faith = sum(r.faithfulness for r in ans_results) / n if n > 0 else 0.0
        avg_relev = sum(r.answer_relevancy for r in ans_results) / n if n > 0 else 0.0
        print(f"  avg faithfulness={avg_faith:.2f}  avg answer_relevancy={avg_relev:.2f}")
        if avg_faith < thresholds["faithfulness"]:
            print(
                f"  FAIL — faithfulness {avg_faith:.2f}"
                f" < threshold {thresholds['faithfulness']:.2f}"
            )
            failed = True
        else:
            print("  PASS (faithfulness)")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
