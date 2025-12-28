FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Optimize PyTorch CPU performance
ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
ENV OPENBLAS_NUM_THREADS=4

WORKDIR /app

# Install dependencies
COPY requirements.txt .
# Install CPU-only PyTorch first to avoid downloading huge CUDA libs
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install chromium
# Install Playwright dependencies and Tesseract OCR
# Install Playwright dependencies, Tesseract OCR, and system libs for PaddleOCR
RUN playwright install-deps chromium

# Install VNC and X11 dependencies
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    fluxbox \
    xterm \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY src/ ./src/
COPY manual_login.py ./
COPY vnc_login.sh ./
COPY run_bot_vnc.sh ./
COPY entrypoint.sh ./
RUN chmod +x vnc_login.sh run_bot_vnc.sh entrypoint.sh

# Create directories for persistent data
RUN mkdir -p /app/data/screenshots /app/data/sessions

# Set environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Run the bot with gallery server
CMD ["./entrypoint.sh"]
