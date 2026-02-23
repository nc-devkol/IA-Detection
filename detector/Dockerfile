FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Python 3.11 from deadsnakes + ffmpeg + system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
  && add-apt-repository -y ppa:deadsnakes/ppa \
  && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-distutils \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    curl \
  && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
  && ln -sf /usr/bin/python3.11 /usr/bin/python \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONPATH=/app
CMD ["python", "-m", "app.main"]