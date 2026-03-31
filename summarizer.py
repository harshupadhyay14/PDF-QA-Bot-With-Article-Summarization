# summarizer.py
import os
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = "llama-3.1-8b-instant"

_client = None

def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _client = Groq(api_key=api_key)
    return _client


def fetch_article_text(url: str, timeout: int = 15) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    candidates = []
    for sel in ["article", "main", "div#content", "div.post", "div.article"]:
        node = soup.select_one(sel)
        if node:
            candidates = node.find_all("p")
            if candidates:
                break
    if not candidates:
        candidates = soup.find_all("p")

    text = "\n".join(p.get_text(strip=True) for p in candidates)
    text = "\n".join(line for line in text.splitlines() if line)
    return text.strip()


def summarize_text(long_text: str) -> str:
    if not long_text or len(long_text.split()) < 40:
        return "Text too short to summarize."

    # Truncate to ~6000 chars to stay within Groq context limits
    if len(long_text) > 6000:
        long_text = long_text[:6000].rsplit(".", 1)[0] + "."

    client = _get_client()

    prompt = (
        "Please provide a clear and concise summary of the following article in 3-5 sentences. "
        "Focus on the main points and key takeaways.\n\n"
        f"Article:\n{long_text}\n\nSummary:"
    )

    resp = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that summarizes articles clearly and concisely."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400,
    )
    return resp.choices[0].message.content.strip()