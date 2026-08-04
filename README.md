# ⚙️ SID-AI — Universal Engineering Drawing Intelligence Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/LangGraph-StateGraph%20Workflow-orange?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Streamlit-Interactive%20Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit" />
  <img src="https://img.shields.io/badge/OpenRouter-Qwen%202.5%2072B-purple?style=for-the-badge&logo=openai&logoColor=white" alt="Qwen 2.5" />
  <img src="https://img.shields.io/badge/Google-Gemini%202.0%20Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini" />
  <img src="https://img.shields.io/badge/OCR-PaddleOCR%20%2B%20PyMuPDF-green?style=for-the-badge" alt="PaddleOCR" />
</p>

---

## 📌 Executive Overview

**SID-AI** (*System for Intelligent Engineering Diagrams*) is an agentic AI system designed to read, classify, reason over, and extract structured digital twins from **ANY engineering drawing type**. 

Unlike conventional fixed P&ID parsers, **SID-AI** features a **universal multi-discipline intelligence engine** that automatically identifies drawing types—including **P&ID**, **Electrical Layouts**, **Earthing/Grounding Layouts**, **Single Line Diagrams (SLD)**, **HVAC Layouts**, **Structural Plans**, **Cable Schedules**, and **Generic Engineering Schematics**—and maps all graphical symbols, alphanumeric tags, connectivity pipelines, electrical circuits, and dynamic specifications into structured engineering formats (**AVEVA Diagrams**, **Siemens COMOS**, **Intergraph SmartPlant P&ID**, **Excel**, and **JSON Graph**).

---

## ✨ Key Features & Capabilities

### 🌐 1. Universal Multi-Discipline Engineering Support
Automated title block recognition and vocabulary scoring classify incoming documents into 10 distinct engineering drawing types:
* 🚰 **P&ID / PFD / Isometric**: Lines, equipment, instruments, manual valves, safety relief valves (PSVs), fluid specs, pressure/temperature classes.
* 💡 **Electrical Layouts**: Luminaires/fittings (`L-01`, `TL-101`), distribution boards (`DB-01`, `MDB-A`), circuits (`MCB-3`), elevation references (`EL.101.445`).
* ⏚ **Earthing Layouts**: Earth bars (`EB-01`, `MEB`), earth pits/electrodes (`EP-A`), bonding conductors (`BC-01`), resistance specs (`<1 Ohm`).
* ⚡ **Single Line Diagrams (SLD)**: Switchgear panels, transformers, busbars, circuit breakers, feeder networks, fault levels.
* ❄️ **HVAC Layouts**: AHUs, FCUs, ductwork, dampers, diffusers, air volume ratings.
* 🏗️ **Structural Layouts**: Structural columns, beams, footings, gridlines, level markings.
* 🔌 **Cable Schedules**: Cable drum tags, core specifications, cross-sectional areas (`mm²`), routing tray pathways.

---

### 🧠 2. 2-Layer Customizable Extraction Engine

To maximize accuracy while minimizing API token usage, text and visual data pass through a modular **2-Layer Extraction Pipeline**:

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                   LAYER 1: OCR Text Extraction Engine                 │
 ├────────────────────────────────────────────────────────────────────────┤
 │  • Local Offline Options : PaddleOCR (GPU/CPU), PyMuPDF Vector Text    │
 │  • Online VLM Options    : Gemini Vision OCR, Qwen 2.5-VL              │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │ (Raw OCR Text + Bounding Box Coordinates)
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │              LAYER 2: Reasoning & Refinement Engine                    │
 ├────────────────────────────────────────────────────────────────────────┤
 │  • Local Offline Option  : Rule-Based Regex Classifier                 │
 │  • Online LLM Options    : Qwen 2.5 via OpenRouter, Gemini, GPT-4o    │
 ├────────────────────────────────────────────────────────────────────────┤
 │  DEEP REASONING CAPABILITIES:                                         │
 │  1. Fixes OCR Typos         : Corrects misread characters (e.g. P1T -> PIT)│
 │  2. Recombines Split Tags   : Merges multiline tag text               │
 │  3. Maps Misplaced Data     : Associates nearby ratings/specs to tags │
 │  4. Discovers Missing Data  : Infers callout notes & missing entities  │
 │  5. Validated JSON Output   : Generates structured RawTextList JSON    │
 └────────────────────────────────────────────────────────────────────────┘
```

---

### 📦 3. Multi-Platform Deliverables & Export System
Extracts digital twins directly into standard engineering formats:
* 📊 **Excel Workbook (`.xlsx`)**: Styled multi-tab workbook with auto-fitted columns and color-coded revision history delta highlighting.
* 🕸️ **Master JSON Graph (`.json`)**: Hierarchical Pydantic schema representation of the entire drawing network.
* 📐 **AVEVA Diagrams / SP3D XML (`.xml`)**: Complete XML plant model schema compliant with AVEVA and Smart 3D import requirements.
* 🔧 **Siemens COMOS JSON (`.json`)**: Hierarchical `Project -> Unit -> Location -> Object` tree formatting.
* 🗃️ **SmartPlant P&ID CSV (`.csv`)**: Relational database import format with standardized headers.

---

### ⚡ 4. 75% Token Savings & Hybrid Optimization
Replaces traditional multi-agent image calls with a **Unified Visual Agent** that extracts graphical symbols, topological relationships, and polyline grid geometry in **1 single visual pass**, saving ~75% in vision token costs.

---

## 📐 Project Architecture & Flowsheet Diagram

The system orchestration is built on **LangGraph (`StateGraph`)**. The complete execution flow and conditional loops defined in [`src/graph.py`](file:///c:/Users/ADMIN/Downloads/pid_project/src/graph.py) are illustrated below:

```mermaid
flowchart TD
    %% Styling
    classDef startEnd fill:#1A73E8,stroke:#0D47A1,stroke-width:2px,color:#FFF;
    classDef agentNode fill:#F8F9FA,stroke:#1A73E8,stroke-width:2px,color:#1A1A2E;
    classDef parallelNode fill:#E8F0FE,stroke:#1A73E8,stroke-width:2px,color:#1A73E8;
    classDef routerNode fill:#FEF3C7,stroke:#F59E0B,stroke-width:2px,color:#92400E;
    classDef outputNode fill:#D1FAE5,stroke:#059669,stroke-width:2px,color:#065F46;

    %% Nodes
    START([📂 Document Upload / Start]) ::: startEnd
    Ingest["📄 Ingestion Agent\n(PDF Rasterization & Drawing Type Detection)"] ::: agentNode
    ContextLoader["📚 Context Loader Agent\n(Legends & Client Standards)"] ::: agentNode
    Supervisor["👨‍✈️ Supervisor Agent\n(Parallel Task Dispatcher)"] ::: agentNode

    %% Parallel Sub-Graph
    subgraph ParallelVision ["👁️ Parallel Vision Sub-Graph"]
        TextDetection["🔤 Text Detection Agent\n(2-Layer OCR + Qwen 2.5 / Gemini Reasoning)"] ::: parallelNode
        UnifiedVision["👁️ Unified Vision Agent\n(1-Call VLM: Symbols + Relations + Geometry)"] ::: parallelNode
    end

    Compiler["⚙️ Universal Object Compiler\n(Entity Assembly into UniversalEngineeringGraph)"] ::: agentNode
    Validation["🔍 Validation Agent\n(Rule-Based & Topological QA Checks)"] ::: agentNode
    Completeness["📋 Completeness Checker\n(Missing Region & Entity Detection)"] ::: agentNode
    
    %% Router
    Router{"🔀 Completeness Router\n(Missing Items & Count < Max Retries?)"} ::: routerNode
    
    ReExtractor["🔎 Focused Re-Extractor Agent\n(Cropped Re-Scanning)"] ::: agentNode
    OutputGen["📥 Output Generator Agent\n(Excel, AVEVA XML, COMOS, SPPID CSV)"] ::: outputNode
    END_NODE([🏁 Final Deliverables Ready]) ::: startEnd

    %% Flow Connections
    START --> Ingest
    Ingest --> ContextLoader
    ContextLoader --> Supervisor
    
    Supervisor --> TextDetection
    Supervisor --> UnifiedVision
    
    TextDetection --> Compiler
    UnifiedVision --> Compiler
    
    Compiler --> Validation
    Validation --> Completeness
    Completeness --> Router
    
    Router -- "YES: Missing Items Found" --> ReExtractor
    ReExtractor --> Compiler
    
    Router -- "NO: Validated / Max Retries" --> OutputGen
    OutputGen --> END_NODE
```

---

## 📂 Repository Structure

```
pid_project/
├── app.py                          # Streamlit UI Dashboard & Config Controls
├── main.py                         # CLI Execution Entry Point
├── requirements.txt                # Dependencies
├── .env.example                    # Sample Environment Variables Configuration
├── .gitignore                      # Git Exclusion Rules
├── src/
│   ├── graph.py                    # LangGraph StateGraph Execution Topology
│   ├── state.py                    # GraphState TypedDict Definition
│   ├── models.py                   # Universal Engineering Data Models (Pydantic)
│   ├── config.py                   # Multi-Provider Client Factory (Gemini, OpenRouter, Qwen)
│   ├── agents/
│   │   ├── base.py                 # Base Agent Class for Multi-Model Execution
│   │   ├── ingestion.py            # Document Rasterization & Metadata Extraction
│   │   ├── context_loader.py       # Client Legend & Standard Parser
│   │   ├── supervisor.py           # Execution Coordinator
│   │   ├── parallel_vision.py      # TextDetectionAgent (2-Layer) & UnifiedVisionAgent
│   │   ├── compiler.py             # Universal Engineering Graph Compiler
│   │   ├── validation.py           # QA & Engineering Consistency Rules
│   │   ├── completeness.py         # Missing Entity Checker
│   │   ├── re_extractor.py         # Cropped Bounding Box Re-Scanner
│   │   └── output_generator.py     # Excel, AVEVA XML, COMOS JSON & SPPID CSV Generator
│   └── utils/
│       ├── drawing_type_detector.py # Drawing Classification Heuristics
│       ├── tag_classifier.py       # Multi-Discipline Regex Pattern Library
│       ├── paddle_ocr.py           # Local PaddleOCR & PyMuPDF Text Layer Extractor
│       ├── preprocess.py           # OpenCV Image Preprocessing
│       └── mock_data.py            # Static Fallback Databases
```

---

## 🛠️ Quickstart & Setup Guide

### 1. Prerequisites
* **Python**: 3.11, 3.12, or 3.13
* **OS**: Windows, macOS, or Linux

### 2. Installation

Clone the repository and install dependencies:
```bash
git clone https://github.com/your-username/sid-ai.git
cd pid_project

# Create virtual environment
python -m venv pid_env

# Activate virtual environment
# Windows:
pid_env\Scripts\activate
# Linux/macOS:
source pid_env/bin/activate

# Install requirements
pip install -r requirements.txt
```

---

### 3. Environment Configuration (`.env`)

Create a `.env` file in the project root directory:
```env
# Google Gemini API Key (For Gemini 2.0 Flash)
GEMINI_API_KEY=your_gemini_api_key_here

# OpenRouter API Key (For Qwen 2.5 via OpenRouter)
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_key_here

# Qwen Settings (Defaults to OpenRouter)
QWEN_BASE_URL=https://openrouter.ai/api/v1
QWEN_MODEL=qwen/qwen-2.5-72b-instruct

# Optional OpenAI / Groq keys
OPENAI_API_KEY=your_openai_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

---

### 4. Running the Dashboard

Launch the Streamlit interactive dashboard:
```bash
streamlit run app.py
```

The web dashboard will be available at `http://localhost:8501`.

---

## 💻 Dashboard Configuration Controls

The dashboard sidebar provides complete control over the pipeline execution:

| Section | Setting | Options / Description |
|---|---|---|
| **Layer 1: OCR Text Engine** | `1st Layer OCR` | • `PaddleOCR (Local / Offline)`<br/>• `PyMuPDF Vector Text (Local / Offline)`<br/>• `Gemini Vision OCR (Online API)`<br/>• `Qwen 2.5-VL / Vision API (Online)` |
| **Layer 2: Reasoning Engine** | `2nd Layer Reasoning` | • `Rule-Based Regex (Local / Offline)`<br/>• `Qwen 2.5 Reasoning Engine (OpenRouter / API)`<br/>• `Gemini 2.0 Flash Engine (Online API)`<br/>• `OpenAI GPT-4o Engine (Online API)` |
| **Provider Settings** | `API Key & Base URL` | Custom inputs for OpenRouter API keys (`sk-or-v1-...`), custom endpoints, or local vLLM / Ollama (`http://localhost:11434/v1`). |
| **Execution Options** | `Offline Mode` | `🔌 Force Full Offline Mode`: Runs PaddleOCR + Regex Classifier locally with zero API token consumption. |

---

## 📞 Author & Contact

**Developer**: Abhinav Gupta  
**Email**: [abhinavgupta15.ag@gmail.com](mailto:abhinavgupta15.ag@gmail.com)  

---

<p align="center">
  <i>Built with ❤️ using Python, LangGraph, Streamlit, OpenRouter Qwen 2.5, and Google Gemini.</i>
</p>
