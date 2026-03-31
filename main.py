# main.py
import os
import tempfile
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from dotenv import load_dotenv
import docx
from PyPDF2 import PdfReader

load_dotenv()

from pdf_qa import ask_groq
from summarizer import fetch_article_text, summarize_text

try:
    import fitz
    PYMUPDF = True
except Exception:
    PYMUPDF = False

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "docmind-secret-2024")
app.config["UPLOAD_FOLDER"] = tempfile.gettempdir()
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

ALLOWED = {".pdf", ".docx"}

# -----------------------
# Text extractors
# -----------------------
def _looks_like_front_matter(text):
    t = (text or "").lower()
    indicators = ["in praise","foreword","preface","table of contents","contents",
                  "acknowledgments","about the author","copyright","isbn","www.","ebooksworld","morgan kaufmann"]
    return sum(1 for k in indicators if k in t) >= 2

def extract_text_from_pdf_smart(path, max_chars=80000, starts=(0,10,20,30,40,50,60)):
    def _extract_from_page(start_page):
        if PYMUPDF:
            out = []
            with fitz.open(path) as doc:
                for i, page in enumerate(doc):
                    if i < start_page: continue
                    out.append(page.get_text() or "")
                    if sum(len(x) for x in out) >= max_chars: break
            return "\n".join(out).strip()
        out = []
        with open(path, "rb") as f:
            reader = PdfReader(f)
            for i, pg in enumerate(reader.pages):
                if i < start_page: continue
                out.append(pg.extract_text() or "")
                if sum(len(x) for x in out) >= max_chars: break
        return "\n".join(out).strip()

    best = ""
    for start in starts:
        if not isinstance(start, int): continue
        cand = _extract_from_page(start)
        if not cand: continue
        if not _looks_like_front_matter(cand): return cand
        if len(cand) > len(best): best = cand
    return best

def extract_text_from_docx(path):
    d = docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs).strip()

def find_section_start_page(path, patterns, scan_pages=120):
    try:
        if PYMUPDF:
            with fitz.open(path) as doc:
                for i in range(min(len(doc), scan_pages)):
                    txt = (doc[i].get_text() or "").lower()
                    for pat in patterns:
                        if re.search(pat, txt): return i
        else:
            with open(path, "rb") as f:
                reader = PdfReader(f)
                for i in range(min(len(reader.pages), scan_pages)):
                    txt = (reader.pages[i].extract_text() or "").lower()
                    for pat in patterns:
                        if re.search(pat, txt): return i
    except Exception:
        return None
    return None

def extract_text_from_page_set(path, page_indices, spread=1, max_chars=80000):
    if not page_indices: return ""
    wanted = set()
    for p in page_indices:
        for d in range(-spread, spread+1):
            if p+d >= 0: wanted.add(p+d)
    out, total = [], 0
    try:
        if PYMUPDF:
            with fitz.open(path) as doc:
                for i in sorted(wanted):
                    if i >= len(doc): continue
                    t = doc[i].get_text() or ""
                    out.append(t); total += len(t)
                    if total >= max_chars: break
        else:
            with open(path, "rb") as f:
                reader = PdfReader(f)
                for i in sorted(wanted):
                    if i >= len(reader.pages): continue
                    t = reader.pages[i].extract_text() or ""
                    out.append(t); total += len(t)
                    if total >= max_chars: break
    except Exception:
        pass
    return "\n".join(out).strip()

def rank_pages_for_term(path, term, scan_pages=None):
    t = (term or "").strip()
    if not t: return []
    t_low, t_upp = t.lower(), t.upper()
    patt_defs = [
        rf"\b{re.escape(t_low)}\s+is\b", rf"\b{re.escape(t_low)}\s+are\b",
        rf"\bdefinition\s+of\s+{re.escape(t_low)}\b",
        rf"\b{re.escape(t_low)}[^\n]{{0,40}}\bdefined\s+as\b",
        rf"^\s*{re.escape(t_low)}s?\s*$", rf"^\s*{re.escape(t_low)}\s*:"
    ]
    rx_defs = [re.compile(p, re.IGNORECASE|re.MULTILINE) for p in patt_defs]
    rx_term = re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE)
    rx_bad  = [re.compile(rf"\b{re.escape(t_upp)}\s*\["), re.compile(rf"\b{re.escape(t_upp)}\s*=")]
    pages_scores = []
    try:
        if PYMUPDF:
            with fitz.open(path) as doc:
                total = len(doc) if scan_pages is None else min(len(doc), scan_pages)
                for i in range(total):
                    txt = doc[i].get_text() or ""
                    if not rx_term.search(txt): continue
                    score = sum(len(list(r.finditer(txt)))*8 for r in rx_defs)
                    score += len(list(rx_term.finditer(txt)))*2
                    score -= sum(len(list(r.finditer(txt)))*6 for r in rx_bad)
                    pages_scores.append((i, max(score,0)))
        else:
            with open(path,"rb") as f:
                reader = PdfReader(f)
                total = len(reader.pages) if scan_pages is None else min(len(reader.pages), scan_pages)
                for i in range(total):
                    txt = reader.pages[i].extract_text() or ""
                    if not rx_term.search(txt): continue
                    score = sum(len(list(r.finditer(txt)))*8 for r in rx_defs)
                    score += len(list(rx_term.finditer(txt)))*2
                    score -= sum(len(list(r.finditer(txt)))*6 for r in rx_bad)
                    pages_scores.append((i, max(score,0)))
    except Exception:
        return []
    pages_scores.sort(key=lambda x: x[1], reverse=True)
    return pages_scores

# -----------------------
# Routes
# -----------------------
@app.route("/")
def index():
    if "history" not in session:
        session["history"] = []
    return render_template("index.html")

@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(e):
    return jsonify({"error": "File too large (max 64 MB)."}), 413

@app.route("/qa", methods=["POST"])
def qa():
    try:
        files = request.files.getlist("files")
        question = (request.form.get("question") or "").strip()
        if not files or not question:
            return jsonify({"error": "Please provide files and a question."}), 400

        all_texts = []
        file_names = []
        for file in files:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in ALLOWED:
                continue
            filename = secure_filename(file.filename)
            path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(path)
            file_names.append(file.filename)

            if ext == ".pdf":
                ql = question.lower()
                patterns = []
                if "application" in ql:
                    patterns += [r"\bapplications?\b"]
                if "layer" in ql or "protocol" in ql:
                    patterns += [r"\blayered\b", r"protocol layers?"]
                if "architecture" in ql or "internet" in ql:
                    patterns += [r"internet architecture"]
                m = re.match(r"\s*(what\s+is|define)\s+([a-zA-Z0-9 _-]+?)\?*$", ql)
                if m:
                    term = m.group(2).strip().rstrip('.')
                    if 1 <= len(term) <= 60:
                        tpat = re.escape(term)
                        patterns += [rf"^\s*{tpat}s?\s*$", rf"\b{tpat}\b"]
                start_hint = find_section_start_page(path, patterns, scan_pages=200) if patterns else None
                starts = (start_hint,) if isinstance(start_hint, int) else tuple()
                starts += (0, 10, 20, 30, 40, 50, 60)
                text = extract_text_from_pdf_smart(path, max_chars=80000, starts=starts)
            else:
                text = extract_text_from_docx(path)

            if text:
                all_texts.append(f"[From: {file.filename}]\n{text}")

        if not all_texts:
            return jsonify({"error": "Could not extract text from uploaded files."}), 400

        combined_text = "\n\n---\n\n".join(all_texts)
        answer = ask_groq(question, combined_text)

        # Save to session history
        history = session.get("history", [])
        history.append({
            "type": "qa",
            "question": question,
            "answer": answer,
            "files": file_names,
            "timestamp": datetime.now().strftime("%H:%M")
        })
        session["history"] = history[-50:]  # keep last 50
        session.modified = True

        return jsonify({"answer": answer, "history": session["history"]})
    except Exception as e:
        print("ERROR /qa:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/summarize", methods=["POST"])
def summarize():
    try:
        data = request.get_json(force=True, silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "URL is required"}), 400

        article_text = fetch_article_text(url)
        if not article_text or len(article_text.split()) < 40:
            return jsonify({"error": "Could not fetch enough text to summarize."}), 400

        summary = summarize_text(article_text)

        history = session.get("history", [])
        history.append({
            "type": "summary",
            "url": url,
            "summary": summary,
            "timestamp": datetime.now().strftime("%H:%M")
        })
        session["history"] = history[-50:]
        session.modified = True

        return jsonify({"summary": summary, "history": session["history"]})
    except Exception as e:
        print("ERROR /summarize:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET"])
def get_history():
    return jsonify(session.get("history", []))

@app.route("/history/clear", methods=["POST"])
def clear_history():
    session["history"] = []
    session.modified = True
    return jsonify({"ok": True})

@app.route("/export-pdf", methods=["POST"])
def export_pdf():
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        import io

        data = request.get_json(force=True, silent=True) or {}
        history = data.get("history", [])

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("Title", parent=styles["Heading1"],
                                     fontSize=20, textColor=colors.HexColor("#7c6af7"),
                                     spaceAfter=6, alignment=TA_CENTER)
        sub_style   = ParagraphStyle("Sub", parent=styles["Normal"],
                                     fontSize=9, textColor=colors.HexColor("#6b7280"),
                                     spaceAfter=16, alignment=TA_CENTER)
        label_style = ParagraphStyle("Label", parent=styles["Normal"],
                                     fontSize=8, textColor=colors.HexColor("#7c6af7"),
                                     fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)
        q_style     = ParagraphStyle("Q", parent=styles["Normal"],
                                     fontSize=10, textColor=colors.HexColor("#1e1e2e"),
                                     fontName="Helvetica-Bold", spaceAfter=4)
        a_style     = ParagraphStyle("A", parent=styles["Normal"],
                                     fontSize=10, textColor=colors.HexColor("#111118"),
                                     leading=15, spaceAfter=8)
        time_style  = ParagraphStyle("Time", parent=styles["Normal"],
                                     fontSize=8, textColor=colors.HexColor("#9ca3af"), spaceAfter=12)

        story = []
        story.append(Paragraph("DocMind — Session Export", title_style))
        story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}", sub_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))
        story.append(Spacer(1, 0.4*cm))

        if not history:
            story.append(Paragraph("No history to export.", a_style))
        else:
            for i, item in enumerate(history, 1):
                ts = item.get("timestamp", "")
                if item.get("type") == "qa":
                    files = ", ".join(item.get("files", []))
                    story.append(Paragraph(f"Q&A #{i}", label_style))
                    if files:
                        story.append(Paragraph(f"📄 {files}", time_style))
                    story.append(Paragraph(f"Q: {item.get('question','')}", q_style))
                    story.append(Paragraph(item.get("answer","").replace("\n","<br/>"), a_style))
                    if ts:
                        story.append(Paragraph(f"🕐 {ts}", time_style))
                else:
                    story.append(Paragraph(f"Summary #{i}", label_style))
                    story.append(Paragraph(f"🌐 {item.get('url','')}", time_style))
                    story.append(Paragraph(item.get("summary","").replace("\n","<br/>"), a_style))
                    if ts:
                        story.append(Paragraph(f"🕐 {ts}", time_style))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#f3f4f6")))
                story.append(Spacer(1, 0.3*cm))

        doc.build(story)
        buf.seek(0)

        from flask import send_file
        return send_file(buf, mimetype="application/pdf",
                         as_attachment=True,
                         download_name=f"docmind-export-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf")
    except ImportError:
        return jsonify({"error": "reportlab not installed. Run: pip install reportlab"}), 500
    except Exception as e:
        print("ERROR /export-pdf:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set in your environment/.env")
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=True, host="127.0.0.1", port=port)