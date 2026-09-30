================================================================================
PID DATA EXTRACTOR — SETUP & EXECUTION GUIDE FOR NIRAJ (OFFLINE MODE)
================================================================================

This guide provides complete, step-by-step instructions for setting up and running
the PID Data Extractor locally on your machine using Visual Studio Code (VS Code),
a dedicated Python 3.13 virtual environment, and Streamlit.

NOTE: This system runs 100% locally and OFFLINE using local machine learning models
(YOLOv8, PaddleOCR/EasyOCR, and rule-based graph compilation). No external API keys
or cloud services are required to run extractions.

All commands below can be directly copied and pasted into your terminal.

================================================================================
TABLE OF CONTENTS
================================================================================
1. Prerequisites
2. Step 1: Open the Project in VS Code
3. Step 2: Verify Python 3.13
4. Step 3: Create Python 3.13 Virtual Environment
5. Step 4: Activate the Virtual Environment
6. Step 5: Install Dependencies
7. Step 6: Launch Streamlit for the First Time (Email Prompt Guide)
8. Step 7: How to Use the Application
9. Stopping and Restarting the App
10. Troubleshooting & FAQs

================================================================================
1. PREREQUISITES
================================================================================
Ensure your system has the following installed:

1. Python 3.13:
   - Download: https://www.python.org/downloads/
   - IMPORTANT during setup: Check the box "Add python.exe to PATH".

2. Visual Studio Code (VS Code):
   - Download: https://code.visualstudio.com/
   - Recommended extension: Python (by Microsoft).

3. Git (optional, if cloning from a repository).

================================================================================
STEP 1: OPEN THE PROJECT IN VS CODE
================================================================================
1. Launch Visual Studio Code.
2. Go to File -> Open Folder... (or press Ctrl + K, Ctrl + O).
3. Select the "pid_project" folder.
4. Open the integrated terminal:
   - Press Ctrl + ` (backtick) OR click menu: Terminal -> New Terminal.
   - On Windows, VS Code opens a PowerShell terminal by default.

================================================================================
STEP 2: VERIFY PYTHON 3.13
================================================================================
In the VS Code terminal, verify that Python 3.13 is available:

py -3.13 --version

Expected output:
Python 3.13.x

(Note: If 'py' is not recognized, run 'python --version' to check your default version).

================================================================================
STEP 3: CREATE PYTHON 3.13 VIRTUAL ENVIRONMENT
================================================================================
Create a dedicated virtual environment named 'venv' inside the project folder:

py -3.13 -m venv venv

(If py -3.13 is not available, run: python -m venv venv)

A new folder named 'venv' will appear in your VS Code explorer.

================================================================================
STEP 4: ACTIVATE THE VIRTUAL ENVIRONMENT
================================================================================
Choose the command matching your terminal type:

A) In PowerShell (Default in VS Code on Windows):
------------------------------------------------
.\venv\Scripts\Activate.ps1

NOTE: If you see an error: "running scripts is disabled on this system", run this once:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

B) In Command Prompt (cmd):
---------------------------
venv\Scripts\activate.bat

C) In Git Bash:
---------------
source venv/Scripts/activate

Once activated, your terminal prompt will show (venv) at the beginning, like:
(venv) PS C:\path\to\pid_project>

---
VS Code Interpreter Selection (Recommended):
1. In VS Code, press Ctrl + Shift + P.
2. Type: Python: Select Interpreter.
3. Choose "Enter interpreter path..." -> "Find...".
4. Browse to: venv\Scripts\python.exe and select it.

================================================================================
STEP 5: INSTALL DEPENDENCIES
================================================================================
With (venv) activated, upgrade pip and install all required packages:

python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

(Installation takes about 2 to 5 minutes to download PyTorch, OpenCV, PaddleOCR,
Ultralytics, and Streamlit).

Verification Check:
-------------------
To confirm everything is installed properly, run:

python -c "import streamlit, ultralytics, langchain_core; print('All core libraries installed successfully!')"

================================================================================
STEP 6: LAUNCH STREAMLIT FOR THE FIRST TIME (EMAIL PROMPT GUIDE)
================================================================================
To launch the application, run:

streamlit run app.py

--------------------------------------------------------------------------------
WHAT HAPPENS ON YOUR VERY FIRST RUN:
--------------------------------------------------------------------------------
Because this is your first time running Streamlit on your computer, Streamlit will
display this prompt in your terminal:

  Welcome to Streamlit!

  If you'd like to receive the latest versions, news, and best practices,
  please enter your email.
  Email: 

HOW TO RESPOND:
- OPTION A (Fastest & Recommended): Just press the ENTER key on your keyboard.
  This skips entering an email and proceeds immediately.
- OPTION B: Type your email address and press ENTER.

After you press Enter, Streamlit prints:

  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501

- Your default browser (Chrome, Edge, etc.) will automatically open to http://localhost:8501.
- If it doesn't open automatically, hold Ctrl and click http://localhost:8501 in the terminal,
  or paste it into your browser.

--------------------------------------------------------------------------------
OPTIONAL PRO-TIP: Bypass the prompt before even running Streamlit
--------------------------------------------------------------------------------
If you want to skip the prompt automatically without it ever showing up, paste this
single line into PowerShell before running streamlit:

mkdir -Force "$env:USERPROFILE\.streamlit"; Set-Content "$env:USERPROFILE\.streamlit\credentials.toml" "[general]`nemail = `"`""

================================================================================
STEP 7: HOW TO USE THE APPLICATION
================================================================================
1. Upload a Drawing:
   - On the web page, drag and drop or browse for a P&ID file (.pdf, .png, .jpg, .tiff).
2. Select Diagram Type:
   - Choose P&ID (Piping & Instrumentation Diagram) or PFD (Process Flow Diagram).
3. Run Extraction:
   - Click the "🚀 Extract P&ID Data" button.
   - The extraction runs completely offline using local models.
   - Watch the multi-agent pipeline progress in real-time.
4. Review Structured Tables On-Screen:
   - Expand the on-screen tables to view:
     * Equipment
     * Piping Lines & Segments
     * Instruments & Loops
     * Valves
     * Nozzles
     * Components
5. Download Output Deliverables:
   - Click any of the 6 format buttons to download directly:
     * Excel Spec Sheet (.xlsx)
     * Engineering Graph (.json)
     * AVEVA Diagrams XML (.xml)
     * Siemens COMOS JSON (.json)
     * SmartPlant P&ID CSV (.csv)
     * Relationships CSV (.csv)
6. Historical Runs:
   - Click the "Extraction History" tab at the top to view past extractions,
     inspect their tables on-screen, and re-download deliverables on-demand.

================================================================================
STOPPING AND RESTARTING THE APP
================================================================================
To Stop Streamlit:
- Click inside the VS Code terminal running Streamlit.
- Press Ctrl + C.

To Restart Later:
Whenever you return to the project:
1. Open VS Code terminal (Ctrl + `).
2. Activate the environment:
   .\venv\Scripts\Activate.ps1
3. Run Streamlit:
   streamlit run app.py

================================================================================
TROUBLESHOOTING & FAQS
================================================================================
Q1: PowerShell says "running scripts is disabled on this system".
A1: Run this in PowerShell:
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\venv\Scripts\Activate.ps1

Q2: Port 8501 is already in use.
A2: Start on a different port:
    streamlit run app.py --server.port 8502

Q3: Do I need an internet connection or API keys to run extractions?
A3: No. The extraction pipeline uses locally hosted YOLO weights (yolov8m.pt / yolo26n.pt),
    local OCR engines, and deterministic graph compilers. It runs 100% offline.

Q4: Python was not found.
A4: Re-run the Python 3.13 installer and check "Add python.exe to PATH",
    or use "py -3.13 -m venv venv".
================================================================================
