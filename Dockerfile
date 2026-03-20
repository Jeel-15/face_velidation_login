FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip setuptools packaging

RUN pip install --no-cache-dir \
    "dlib==19.22.1" \
    --find-links https://github.com/z-mahmud22/Dlib_Windows_Python3.x/releases/download/v1.0/dlib-19.22.1-cp311-cp311-linux_x86_64.whl

COPY requirements.txt .

RUN grep -v "dlib" requirements.txt > requirements_nodlib.txt && \
    pip install --no-cache-dir -r requirements_nodlib.txt

COPY . .

CMD ["python", "app.py"]
