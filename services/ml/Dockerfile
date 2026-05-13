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

# onnxruntime-gpu (CUDA 12 / cuDNN 9) also needs cuRAND and cuFFT at runtime.
# Install all CUDA 12 deps as pip wheels so they live in a predictable path
# we can register with the dynamic loader below.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir \
        nvidia-cuda-runtime-cu12 \
        nvidia-cublas-cu12 \
        nvidia-cudnn-cu12 \
        nvidia-curand-cu12 \
        nvidia-cufft-cu12

# Make pip-installed CUDA libs visible to onnxruntime-gpu and other native libs
# that use dlopen (libcublas, libcudnn, libcurand, libcufft, libcudart).
RUN echo "/opt/conda/lib/python3.11/site-packages/nvidia/cublas/lib" > /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/cudnn/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/cuda_runtime/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/curand/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    echo "/opt/conda/lib/python3.11/site-packages/nvidia/cufft/lib" >> /etc/ld.so.conf.d/pip-nvidia.conf && \
    ldconfig

# Application code
COPY . .

EXPOSE 8000

HEALTHCHECK --start-period=300s --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/api/v1/health').raise_for_status()"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
