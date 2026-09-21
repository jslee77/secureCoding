FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 최초 실행 시 DB가 없으면 시드
RUN python -m app.seed

EXPOSE 5000
CMD ["python", "run.py"]
