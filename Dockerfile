# ==============================================================================
# Multi-Stage Dockerfile for SID-AI P&ID / Engineering Diagram Extraction
#
# Stage 1 (Builder): "Heavy" Python 3.13 (Debian Bookworm) with complete C/C++
#                   compilers, CMake, and build tools to compile and install
#                   heavy dependencies (PyTorch, EasyOCR, PaddlePaddle, OpenCV).
#
# Stage 2 (Runner) : "Slim" Python 3.13 (Debian Bookworm Slim) containing only
#                   shared runtime libraries (libgl1, libgomp1, poppler-utils)
#                   and copying the pre-compiled virtualenv for a lightweight,
#                   secure production container.
# ==============================================================================

ARG BUILDER_IMAGE=python:3.13-bookworm
ARG RUNNER_IMAGE=python:3.13-slim-bookworm

# ── Stage 1: Heavy Build Environment ──────────────────────────────────────────
FROM ${BUILDER_IMAGE} AS builder

# Stop interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install C/C++ build tools and system headers needed by binary wheels & extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    cmake \
    pkg-config \
    libgl1-mesa-dev \
    libglib2.0-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Create isolated Python virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade core packaging tools
RUN pip install --upgrade pip setuptools wheel

# Install all Python dependencies inside the virtual environment
WORKDIR /build
COPY requirements.txt .

RUN pip install -r requirements.txt


# ── Stage 2: Minimal Slim Runtime ─────────────────────────────────────────────
FROM ${RUNNER_IMAGE} AS runner

LABEL maintainer="SID-AI Engineering Team" \
      description="Production multi-stage runtime for SID-AI engineering diagram extraction" \
      version="1.0.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Application Paths
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    # Model Cache Locations
    TORCH_HOME="/app/models/torch" \
    EASYOCR_MODULE_PATH="/app/models/easyocr" \
    # Streamlit Headless Configuration
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Install only the required shared runtime libraries:
# - libgl1, libglib2.0-0, libsm6, libxext6, libxrender1 : OpenCV & PaddleOCR image processing
# - libgomp1                                              : OpenMP runtime for PyTorch / Paddle
# - poppler-utils                                         : pdf2image PDF rendering
# - fonts-dejavu-core                                     : Diagram text and overlay annotation fonts
# - curl                                                  : Streamlit healthcheck probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    poppler-utils \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from Stage 1
COPY --from=builder /opt/venv /opt/venv

# Set up application workspace
WORKDIR /app

# Create directory structure for data persistence, caches, and models
RUN mkdir -p \
    /app/uploads \
    /app/outputs \
    /app/models/torch \
    /app/models/easyocr

# Create a non-root user for security best practices
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /app /opt/venv

# Copy application source code
COPY --chown=appuser:appuser . /app

# Switch to non-root user
USER appuser

# Expose Streamlit dashboard port
EXPOSE 8501

# Healthcheck probe to monitor Streamlit readiness
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default runtime entrypoint
ENTRYPOINT ["streamlit", "run", "app.py"]
CMD ["--server.port=8501", "--server.address=0.0.0.0"]
