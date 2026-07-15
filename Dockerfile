FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc tzdata curl && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://get.docker.com | sh

ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "-m", "app.main"]
