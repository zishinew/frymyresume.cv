# 📄 AI Resume Critique

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://ai-resume-critique-xrppbcokwqrqxxxgnhmp7k.streamlit.app/)
[![Built with](https://img.shields.io/badge/Built_with-Google_Gemini-blue)](https://deepmind.google/technologies/gemini/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)

**Get brutal, professional feedback on your resume in seconds.**

This application uses Google's Gemini AI to critique your resume against the high standards of top-tier tech companies. It provides a 1-10 rating, checks for "impact-driven" bullet points, and offers role-specific advice (e.g., for Software Engineering internships).

## 🚀 Try it Live

The easiest way to use the tool is to visit the live website. No API key or setup required!

### [👉 Click here to launch AI Resume Critique](https://ai-resume-critique-xrppbcokwqrqxxxgnhmp7k.streamlit.app/)

---

## ✨ Features

* **1-10 Scoring:** innovative scoring system to gauge your market competitiveness.
* **Role-Specific Analysis:** Tailors feedback based on whether you are applying for "Software Engineer," "Data Scientist," etc.
* **Impact Detection:** specifically checks if you are quantifying your wins (e.g., "Increased X by Y%").
* **File Support:** Accepts both PDF and TXT files.

---

## 💻 Local Development

If you are a developer and want to run this locally or contribute to the code, follow the steps below.

**Note:** To run locally, you will need your own **Google Gemini API Key**.

### 1. Prerequisites
* **Python 3.10+**
* **uv** (An extremely fast Python package manager)
* **Google Gemini API Key**:
    1.  Go to [Google AI Studio](https://aistudio.google.com/).
    2.  Create a new API key.
    3.  Copy the key string.

### 2. Installation
This project uses `uv` for dependency management.

```bash
# Clone the repository
git clone [https://github.com/yourusername/ai-resume-critique.git](https://github.com/yourusername/ai-resume-critique.git)
cd ai-resume-critique

# Install dependencies using uv
uv add streamlit google-genai python-dotenv PyPDF2
