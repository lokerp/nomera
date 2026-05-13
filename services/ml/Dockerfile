# syntax=docker/dockerfile:1
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

WORKDIR /app

# System dependencies for OpenCV and turbojpeg
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    libturbojpeg \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Make pip-installed CUDA libs (nvidia-cublas-cu12, nvidia-cudnn-cu12, etc.)
# visible to onnxruntime-gpu and other native libs that use dlopen.
RUN echo "/opt/conda/lib/python3.11/site-packages/nvidia/cublas/lib" > /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/cudnn/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/cuda_runtime/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    ldconfig

# Application code
COPY . .

# Pre-download models at build time (optional, speeds up cold start)
# RUN python -c "from nomeroff_net import pipeline; pipeline('number_plate_detection_and_reading')"

EXPOSE 8000

HEALTHCHECK --start-period=300s --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
