# 🎭 StageCoach  
### Accessible Performance Feedback for Every Student

StageCoach is a web-based performance feedback tool designed to help students improve speeches, monologues, and debates through structured, actionable analysis.

Built during a hackathon with a focus on educational accessibility.

---

## 🚀 What It Does

Users can:

- Upload a script (.txt, .docx, selectable PDF)
- Choose performance type:
  - 🎭 Monologue (Acting)
  - 🗣 Debate
  - 🎤 Public Speech
- Select feedback style and performance goals
- Receive structured coaching feedback

The system generates:

- ✅ Strengths
- ✅ Improvements
- ✅ Line-specific notes
- ✅ A rehearsal checklist
- ✅ Word count
- ✅ Estimated speaking time
- ✅ Text complexity level
- ✅ Repetition analysis
- ✅ Rubric scores

---

## 🧠 The Problem

Many students do not have access to:

- Private acting coaches
- Debate mentors
- Public speaking tutors
- Immediate structured feedback

StageCoach aims to lower that barrier by providing structured performance coaching instantly and affordably.

---

## 🎯 Educational Accessibility Focus

StageCoach supports:

- Simplified feedback modes
- ESL-friendly analysis
- Confidence-building feedback options
- Rubric-style scoring for classroom use
- Estimated speaking time for competition prep

The goal is to make quality performance coaching accessible to more students.

---

## 🛠 Tech Stack

- **Backend:** Python (Flask)
- **Frontend:** HTML, CSS, JavaScript
- **Text Processing:** Regex-based heuristic analysis
- **File Parsing:** python-docx, PyPDF2
- **Environment Management:** python-dotenv

---

## ⚙️ How It Works

1. User uploads script.
2. Text is extracted and cleaned.
3. The system analyzes:
   - Sentence count
   - Word count
   - Repetition frequency
   - Evidence indicators
   - Emotional language
4. Feedback branches depending on speech type.
5. Structured coaching output is returned.
6. Frontend displays animated processing before revealing feedback.

---

## 📂 Project Structure

```
stagecoach/
│
├── main.py
├── templates/
│   ├── greeting.html
│   └── index.html
├── static/
├── README.md
├── requirements.txt
└── .gitignore
```

---

## 🧪 Running Locally

Install dependencies:

```bash
pip install flask python-docx PyPDF2 python-dotenv
```

Run the app:

```bash
python main.py
```

Open:

```
http://localhost:5000
```

---

## 🌍 Future Improvements

- Audio upload for vocal analysis
- Classroom dashboard mode
- Time-limit warnings for competitions
- Advanced AI-driven feedback
- Teacher rubric export

---

## 👥 Team

Built with the mission of making performance coaching accessible to all learners.
