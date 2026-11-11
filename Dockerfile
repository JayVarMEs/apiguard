FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt package.json ./
RUN pip install --no-cache-dir -r requirements.txt && npm install --omit=dev --no-audit --no-fund
COPY src ./src
COPY config ./config
COPY models ./models
COPY demo/specs ./demo/specs
COPY demo_ui ./demo_ui
ENV PYTHONPATH=src HOST=0.0.0.0 PORT=8765
EXPOSE 8765
CMD ["python", "demo_ui/app.py"]
