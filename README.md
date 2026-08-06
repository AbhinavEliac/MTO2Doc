# ⚙️ SID-AI — Universal Engineering Drawing Intelligence Platform

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/LangGraph-StateGraph%20Workflow-orange?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Streamlit-Interactive%20Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit" />
  <img src="https://img.shields.io/badge/Pathnovo-ISA%205.1%20API-008080?style=for-the-badge" alt="Pathnovo ISA 5.1" />
  <img src="https://img.shields.io/badge/OpenRouter-Qwen%203.7%20VL-purple?style=for-the-badge&logo=openai&logoColor=white" alt="Qwen 3.7 VL" />
  <img src="https://img.shields.io/badge/Google-Gemini%202.0%20Flash-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Gemini" />
</p>

---

## 📌 Executive Overview

**SID-AI** (*System for Intelligent Engineering Diagrams*) is an agentic AI system designed to read, classify, reason over, and extract structured digital twins from **ANY engineering drawing type**. 

Unlike conventional fixed P&ID parsers, **SID-AI** features a **parallel perception multi-discipline intelligence engine** that automatically identifies drawing types—including **P&ID**, **Electrical Layouts**, **Earthing/Grounding Layouts**, **Single Line Diagrams (SLD)**, **HVAC Layouts**, **Structural Plans**, **Cable Schedules**, and **Generic Engineering Schematics**—and maps all graphical symbols, alphanumeric tags, connectivity pipelines, electrical circuits, and dynamic specifications into structured engineering formats (**AVEVA Diagrams**, **Siemens COMOS**, **Intergraph SmartPlant P&ID**, **Excel**, and **JSON Graph**).

---

## ✨ Key Features & Capabilities

### 🌐 1. Pathnovo ISA 5.1 Native Extraction API Integration
Native integration with the **Pathnovo P&ID Extraction API**, trained on ISA 5.1 instrumentation standards:
* **Instrument Function Bubbles & Loop IDs**: Pulls exact loop numbers (`9054`, `9055`, `9077`) directly from spatial image coordinates inside symbol bubbles.
* **Piping Line Sizes & Specs**: Parses nominal line sizes (`8"`, `6"`, `4"`), service codes (`PV`, `VF`, `DC`), and piping specs (`FC11S`, `GC11S`, `AS20S`).
* **Valve Specifications**: Detects valve types (`Check Valve`, `Gate Valve`, `Control Valve`) and pressure rating classes (`150#`, `300#`, `2500#`).

---

### ⚡ 2. High-Performance Parallel Perception Sub-Graph
Features 3 dedicated, parallel perception agents running concurrently:
* 🔤 **TextRecognitionAgent**: 2-Layer OCR Reading & Deep Reasoning Engine (Pathnovo ISA 5.1 OCR, PaddleOCR, PyMuPDF, Qwen 3.7-VL, Gemini).
* 🎯 **SymbolRecognitionAgent**: Component & Symbol Detector (Pathnovo ISA 5.1 Engine, Multimodal VLM, RF-DETR).
* ⚡ **PipelineRecognitionAgent**: Topological Connectivity & Line Spec Tracer (Pathnovo Line & Loop Tracer, OpenCV CV Line Tracer + VLM).

---

### 🚀 3. Ultra-Fast Performance & Latency Elimination
* **0.052s Ingestion Agent**: Pre-rasterized page caching and sub-crop title block OCR.
* **13.78s Total Pipeline Execution**: Latency optimization reducing total pipeline runtime from 11m49s to 13.78 seconds.
* **Auto-Routing Vision Models**: Automatically remaps text-only LLM requests to multimodal vision models (`qwen/qwen-3.7-vl`).

---

### 📦 4. Multi-Platform Deliverables & Export System
Extracts digital twins directly into standard engineering formats:
* 📊 **Excel Workbook (`.xlsx`)**: Styled multi-tab workbook with auto-fitted columns and revision history delta highlighting.
* 🕸️ **Master JSON Graph (`.json`)**: Hierarchical Pydantic schema representation of the entire drawing network.
* 📐 **AVEVA Diagrams / SP3D XML (`.xml`)**: Complete XML plant model schema compliant with AVEVA and Smart 3D import requirements.
* 🔧 **Siemens COMOS JSON (`.json`)**: Hierarchical `Project -> Unit -> Location -> Object` tree formatting.
* 🗃️ **SmartPlant P&ID CSV (`.csv`)**: Relational database import format with standardized headers.

---

## 🛠️ Setup & Execution Guide

### 1. Prerequisites
* **Python**: 3.11, 3.12, or 3.13
* **OS**: Windows, macOS, or Linux

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/AbhinavEliac/MTO2Doc.git
cd pid_project

# Activate virtual environment
# Windows:
pid_env\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Launch Interactive Dashboard
```bash
streamlit run app.py
```

---

## 📞 Author & Contact

**Developer**: Abhinav Gupta  
**Email**: [abhinavgupta15.ag@gmail.com](mailto:abhinavgupta15.ag@gmail.com)  

---

<p align="center">
  <i>Built with ❤️ using Python, LangGraph, Streamlit, Pathnovo ISA 5.1 API, OpenRouter Qwen 3.7 VL, and Google Gemini.</i>
</p>
