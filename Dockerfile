FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && \
    CMAKE_ARGS="-DCMAKE_POLICY_VERSION_MINIMUM=3.5" pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```
> Replace `app.py` with your actual start file (e.g. `main.py`, `wsgi.py`, etc.)

---

## Step 2: Configure Render to use Docker

1. Go to your Render service → **Settings**
2. Under **Environment**, change from **Python** → **Docker**
3. Leave **Dockerfile Path** as `./Dockerfile`
4. Click **Save Changes** and redeploy

---

## Step 3: Make sure your `requirements.txt` has these pinned versions
```
dlib==19.24.2
face-recognition==1.3.0
face-recognition-models==0.3.0
