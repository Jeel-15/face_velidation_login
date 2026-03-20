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

RUN git clone --depth 1 https://github.com/davisking/dlib.git && \
    find /app/dlib -name "CMakeLists.txt" -exec \
    sed -i 's/cmake_minimum_required(VERSION 2\.8/cmake_minimum_required(VERSION 3.5/g' {} \; && \
    cd dlib && \
    DLIB_NO_GUI_SUPPORT=1 python setup.py install --set DLIB_NO_GUI_SUPPORT=ON && \
    cd .. && rm -rf dlib

COPY requirements.txt .
RUN grep -vi "dlib" requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY . .

CMD ["python", "app.py"]
