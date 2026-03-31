# pdf_qa.py
import os
import re
from typing import List
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Use the more capable model for better answers
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_CONTEXT_CHARS = 4000
SYNTHESIS_MAX_CHARS = 4000
SAFE_PROMPT_LIMIT = 6000

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = Groq(api_key=api_key)
    return _client


def _safe_truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = max(
        text.rfind(". ", 0, max_chars),
        text.rfind("\n", 0, max_chars),
    )
    if cut == -1 or cut < max_chars * 0.5:
        return text[:max_chars].rstrip()
    return text[: cut + 1].rstrip()


def _score_chunk(question: str, chunk: str) -> int:
    if not question or not chunk:
        return 0
    q = question.lower()
    c = chunk.lower()

    stop = {
        "the","and","with","from","into","about","using","for","to","of",
        "a","an","in","on","at","by","as","is","are","was","were","be","been","or","that","this","these","those","it","its","their"
    }
    q_tokens = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", q) if w not in stop]
    if not q_tokens:
        return 0

    def variants(w: str):
        base = w
        out = {base}
        if base.endswith("s"):
            out.add(base[:-1])
        if base.endswith("es") and len(base) > 3:
            out.add(base[:-2])
        if base.endswith("ing") and len(base) > 4:
            out.add(base[:-3])
            out.add(base[:-3] + "e")
        if base.endswith("ed") and len(base) > 3:
            out.add(base[:-2])
        return out

    score = 0.0
    for w in q_tokens:
        exact = c.count(w)
        score += exact * 3
        for v in variants(w):
            if v != w:
                score += c.count(v) * 1.5

    bigrams = [f"{q_tokens[i]} {q_tokens[i+1]}" for i in range(len(q_tokens)-1)]
    for bg in bigrams[:4]:
        score += c.count(bg) * 4

    heading_bonus = 0
    for line in chunk.splitlines():
        if 0 < len(line) <= 80:
            l_lower = line.lower()
            if any(k in l_lower for k in q_tokens):
                words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", line)]
                if words:
                    caps = sum(1 for w in words if (w.isupper() or (len(w) > 1 and w[0].isupper())))
                    if caps >= max(1, int(0.5 * len(words))):
                        heading_bonus += 5
    score += heading_bonus

    fm_indicators = ["table of contents","contents","foreword","preface","acknowledgments","copyright","isbn","index"]
    fm_hits = sum(1 for k in fm_indicators if k in c)
    if fm_hits >= 2:
        score -= 10

    norm = max(1.0, (len(chunk) ** 0.5) / 40.0)
    score = int(round(score / norm))
    return score


def _select_relevant_chunks(question: str, chunks: List[str], top_k: int = 3) -> List[str]:
    if not chunks:
        return []
    scored = [(idx, _score_chunk(question, ch)) for idx, ch in enumerate(chunks)]
    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [chunks[i] for i, s in scored[:top_k] if s > 0]
    if not selected:
        return chunks[:min(len(chunks), 2)]
    return selected


def _make_windows(text: str, window: int = 1400, overlap: int = 250) -> List[str]:
    text = text or ""
    if not text:
        return []
    if len(text) <= window:
        return [text]
    step = max(1, window - overlap)
    windows = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + window, n)
        windows.append(text[start:end].strip())
        if end == n:
            break
        start += step
    return [w for w in windows if w]


def _gather_definition_candidates(question: str, text: str) -> List[str]:
    q = (question or "").strip().lower()
    term = None
    m = re.match(r"\s*(what\s+is|define)\s+([a-zA-Z0-9 _-]+?)\?*$", q)
    if m:
        term = m.group(2).strip().rstrip('.')
    if not term or len(term) > 50:
        return []

    tpat = re.escape(term)
    patterns = [
        rf"\b(a|an|the)\s+{tpat}\s+is\b",
        rf"\b{tpat}\s+is\b",
        rf"\b{tpat}\s+are\b",
        rf"\b{tpat}[^\n]{{0,40}}\bdefined\s+as\b",
        rf"\b{tpat}[^\n]{{0,40}}\brefers\s+to\b",
        rf"^\s*{tpat}s?\s*$",
        rf"^\s*definition\s+of\s+{tpat}\b",
    ]
    candidates: List[str] = []
    n = len(text)
    for pat in patterns:
        for m2 in re.finditer(pat, text, flags=re.IGNORECASE | re.MULTILINE):
            start = max(0, m2.start() - 400)
            end = min(n, m2.end() + 700)
            span = text[start:end].strip()
            if span and span not in candidates:
                candidates.append(span)
            if len(candidates) >= 6:
                break
        if len(candidates) >= 6:
            break
    return candidates


def ask_groq(question: str, context: str) -> str:
    if not context.strip():
        return "No content found to answer from."

    client = _get_client()
    chunks = _make_windows(context, window=1400, overlap=250)

    is_definition = bool(re.match(r"\s*(what\s+is|define)\b", (question or "").strip().lower()))
    if is_definition:
        defs = _gather_definition_candidates(question, context)
        if defs:
            chunks = defs + chunks

    partial_answers = []
    rel_chunks = _select_relevant_chunks(question, chunks, top_k=3)

    for i, chunk in enumerate(rel_chunks, 1):
        static_overhead = (
            len("Answer the question using ONLY the context. If the answer isn't in the context, say \"Not found in the document.\" ")
            + len(f"\n\nContext (part {i}/{len(rel_chunks)}):\n\nQuestion: {question}")
        )
        allowed_context = max(1000, min(MAX_CONTEXT_CHARS, SAFE_PROMPT_LIMIT - static_overhead))
        safe_chunk = _safe_truncate(chunk, allowed_context)

        if is_definition:
            prompt = (
                "Provide a clear, textbook-style definition based ONLY on this context. "
                "Prefer sentences like 'A <term> is ...' or headings. Ignore code variables or arrays. "
                "If a definition isn't present, reply: Not found in the document. "
                f"\n\nContext (part {i}/{len(rel_chunks)}):\n{safe_chunk}\n\nQuestion: {question}"
            )
        else:
            prompt = (
                "Answer the question using ONLY the context below. Be concise and accurate. "
                "If the answer isn't in the context, say \"Not found in the document.\" "
                f"\n\nContext (part {i}/{len(rel_chunks)}):\n{safe_chunk}\n\nQuestion: {question}"
            )

        if len(prompt) > SAFE_PROMPT_LIMIT:
            overflow = len(prompt) - SAFE_PROMPT_LIMIT + 200
            safe_chunk = _safe_truncate(safe_chunk, max(500, len(safe_chunk) - overflow))
            prompt = prompt.replace(chunk, safe_chunk)

        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise document reader. Answer only from the provided context."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=600,
        )
        partial_answers.append(resp.choices[0].message.content.strip())

    def _is_substantive(a: str) -> bool:
        if not a:
            return False
        al = a.strip().lower()
        return ("not found" not in al) and (len(al) > 20)

    substantive_answers = [a for a in partial_answers if _is_substantive(a)]

    if not substantive_answers:
        # Fallback: merged context retry
        rel_chunks_full = _select_relevant_chunks(question, chunks, top_k=5)
        merged = "\n\n".join(rel_chunks_full)
        merged = _safe_truncate(merged, MAX_CONTEXT_CHARS)
        fallback_prompt = (
            "Answer the question using the context below. "
            "If exact phrases aren't present, summarize the closest relevant information. "
            "If nothing relevant is present, say 'Not found in the document.'\n\n"
            f"Context:\n{merged}\n\nQuestion: {question}\nAnswer:"
        )
        if len(fallback_prompt) > SAFE_PROMPT_LIMIT:
            merged = _safe_truncate(merged, max(800, MAX_CONTEXT_CHARS - 400))
            fallback_prompt = (
                "Answer the question using the context below. "
                "If nothing relevant is present, say 'Not found in the document.'\n\n"
                f"Context:\n{merged}\n\nQuestion: {question}\nAnswer:"
            )
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "Answer questions based on provided context."},
                    {"role": "user", "content": fallback_prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            fb = resp.choices[0].message.content.strip()
            if fb:
                return fb
        except Exception:
            pass
        return "Not found in the document."

    # Synthesis pass
    synthesis_parts: List[str] = []
    running = 0
    for ans in substantive_answers:
        if running + len(ans) + 8 > SYNTHESIS_MAX_CHARS:
            break
        synthesis_parts.append(ans)
        running += len(ans) + 8

    synthesis_context = "\n\n---\n".join(synthesis_parts)
    if not synthesis_context:
        return "Not found in the document."

    if is_definition:
        synth_prompt = (
            "Combine the notes into a single, precise definition. Start with the general definition; "
            "mention key properties if provided. If missing, reply: Not found in the document.\n\n"
            f"{synthesis_context}\n\nDefinition:"
        )
    else:
        synth_prompt = (
            "Combine the notes below into one clear, concise answer. "
            "If they conflict, prefer the clearest passage. "
            "If no answer is present, reply: Not found in the document.\n\n"
            f"{synthesis_context}\n\nFinal Answer:"
        )

    if len(synth_prompt) > SAFE_PROMPT_LIMIT:
        keep = max(500, SAFE_PROMPT_LIMIT - 300)
        synthesis_context = _safe_truncate(synthesis_context, keep)
        synth_prompt = synth_prompt.replace(synthesis_context, synthesis_context)

    final = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You synthesize multiple text excerpts into a single faithful answer."},
            {"role": "user", "content": synth_prompt},
        ],
        temperature=0.1,
        max_tokens=500,
    )
    return final.choices[0].message.content.strip()