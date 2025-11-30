import streamlit as st
import PyPDF2
import io
import os
from datetime import date
from google import genai
from dotenv import load_dotenv

load_dotenv()
st.markdown("""
    <style>
    /* Style the title */
    h1 {
        text-align: center;
        color: #6C63FF;
    }

    /* Target the actual button */
    div.stButton > button {
        width: 465% !important; /* Set a reasonable width */
        background-color: #4CAF50 !important; 
        color: white !important;
        padding: 10px !important;
        border-radius: 10px !important;
        border: none !important;
        display: block !important; 
    }
    
    /* Hover effect */
    div.stButton > button:hover {
        background-color: #45a049 !important;
        color: white !important;
    }
    </style>
""", unsafe_allow_html=True)

st.set_page_config(page_title = "AI Resume Critique", page_icon = "📄", layout = "centered")

st.title("AI Resume Critique 🗒️")
st.subheader("Upload your resume and get professional AI-powered feedback, designed with resume criteria from hiring managers at Google.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
uploaded_file = st.file_uploader("Upload your resume (PDF or TXT)", type = ["pdf", "txt"])

# Create two columns of equal width
col1, col2 = st.columns(2)

with col1:
    job_role = st.text_input("Target Job Role", placeholder="e.g. Software Engineer")
with col2:
    notes = st.text_input("Additional Notes", placeholder="e.g. Applying for Internship")

analyze_button = st.button("📝 Analyze Resume!")

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_text(uploaded_file):
    if uploaded_file.type == "application/pdf":
        return extract_text_from_pdf(io.BytesIO(uploaded_file.read()))
    return uploaded_file.read().decode("utf-8")

if analyze_button and uploaded_file:
    with st.spinner("AI is reviewing your resume..."):
        try:
            file_content = extract_text(uploaded_file)
        
            if not file_content.strip():
                st.error("File does not have any content")
                st.stop()
    
            prompt = f"""Today is {date.today()}. Take the role of a professional resume critiquer and analyze the following resume in detail. Also provide a rating from 1-10
            Make sure that their resume follows these tips:
            - Beyond the basics: your narrative
            - Making the first impression
                - You can alter your resume for each position youre applying to if necessary
            - Highlighting relevant qualifications
                - Dont list anything and everything that has no correlation at all, make sure you emphasize things that actually have relevance
            Important Notes for First Resumes
            - High School Highlights: Know when to let go
            - Beyond the Classroom: Start building your story now
            - Skills that Shine: Focus on what you can do
            - Resume Essentials: Clarity, structure, and impactful language
            Resume concept: Know Your Audience
            - Adapt and Iterate: Your resume is never “done”
            - Quantify Your Wins: Use numbers and specific examples to show your expertise
            - Communicate Your Value: What makes you the right fit?
            - Authenticity Matters: While you should tailor your resume, don’t try to be someone you’re not. Let your unique contributions shine. Recruiters appreciate authenticity and let your passion and character shine through
            General Resume Tips
            - Formatting
                - PDF
                - Bullet points and consistent formatting
                    - Use consistent bullet points for readibility
                - Action + Merit = Results
                - Github and contact info
            - Important Notes
                - Review qualifications
                    - Know the minimum and preferred qualifications and use your background to show how you fill those requirements
                - Coursework
                    - Include relevant coursework pertinent to the role. If you have some sort of background with coursework for a field that you are applying for, then list what coursework you did
                - References and Objectives
                    - Do not include references or lengthy objectives
                - Keep your resume to only ONE PAGE
            What to Include
            - Must have
                - Contact information
                    - Address, phone number, email etc.
                - Education
                    - State your major, anticipated graduation month and year
                - Technical skills
                    - Programming skills, personal projects, class assignments, ux design, hackathon wins, etc anywhere where those skills could have been applied
                    - Highlight what programming languages that you have experience in
                - Leadership/Activities
                    - Show your passion in other interests, especially ones where you have taken a leadership role in
                    - Include a portfolio
            - Good to Have
                - Awards/Honors
                    - If you have any academic awards then highlight them
                - Interests
                    - Add a personal touch but keep it concise
            Resume Flow
            - Education
                - Technical Skills
            - Work Experience
            - Projects (Classroom & Personal)
            - Leadership Updates
            Header
            - Name at top
            - Phone number | email | Linkedin, Github
            Education
            - Post-secondary school + High school if you are a first year
            - Major
            - GPA
            - Relevant coursework
            - Technical skills
                - Highlight your most proficient skills, you can add tags in brackets like (proficient), (intermediate) etc.
            Work Experience
            - Employer, role, dates: the essentials
            - Impact-driven bullets: concise & results-orientated
            - Highlight relevance: tech skills & transferable strengths
            - Formula:
                - Accomplished [X] (what you did), as measured by [Y] (the metric/result), by doing [Z] (the actions you took) IMPORTANT!!! If they do not do this, make sure to point it out!
                - Examples:
                    - Increased server query response time by 15% by restricting API ✅
                    - Participated in city hackathon working on a. Facial recognition project ❌
                    - Won second place out of 40 teams in the City Hackathon, building facial recognition software that helps detect human emotions, utilizing Python and Java ✅
                    
            Resume content: {file_content}
            Tailor your feedback for {job_role if job_role else "general applications"}
            Provide your feedback and analysis in a clear strutured format with specific recommendations.
            Additional Notes: {notes + "If the student is still in university, they are probably applying for internship roles"if notes else "If the student is still in university, they are probably applying for internship roles"}
            Be SUPER strict and BRUTALLY honest. This is an EXTREMELY IMPORTANT POINT. IF THEY ARE NOT READY, DO NOT GIVE THEM FALSE HOPE. {f"Consider the current job market for the {job_role} industry" if job_role else ""} If the user is not qualified give them a serious reality check, however do not be demotivating. Tell them their current situation, and provide next steps.
            Do not weigh in factors such as "for a first year your resume is very good" into the rating and give them a high rating. You can mention it in the analysis, but make the rating out of ten extremely strict and realistic for the job market.
            Jump right into the rating and analysis.
            When providing them with a rating, use this scale:
            1-3: Resume needs LOTS of work, and as of where they are right now they have no chance in the industry.
            3-5: Beginner level resume, small chance at finding work in competitive industries, especially with the current job market
            5-7: Ready for entry-level jobs, but not very competitive, has chance at landing jobs at small scale firms/startups
            8-10: Competitive in the market for top firms
            Assume the resume they attach are the resume they are applying to the job role with. Do not consider future trajectory in the rating, but it is okay to mention it in the analysis/breakdown.
            """ 
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model = "gemini-2.5-flash",
                contents = prompt
            )
            st.success("Analysis Complete!")

            # Create a container with a border
            with st.container(border=True):
                st.markdown("### 📝 Detailed Feedback")
                st.markdown(response.text)
    
        except Exception as e:
            st.error(f"An error occured: {str(e)}")