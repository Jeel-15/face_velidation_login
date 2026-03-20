FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip setuptools packaging

RUN git clone https://github.com/davisking/dlib.git && \
    sed -i 's/cmake_minimum_required(VERSION 2.8.12)/cmake_minimum_required(VERSION 3.5)/' /app/dlib/dlib/external/pybind11/CMakeLists.txt && \
    cd dlib && \
    python setup.py install && \
    cd .. && rm -rf dlib

COPY requirements.txt .

RUN grep -v "dlib" requirements.txt > requirements_nodlib.txt && \
    pip install --no-cache-dir -r requirements_nodlib.txt

COPY . .

CMD ["python", "app.py"]
