import os
from flask import Flask, render_template, request, jsonify

from dotenv import load_dotenv
load_dotenv()

from PyPDF2 import PdfReader
import docx
import re
from collections import Counter

app = Flask(__name__)

# ---------- File text extraction ----------
def extract_text_from_upload(file_storage) -> str:
    filename = (file_storage.filename or "").lower()

    if filename.endswith(".txt"):
        return file_storage.read().decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        reader = PdfReader(file_storage.stream)
        parts = []
        for page in reader.pages[:5]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()

    if filename.endswith(".docx"):
        d = docx.Document(file_storage.stream)
        return "\n".join(p.text for p in d.paragraphs).strip()

    return ""

def clean_text(text: str) -> str:
    if not text:
        return ""

    if text.lstrip().startswith("{\\rtf"):
        text = re.sub(r"{\\.*?}|\\[a-zA-Z]+\d* ?", " ", text)
        text = text.replace("{", " ").replace("}", " ")

    # Remove weird control characters
    text = "".join(
        ch if ch == "\n" or ch == "\t" or 32 <= ord(ch) <= 126 else " "
        for ch in text
    )

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ---------- Prompting ----------
def build_prompt(speech_type: str, audience: str, style: str, text: str) -> str:
    style_map = {
        "balanced": "Balanced: encouraging but direct.",
        "strict": "Strict coach: blunt, specific, no fluff.",
        "supportive": "Supportive coach: kind, confidence-building, still specific."
    }
    tone = style_map.get(style, style_map["balanced"])

    return f"""
You are a performance coach helping students improve with deliberate practice.
Tone: {tone}

Context:
- Type: {speech_type}
- Intended audience: {audience}

Rules:
- Give EXACTLY these sections in this order:
  1) Strengths (3 bullet points)
  2) Improvements (3 bullet points)
  3) Line-specific notes (2 bullets). Each bullet must quote a short snippet (<= 12 words) then a coaching note.
  4) Next Take Checklist (exactly 3 numbered items)
- Keep it actionable and rehearsal-focused (pacing, emphasis, structure, clarity, delivery).
- Do NOT rewrite the entire piece. Do NOT add extra sections.

Student text:
{text}
""".strip()

FILLER_WORDS = {"um", "uh", "like", "you know", "literally", "basically"}
EMOTION_WORDS = {"love", "hate", "fear", "hope", "cry", "laugh", "anger", "hurt", "joy", "regret"}
EVIDENCE_CUES = {"because", "therefore", "however", "according", "data", "study", "evidence", "statistic", "%"}

def _sentences(text: str):
    # simple sentence split
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p for p in parts if p]

def _top_repeats(text: str, n=3):
    words = re.findall(r"[A-Za-z']+", text.lower())
    counts = Counter(w for w in words if len(w) > 3)
    common = [w for w, c in counts.most_common(n) if c >= 3]
    return common

def clean_text_for_display(text: str) -> str:
    # Removes weird RTF-ish junk and control sequences and collapses whitespace
    text = re.sub(r"{\\rtf1.*?}|\\[a-z]+\d*", " ", text)   # kills RTF fragments like {\rtf1... \ansi ...}
    text = re.sub(r"[^\x09\x0A\x0D\x20-\x7E]", " ", text)  # remove non-printable chars
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _rubric_scores(speech_type: str, text: str):
    # Quick heuristic rubric (0-5)
    t = text.lower()
    wc = len(re.findall(r"[A-Za-z']+", text))
    has_evidence = any(cue in t for cue in EVIDENCE_CUES)
    has_signposts = any(k in t for k in ["first", "second", "finally", "in conclusion"])
    has_emotion = any(w in t for w in EMOTION_WORDS)

    def clamp(x): 
        return max(0, min(5, x))

    if speech_type == "debate":
        structure = 3 + (1 if has_signposts else 0)
        evidence = 2 + (2 if has_evidence else 0)
        clarity = 3 + (1 if wc < 900 else 0)
        return {
            "Structure": clamp(structure),
            "Evidence": clamp(evidence),
            "Clarity": clamp(clarity),
        }

    if speech_type == "monologue":
        stakes = 2 + (2 if has_emotion else 0)
        objective = 3
        beats = 2 + (1 if wc > 250 else 0)
        return {
            "Emotional Stakes": clamp(stakes),
            "Objective Clarity": clamp(objective),
            "Beat Changes": clamp(beats),
        }

    # public_speech
    hook = 2 + (1 if "?" in text else 0) + (1 if has_signposts else 0)
    organization = 3 + (1 if has_signposts else 0)
    takeaway = 3 + (1 if "call" in t or "action" in t else 0)
    return {
        "Hook": clamp(hook),
        "Organization": clamp(organization),
        "Takeaway": clamp(takeaway),
    }

def _tone_wrap(style: str, goal: str, msg: str) -> str:
    if not msg:
        return msg

    strict = (style == "strict")
    supportive = (style == "supportive")

    if goal == "confidence":
        msg = "You're doing a lot right — " + msg[0].lower() + msg[1:]
    elif goal == "competition":
        msg = "For competition-level scoring: " + msg

    if strict:
        msg = msg.replace("Consider", "You need to").replace("Try", "Do")
    elif supportive:
        msg = "You're close — " + msg[0].lower() + msg[1:]
    return msg

def _simplify(complexity: str, msg: str) -> str:
    if complexity == "standard":
        return msg
    if complexity == "simplified":
        # shorter, simpler
        msg = msg.replace("opportunities", "chances")
        msg = msg.replace("structure", "order")
        msg = msg.replace("audience", "people listening")
        return msg
    if complexity == "esl":
        # clearer, slower language
        msg = msg.replace("warrant", "reason")
        msg = msg.replace("signposting", "clear transitions")
        msg = msg.replace("impact", "why it matters")
        return msg
    return msg

def ai_feedback(speech_type: str, audience: str, style: str, text: str, complexity="standard", goal="confidence", rubric_mode="on") -> str:
    text_clean = clean_text_for_display(text)
    sents = _sentences(text_clean)
    words = re.findall(r"[A-Za-z']+", text_clean)
    wc = len(words)
    sc = max(1, len(sents))
    repeats = _top_repeats(text_clean)

    has_questions = "?" in text_clean
    has_emotion = any(w.lower() in EMOTION_WORDS for w in words)
    has_evidence = any(cue in text_clean.lower() for cue in EVIDENCE_CUES)

    # Safer “snippets”
    if sents:
        q1 = " ".join(sents[0].split()[:12])
        q2 = " ".join(sents[min(1, len(sents)-1)].split()[:12])
    else:
        q1 = " ".join(text_clean.split()[:12])
        q2 = " ".join(text_clean.split()[12:24])

    # ---- Branch by speech type ----
    if speech_type == "monologue":
        strengths = [
            "You have a clear character point-of-view driving the lines.",
            f"You can tailor delivery to your audience vibe: {audience}.",
            "There are moments that can land emotionally with pacing and emphasis."
        ]
        improvements = [
            "Add playable actions per beat: persuade, deflect, confess, challenge.",
            "Build contrast: vary pace + volume so the energy changes with meaning.",
            "Mark 2–3 ‘turns’ where the intention changes, and show it physically."
        ]
        if not has_emotion:
            improvements[0] = "Add emotional stakes: what is lost if the character fails?"

        line_notes = [
            f"\"{q1}\" → Choose one verb-action (to charm / to accuse / to confess) and commit.",
            f"\"{q2}\" → Add a pause before the key word so the truth or punch lands."
        ]
        checklist = [
            "Write the objective (what you want) at the top of the page.",
            "Circle 3 key words and hit them with emphasis + pause.",
            "Do one take with stillness, one with blocking—keep what works."
        ]

    elif speech_type == "debate":
        strengths = [
            "Your argument can be shaped into a clear claim → reason → impact flow.",
            "You’re already thinking about judges/opponent expectations.",
            "You have opportunities for strong signposting and clash."
        ]
        improvements = [
            "State your claim in the first 1–2 sentences, then label your reasons.",
            "Add evidence: a statistic, a credible source, and an example.",
            "Preempt a likely counterargument and answer it in one clean paragraph."
        ]
        if not has_evidence:
            improvements[1] = "Right now it reads like opinion—add at least 2 pieces of evidence."
        if not has_questions:
            improvements[2] = "Add one strategic rhetorical question to frame the judge’s choice."

        line_notes = [
            f"\"{q1}\" → Turn this into a labeled claim (e.g., ‘Contention 1: …’).",
            f"\"{q2}\" → Add why it matters: what changes if the judge agrees?"
        ]
        checklist = [
            "Write a 10-second thesis you can say without looking.",
            "Add 2 evidence lines (source + number) and practice delivering them cleanly.",
            "End with a voting issue: ‘Prefer us because…’ (1 sentence)."
        ]

    else:  # public_speech
        strengths = [
            "You can shape this into a strong hook → message → takeaway structure.",
            "Your topic can be made audience-specific, which judges love.",
            "There are places to add storytelling for memorability."
        ]
        improvements = [
            "Open with a hook (story, surprising stat, vivid image) in the first 2 lines.",
            "Use clear transitions: ‘First… Second… Finally…’ so it’s easy to follow.",
            "End with a clear call-to-action or memorable final line."
        ]
        if wc < 180:
            improvements[1] = "It may be too short—add one example story to deepen the point."

        line_notes = [
            f"\"{q1}\" → Make this stronger by adding one concrete detail (who/where/when).",
            f"\"{q2}\" → Repeat the core message in a clean one-sentence takeaway."
        ]
        checklist = [
            "Write a 1-sentence message and repeat it twice in different words.",
            "Add one vivid example story (3–4 sentences).",
            "Craft a final line that sounds like an ending, not an explanation."
        ]

    # Apply tone + complexity adjustments
    strengths = [_simplify(complexity, _tone_wrap(style, goal, s)) for s in strengths]
    improvements = [_simplify(complexity, _tone_wrap(style, goal, s)) for s in improvements]
    line_notes = [_simplify(complexity, _tone_wrap(style, goal, s)) for s in line_notes]

    # Rubric block
    rubric_block = ""
    if rubric_mode != "off":
        scores = _rubric_scores(speech_type, text_clean)
        rubric_lines = "\n".join([f"- {k}: {v}/5" for k, v in scores.items()])
        rubric_block = f"Rubric Scores:\n{rubric_lines}\n\n"

    # ---- Educational Analysis Block ----
    speaking_time_minutes = wc / 160  # average speaking rate ~160 wpm
    minutes = int(speaking_time_minutes)
    seconds = int((speaking_time_minutes - minutes) * 60)

    # Rough complexity check
    avg_sentence_length = wc / sc if sc else 0
    if avg_sentence_length < 12:
        complexity_label = "Simple"
    elif avg_sentence_length < 18:
        complexity_label = "Medium"
    else:
        complexity_label = "Advanced"

    repetition_note = ""
    if repeats:
        repetition_note = f"{', '.join(repeats)} appear frequently. Consider varying word choice."

    analysis_block = (
        "Text Analysis:\n"
        f"- Word Count: {wc}\n"
        f"- Estimated Speaking Time: {minutes} min {seconds} sec\n"
        f"- Complexity Level: {complexity_label}\n"
    )

    if repetition_note:
        analysis_block += f"- Repetition Focus: {repetition_note}\n"
    analysis_block += "\n"
    return (
            f"{analysis_block}"
            f"{rubric_block}"
            "Strengths:\n"
            f"- {strengths[0]}\n- {strengths[1]}\n- {strengths[2]}\n\n"
            "Improvements:\n"
            f"- {improvements[0]}\n- {improvements[1]}\n-    {improvements[2]}\n\n"
            "Line-specific notes:\n"
            f"- {line_notes[0]}\n- {line_notes[1]}\n\n"
            "Next Take Checklist:\n"
            f"1) {checklist[0]}\n2) {checklist[1]}\n3) {checklist[2]}\n"
        )

# ---------- Routes ----------
@app.route("/")
def home():
    return render_template("greeting.html")


@app.route("/feedback")
def feedback_page():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        speech_type = request.form.get("speechType", "").strip()
        audience = request.form.get("audience", "").strip()
        style = request.form.get("style", "balanced").strip()
        complexity = request.form.get("complexity", "standard").strip()
        goal = request.form.get("goal", "confidence").strip()
        rubric_mode = request.form.get("rubricMode", "on").strip()

        file_storage = request.files.get("scriptFile")

        if not file_storage or not file_storage.filename:
            return jsonify({"feedback": "Please upload a file."}), 400
        if not speech_type:
            return jsonify({"feedback": "Please select a speech type."}), 400
        if not audience:
            return jsonify({"feedback": "Please describe the audience."}), 400

        text = extract_text_from_upload(file_storage)
        text = clean_text(text)            
        if not text:
            return jsonify({"feedback": "Couldn’t extract text. Try .txt, .docx, or a selectable-text PDF."}), 400

        if len(text) > 12000:
            text = text[:12000] + "\n\n[Truncated for demo length]"

        feedback = ai_feedback(
            speech_type=speech_type,
            audience=audience,
            style=style,
            text=text,
            complexity=complexity,
            goal=goal,
            rubric_mode=rubric_mode
        )
        return jsonify({"feedback": feedback})

    except Exception as e:
        return jsonify({"feedback": f"Server error: {type(e).__name__}: {e}"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
