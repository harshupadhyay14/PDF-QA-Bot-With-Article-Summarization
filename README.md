# 🧠 DocMind — PDF Q&A & Article Summarizer

> An AI-powered web app to ask questions from documents and summarize articles — built with Flask, Groq API, and LLaMA 3.

![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-black?style=flat-square&logo=flask)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203-orange?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

![alt text](<Screenshot 2026-03-31 110333.png>)
![alt text](<Screenshot 2026-03-31 110357.png>)
![alt text](<Screenshot 2026-03-31 110612.png>)

---

## ✨ Features

- 📄 **Multi-file Document Q&A** — Upload multiple PDFs or DOCX files and ask questions across all of them
- 🌐 **Article Summarizer** — Paste any article URL and get a concise 3–5 sentence summary
- 🕐 **Session History** — All Q&A and summaries are saved during your session
- 📥 **Export as PDF** — Download your entire session as a formatted PDF report
- 🖱️ **Drag & Drop** — Drag files directly onto the upload zone
- 📋 **Copy to Clipboard** — One-click copy for answers and summaries
- 🎨 **Dark UI** — Clean, modern dark interface

---

## 🖼️ Demo

![DocMind Screenshot](https://raw.githubusercontent.com/harshupadhyay14/PDF-QA-Bot-With-Article-Summarization/main/static/demo.png)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask |
| AI / LLM | Groq API — LLaMA 3.3 70B Versatile (Q&A), LLaMA 3.1 8B Instant (Summarization) |
| PDF Parsing | PyMuPDF, PyPDF2 |
| DOCX Parsing | python-docx |
| PDF Export | ReportLab |
| Web Scraping | BeautifulSoup4, Requests |
| Frontend | HTML, CSS, Vanilla JS |

---

## 📁 Project Structure

```
PDF_QA_BOT/
├── templates/
│   └── index.html          ← Jinja2 HTML template
├── static/
│   ├── css/style.css       ← Stylesheet
│   └── js/script.js        ← Frontend logic
├── uploads/                ← Temp uploaded files
├── main.py                 ← Flask app & all routes
├── pdf_qa.py               ← Groq LLM Q&A logic
├── summarizer.py           ← Groq summarization logic
├── .env                    ← API keys (never commit!)
├── requirements.txt
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/harshupadhyay14/PDF-QA-Bot-With-Article-Summarization.git
cd PDF-QA-Bot-With-Article-Summarization
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install flask groq pymupdf pypdf2 python-docx python-dotenv requests beautifulsoup4 reportlab
```

### 4. Add your Groq API key

Create a `.env` file in the project root:

```
GROQ_API_KEY=gsk_your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card required.

### 5. Run the app

```bash
python main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🤖 Models Used

| Feature | Model | Provider |
|---------|-------|----------|
| Document Q&A | `llama-3.3-70b-versatile` | Groq |
| Article Summarization | `llama-3.1-8b-instant` | Groq |

---

## 💡 How It Works

### Document Q&A
1. User uploads one or more PDF/DOCX files
2. Text is extracted using PyMuPDF (with smart front-matter skipping)
3. Text is split into overlapping windows and scored for relevance to the question
4. Top chunks are sent to Groq's LLaMA 3.3 70B model
5. A synthesis pass combines partial answers into a final response

### Article Summarization
1. User pastes an article URL
2. BeautifulSoup scrapes the article text
3. Text is sent to Groq's LLaMA 3.1 8B Instant model
4. A clean 3–5 sentence summary is returned

---

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | Your Groq API key (required) |
| `SECRET_KEY` | `docmind-secret-2024` | Flask session secret key |
| `PORT` | `5000` | Port to run the app on |

---

## 📝 Notes

- Max file upload size: **64 MB**
- Groq API free tier has generous rate limits
- Session history is stored in the Flask session (cleared on server restart)
- The `.env` file is gitignored — never commit your API key

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first.

---

## 📄 License

MIT License — feel free to use this project for learning or your portfolio.

---

Made with ❤️ by [Harsh Upadhyay](https://github.com/harshupadhyay14)
