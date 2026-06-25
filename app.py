from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import re
from datetime import datetime
from urllib.parse import quote_plus
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ============================================================
#  ADD YOUR API KEYS HERE
#  GROQ_API_KEY   → https://console.groq.com  (FREE, no card, works in India)
#  NEWS_API_KEY   → https://newsapi.org        (optional, free)
#  GOOGLE_API_KEY → Google Custom Search       (optional)
#  SEARCH_ENGINE_ID→ Google Custom Search CX   (optional)
#

# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

GROQ_MODEL        = "llama-3.3-70b-versatile"   # text model
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # vision model — supports images
GROQ_API_URL      = "https://api.groq.com/openai/v1/chat/completions"

TODAY = datetime.now()
cache = {}

MONTHS = ["january","february","march","april","may","june",
          "july","august","september","october","november","december"]

# ─────────────────────────────────────────────
#  DEATH / OBITUARY CLAIM DETECTION
#  Detects if the claim is about someone dying.
#  Triggers a targeted search + stronger prompt.
# ─────────────────────────────────────────────
DEATH_KEYWORDS = [
    "died", "dead", "passed away", "no more", "demise", "death",
    "killed", "deceased", "passed on", "lost his life", "lost her life",
    "funeral", "obituary", "rip", "rest in peace", "no longer with us",
    "is no more", "has died", "have died", "has passed", "have passed"
]

def detect_death_claim(text):
    """Returns (is_death_claim: bool, person_name: str|None)"""
    tl = text.lower()
    if not any(kw in tl for kw in DEATH_KEYWORDS):
        return False, None
    # Extract likely person name = capitalised words before the death keyword
    words = text.split()
    name_words = []
    stop = {"the","a","an","this","that","he","she","they","it",
            "on","in","at","of","and","or","is","was","has","have"}
    for w in words:
        clean = w.strip(".,!?")
        if clean and clean[0].isupper() and clean.lower() not in stop:
            name_words.append(clean)
        if len(name_words) >= 4:
            break
    person = " ".join(name_words) if name_words else None
    return True, person

# ─────────────────────────────────────────────
#  SERVER-SIDE STATS
# ─────────────────────────────────────────────
server_stats = {"total": 0, "real": 0, "fake": 0, "unc": 0}

def record_verdict(verdict):
    server_stats["total"] += 1
    if verdict == "REAL":   server_stats["real"] += 1
    elif verdict == "FAKE": server_stats["fake"] += 1
    else:                   server_stats["unc"]  += 1

# ─────────────────────────────────────────────
#  DEBUG ENDPOINT  →  GET /debug-keys
# ─────────────────────────────────────────────
@app.route("/debug-keys")
def debug_keys():
    def status(val, placeholder):
        if not val or val == placeholder: return "NOT SET (still placeholder)"
        if len(val) < 8:                  return "Too short — likely wrong"
        return f"SET (first 6 chars: {val[:6]}...)"
    return jsonify({
        "GROQ_API_KEY":     status(GROQ_API_KEY,     "your_groq_api_key"),
        "NEWS_API_KEY":     status(NEWS_API_KEY,      "your_news_api_key"),
        "GOOGLE_API_KEY":   status(GOOGLE_API_KEY,    "your_google_api_key"),
        "SEARCH_ENGINE_ID": status(SEARCH_ENGINE_ID,  "your_search_engine_id"),
        "DuckDuckGo":       "ALWAYS ON — no key needed",
        "TODAY":            TODAY.strftime("%d %B %Y")
    })

# ─────────────────────────────────────────────
#  STATS ENDPOINTS
# ─────────────────────────────────────────────
@app.route("/stats")
def get_stats():
    return jsonify(server_stats)

@app.route("/stats/reset", methods=["POST"])
def reset_stats():
    for k in server_stats: server_stats[k] = 0
    return jsonify({"ok": True})

# ─────────────────────────────────────────────
#  DATE EXTRACTION
# ─────────────────────────────────────────────
def extract_date(text):
    tl = text.lower()
    p1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})\b', tl)
    if p1:
        try: return datetime(int(p1.group(3)), MONTHS.index(p1.group(2))+1, int(p1.group(1)))
        except: pass
    p2 = re.search(r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b', tl)
    if p2:
        try: return datetime(int(p2.group(3)), MONTHS.index(p2.group(1))+1, int(p2.group(2)))
        except: pass
    p3 = re.search(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b', text)
    if p3:
        try: return datetime(int(p3.group(3)), int(p3.group(2)), int(p3.group(1)))
        except: pass
    p4 = re.search(r'\bin\s+((?:19|20)\d{2})\b', text, re.IGNORECASE) or re.search(r'\b((?:19|20)\d{2})\b', text)
    if p4:
        y = int(p4.group(1))
        if 1900 <= y <= 2100: return datetime(y, 1, 1)
    return None

# ─────────────────────────────────────────────
#  DUCKDUCKGO SEARCH — no API key needed!
#  Pass extra_query for death/targeted searches
# ─────────────────────────────────────────────
def check_duckduckgo(query, extra_query=None):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        # Use targeted query if provided (e.g. "Asha Bhosle died obituary")
        search_q = extra_query if extra_query else query

        # DuckDuckGo instant answer API
        url = f"https://api.duckduckgo.com/?q={quote_plus(search_q)}&format=json&no_redirect=1&no_html=1&skip_disambig=1"
        res = requests.get(url, headers=headers, timeout=8).json()
        results = []

        if res.get("AbstractText"):
            results.append({
                "title":   res.get("Heading", "DuckDuckGo Result"),
                "snippet": res["AbstractText"][:300],
                "source":  res.get("AbstractSource", "DuckDuckGo")
            })

        for topic in res.get("RelatedTopics", [])[:4]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title":   topic.get("Text","")[:100],
                    "snippet": topic.get("Text","")[:200],
                    "source":  "DuckDuckGo"
                })

        # HTML scrape for recent news
        html_url = f"https://html.duckduckgo.com/html/?q={quote_plus(search_q + ' news')}"
        html_res  = requests.get(html_url, headers=headers, timeout=8)
        html_text = html_res.text

        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html_text, re.DOTALL)
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>',       html_text, re.DOTALL)

        for t, s in zip(titles[:6], snippets[:6]):
            clean_t = re.sub(r'<[^>]+>', '', t).strip()
            clean_s = re.sub(r'<[^>]+>', '', s).strip()
            if clean_t and clean_s:
                results.append({"title": clean_t, "snippet": clean_s, "source": "DuckDuckGo Web"})

        return {"found": len(results) > 0, "results": results[:8]}
    except Exception as e:
        return {"found": False, "results": [], "error": str(e)}

# ─────────────────────────────────────────────
#  NEWSAPI  (optional)
# ─────────────────────────────────────────────
def check_news(query):
    if not NEWS_API_KEY or NEWS_API_KEY == "your_news_api_key":
        return None
    try:
        url = f"https://newsapi.org/v2/everything?q={quote_plus(query[:80])}&apiKey={NEWS_API_KEY}&pageSize=5&sortBy=relevancy&language=en"
        res = requests.get(url, timeout=8).json()
        if res.get("status") == "error":
            return {"found": False, "articles": [], "error": res.get("message")}
        articles = res.get("articles", [])
        return {"found": len(articles) > 0, "articles": articles}
    except Exception as e:
        return {"found": False, "articles": [], "error": str(e)}

# ─────────────────────────────────────────────
#  GOOGLE CUSTOM SEARCH  (optional)
# ─────────────────────────────────────────────
def check_google(query):
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "your_google_api_key":
        return None
    try:
        url    = "https://www.googleapis.com/customsearch/v1"
        params = {"key": GOOGLE_API_KEY, "cx": SEARCH_ENGINE_ID, "q": query[:120], "num": 5}
        res    = requests.get(url, params=params, timeout=8).json()
        if "error" in res:
            return {"found": False, "items": [], "error": res["error"]["message"]}
        items = res.get("items", [])
        return {"found": len(items) > 0, "items": items}
    except Exception as e:
        return {"found": False, "items": [], "error": str(e)}

# ─────────────────────────────────────────────
#  GROQ — Text fact-check
# ─────────────────────────────────────────────
def call_groq(messages):
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key":
        raise ValueError("Groq API key not configured. Open app.py and add your key from https://console.groq.com")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    body    = {"model": GROQ_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 900}
    resp    = requests.post(GROQ_API_URL, headers=headers, json=body, timeout=30)
    res     = resp.json()
    if "error" in res:
        code = res['error'].get('code') or res['error'].get('type', 'unknown')
        raise ValueError(f"Groq error ({code}): {res['error'].get('message','Unknown error')}")
    return res["choices"][0]["message"]["content"]

# ─────────────────────────────────────────────
#  GROQ — Image analysis (context-based)
# ─────────────────────────────────────────────
def call_groq_image(mime_type, context="", b64_image=""):
    """
    Sends the actual image to Groq LLaMA 4 Scout vision model.
    Analyzes pixels, lighting, artifacts, deepfakes, manipulations.
    Also considers the context claim text if provided.
    """
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key":
        raise ValueError("Groq API key not configured. Get it free from https://console.groq.com")

    # Build death context note if applicable
    is_death, person = detect_death_claim(context) if context else (False, None)
    death_note = ""
    if is_death and person:
        death_note = (
            f"\n\nIMPORTANT: This image claims to show the death/funeral of '{person}'. "
            "Check: Does the image match a real funeral or death scene? "
            "Is there anything inconsistent or fabricated?"
        )

    ctx_line = f'Context claim: "{context}"' if context else "No context provided."

    prompt = (
        "You are an expert image forensics analyst and fact-checker. "
        "Carefully analyze this image for:\n"
        "1. Signs of manipulation — inconsistent lighting, shadows, edges, or blending\n"
        "2. AI-generated or deepfake indicators — unnatural skin, hair, backgrounds\n"
        "3. Cloning artifacts — repeated patterns or copy-pasted regions\n"
        "4. Metadata mismatches — image quality inconsistent with claimed date/location\n"
        "5. Misleading context — real image used out of context or mislabelled\n"
        "6. Whether the scene matches the claimed event (if context given)\n"
        f"\n{ctx_line}{death_note}\n\n"
        "Based on BOTH the visual analysis AND the context claim, give a verdict:\n"
        "- REAL: image appears genuine and context matches\n"
        "- FAKE: image is manipulated, AI-generated, or context is misleading/false\n"
        "- UNCERTAIN: cannot confidently determine authenticity\n\n"
        "Return ONLY valid JSON, no markdown, no extra text:\n"
        '{"verdict":"REAL" or "FAKE" or "UNCERTAIN","confidence":number 0-100,' 
        '"reason":"one sentence max 20 words summarising the key finding",'
        '"explanation":"3-4 sentences with specific visual observations — mention what you see",'
        '"signals":[{"type":"green" or "red" or "yellow","text":"short label max 4 words"}]}'
    )

    # Build message with actual image content
    user_content = []
    if b64_image:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}
        })
    user_content.append({"type": "text", "text": prompt})

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"}
    body = {
        "model": GROQ_VISION_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert image forensics analyst. Return only valid JSON, no markdown, no code blocks."},
            {"role": "user",   "content": user_content}
        ],
        "temperature": 0.2,
        "max_tokens": 900
    }
    resp = requests.post(GROQ_API_URL, headers=headers, json=body, timeout=40)
    res  = resp.json()
    if "error" in res:
        code = res["error"].get("code") or res["error"].get("type", "unknown")
        raise ValueError(f"Groq vision error ({code}): {res['error'].get('message','Unknown')}")
    return res["choices"][0]["message"]["content"]

# ─────────────────────────────────────────────
#  BUILD PROMPT WITH ALL EVIDENCE
# ─────────────────────────────────────────────
def build_prompt(text, det_date, ddg_res, news_res, google_res):
    # ── Date context ──
    date_ctx = ""
    if det_date:
        diff_days = (det_date - TODAY).days
        if diff_days < -3:
            ago     = (TODAY - det_date).days
            ago_str = f"{ago} days ago" if ago < 365 else f"{ago//365} year(s) ago"
            date_ctx = (
                f"\n\n=== DATE DETECTED ===\n"
                f"The claim contains the date: {det_date.strftime('%d %B %Y')} ({ago_str}).\n"
                f"Today is {TODAY.strftime('%d %B %Y')}.\n"
                "This is a PAST date. Determine if this event ACTUALLY happened:\n"
                "- If YES (confirmed by web search, news, or your knowledge) → REAL, confidence 80-95\n"
                "- If NO (impossible, never happened, contradicts history/science) → FAKE, confidence 85-98\n"
            )
        elif diff_days > 3:
            date_ctx = (
                f"\n\n=== DATE DETECTED ===\n"
                f"The claim contains a FUTURE date: {det_date.strftime('%d %B %Y')}.\n"
                "Cannot verify if this will happen. Mark UNCERTAIN unless it contradicts a known fact.\n"
            )

    # ── DuckDuckGo results ──
    ddg_ctx = ""
    if ddg_res and ddg_res.get("found") and ddg_res.get("results"):
        items   = ddg_res["results"][:8]
        ddg_ctx = f"\n=== LIVE WEB SEARCH — DuckDuckGo ({len(items)} results) ===\n"
        ddg_ctx += "These are REAL-TIME web results — prioritize over training data for recent events!\n"
        for r in items:
            ddg_ctx += f'- [{r["source"]}] {r["title"]}: {r["snippet"][:150]}\n'
        ddg_ctx += "\nIf these web results confirm the claim → REAL. If they contradict it → FAKE.\n"
    else:
        ddg_ctx = "\n=== LIVE WEB SEARCH: No results found ===\n"

    # ── NewsAPI ──
    news_ctx = ""
    if news_res and news_res.get("found") and news_res.get("articles"):
        arts     = news_res["articles"][:4]
        news_ctx = f"\n=== NEWSAPI ({len(arts)} articles found) ===\n"
        for a in arts:
            src       = a.get("source", {}).get("name", "")
            pub       = (a.get("publishedAt") or "")[:10]
            news_ctx += f'- "{a["title"]}" ({src}, {pub})\n'
        news_ctx += "If these corroborate the claim → more REAL. If they contradict → more FAKE.\n"

    # ── Google ──
    google_ctx = ""
    if google_res and google_res.get("found") and google_res.get("items"):
        items      = google_res["items"][:4]
        google_ctx = f"\n=== GOOGLE SEARCH ({len(items)} results) ===\n"
        for i in items:
            google_ctx += f'- "{i["title"]}" — {i.get("snippet","")[:100]}\n'

    # ── Death claim special rules ──
    is_death, person_name = detect_death_claim(text)
    death_rule = ""
    if is_death:
        death_rule = (
            "\n\n=== DEATH / OBITUARY CLAIM DETECTED ===\n"
            f"Person mentioned: {person_name or 'unknown'}.\n"
            "DEATH VERIFICATION RULES — highest priority, override everything else:\n"
            "1. If web search results contain words like 'died', 'passed away', 'death', "
            "'obituary', 'funeral', 'no longer with us' about this person "
            "→ verdict MUST be REAL, confidence 90-97.\n"
            "2. If web results show the person is still alive, active, or posting recently "
            "→ verdict MUST be FAKE for this death claim, confidence 88-96.\n"
            "3. If web search returns nothing about this person at all "
            "→ verdict UNCERTAIN, confidence 45.\n"
            "4. Name spelling variations are allowed — 'Bholse' and 'Bhosle' are the same person.\n"
            "5. NEVER mark a confirmed real death as FAKE.\n"
            "6. NEVER mark a living person's death as REAL.\n"
        )

    # ── System message ──
    system_msg = (
        f"You are a professional real-world fact-checker with access to live web search results.\n"
        f"Today's date is {TODAY.strftime('%d %B %Y')}.\n\n"
        "CRITICAL RULES:\n"
        "1. ALWAYS trust live web search results over your training data for recent events.\n"
        "2. Your training data has a cutoff — for 2024 onwards, web results are ground truth.\n"
        "3. Web results confirm claim → verdict REAL, high confidence.\n"
        "4. Web results contradict claim → verdict FAKE, high confidence.\n"
        "5. Ambiguous or no web results → use your knowledge, lean UNCERTAIN.\n"
        "6. Never mark something FAKE just because it is recent or unfamiliar.\n"
        + death_rule +
        "\nReturn ONLY valid JSON with no markdown, no code blocks, no extra text:\n"
        '{"verdict":"REAL" or "FAKE" or "UNCERTAIN","confidence":number 0-100,'
        '"reason":"one sentence max 20 words citing key evidence",'
        '"explanation":"2-3 sentences explaining exactly why, referencing specific web evidence",'
        '"signals":[{"type":"green" or "red" or "yellow","text":"label max 4 words"}]}'
    )

    user_msg = f'Fact-check this claim:\n\n"{text}"{date_ctx}{ddg_ctx}{news_ctx}{google_ctx}'
    return [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_msg}
    ]

# ─────────────────────────────────────────────
#  ROUTES — pages
# ─────────────────────────────────────────────
@app.route("/")
def dashboard(): return render_template("dashboard.html")

@app.route("/text")
def text_page(): return render_template("text.html")

@app.route("/image")
def image_page(): return render_template("image.html")

@app.route("/url")
def url_page(): return render_template("url.html")

@app.route("/analytics")
def analytics_page(): return render_template("analytics.html")

# ─────────────────────────────────────────────
#  API — /analyze  (text + URL)
# ─────────────────────────────────────────────
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    cache_key = text[:80]
    if cache_key in cache:
        return jsonify(cache[cache_key])

    try:
        det_date = extract_date(text)

        # Hard FAKE rules — instant verdict, no API call needed
        hard_fakes = [
            ("humans can breathe in space",  "Humans cannot breathe in space — no oxygen"),
            ("capital of india is mumbai",    "The capital of India is New Delhi, not Mumbai"),
            ("capital of india is kolkata",   "The capital of India is New Delhi, not Kolkata"),
            ("capital of usa is new york",    "The capital of the USA is Washington D.C."),
            ("sun revolves around earth",     "The Earth revolves around the Sun, not vice versa"),
            ("time travel invented",          "Time travel has not been invented"),
            ("aliens landed",                 "No verified alien landing has ever occurred"),
            ("live without food forever",     "Humans cannot survive without food"),
            ("free energy machine",           "Free energy machines violate laws of thermodynamics"),
        ]
        for rule, reason in hard_fakes:
            if rule in text.lower():
                result = {
                    "verdict": "FAKE", "confidence": 97, "reason": reason,
                    "explanation": "This claim violates established scientific or geographical facts.",
                    "signals": [{"type": "red", "text": "Known false fact"}],
                    "date_info": None, "news_articles": [], "google_items": [], "ddg_results": []
                }
                cache[cache_key] = result
                record_verdict("FAKE")
                return jsonify(result)

        # Far-future date — skip API
        if det_date:
            diff = (det_date - TODAY).days
            if diff > 30:
                result = {
                    "verdict": "UNCERTAIN", "confidence": 60,
                    "reason": f"Claim refers to a future date ({det_date.strftime('%d %b %Y')})",
                    "explanation": "Future events cannot be verified. The claim may or may not come true.",
                    "signals": [{"type": "yellow", "text": "Future date"}],
                    "date_info": {"date": det_date.strftime("%d %B %Y"), "type": "future"},
                    "news_articles": [], "google_items": [], "ddg_results": []
                }
                cache[cache_key] = result
                record_verdict("UNCERTAIN")
                return jsonify(result)

        # Detect death claim → run targeted search
        is_death_claim, person = detect_death_claim(text)
        extra_q = f"{person} died death obituary" if (is_death_claim and person) else None

        # Run all search sources
        ddg_res    = check_duckduckgo(text, extra_query=extra_q)  # targeted if death claim
        news_res   = check_news(extra_q or text)                  # optional
        google_res = check_google(extra_q or text)                # optional

        messages = build_prompt(text, det_date, ddg_res, news_res, google_res)
        raw      = call_groq(messages)
        clean    = raw.replace("```json", "").replace("```", "").strip()
        parsed   = json.loads(clean)

        result = {
            "verdict":     parsed.get("verdict", "UNCERTAIN"),
            "confidence":  parsed.get("confidence", 50),
            "reason":      parsed.get("reason", ""),
            "explanation": parsed.get("explanation", ""),
            "signals":     parsed.get("signals", []),
            "date_info": {
                "date": det_date.strftime("%d %B %Y"),
                "type": "past" if (det_date - TODAY).days < 0 else "future"
            } if det_date else None,
            "news_articles": (news_res  or {}).get("articles", [])[:4],
            "google_items":  (google_res or {}).get("items",    [])[:4],
            "ddg_results":   (ddg_res   or {}).get("results",   [])[:4],
        }
        cache[cache_key] = result
        record_verdict(result["verdict"])
        return jsonify(result)

    except Exception as e:
        error_msg = str(e)
        return jsonify({
            "error":       f"Analysis failed: {error_msg}",
            "verdict":     "UNCERTAIN", "confidence": 0,
            "reason":      "Backend error — see explanation",
            "explanation": error_msg,
            "signals":     [{"type": "red", "text": "API error"}],
            "date_info":   None, "news_articles": [], "google_items": [], "ddg_results": []
        })

# ─────────────────────────────────────────────
#  API — /analyze-image
# ─────────────────────────────────────────────
@app.route("/analyze-image", methods=["POST"])
def analyze_image():
    try:
        data    = request.json or {}
        b64     = data.get("image", "")
        mime    = data.get("mime_type", "image/jpeg")
        context = data.get("context", "")
        if not b64:
            return jsonify({"error": "No image data"}), 400

        det_date = extract_date(context) if context else None

        # If context mentions a person dying, run targeted DDG search
        is_death_claim, person = detect_death_claim(context) if context else (False, None)
        extra_q = f"{person} died death obituary" if (is_death_claim and person) else None
        ddg_res = check_duckduckgo(context, extra_query=extra_q) if context else {"found": False, "results": []}

        raw    = call_groq_image(mime, context, b64_image=b64)
        clean  = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)

        parsed["date_info"] = {
            "date": det_date.strftime("%d %B %Y"),
            "type": "past" if (det_date - TODAY).days < 0 else "future"
        } if det_date else None
        parsed["news_articles"] = []
        parsed["google_items"]  = []
        parsed["ddg_results"]   = (ddg_res or {}).get("results", [])[:4]
        record_verdict(parsed.get("verdict", "UNCERTAIN"))
        return jsonify(parsed)

    except Exception as e:
        error_msg = str(e)
        return jsonify({
            "error":       f"Image analysis failed: {error_msg}",
            "verdict":     "UNCERTAIN", "confidence": 0,
            "reason":      "Backend error — see explanation",
            "explanation": error_msg,
            "signals":     [{"type": "red", "text": "API error"}],
            "date_info":   None, "news_articles": [], "google_items": [], "ddg_results": []
        })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
