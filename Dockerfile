FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pandas openpyxl

COPY . .

EXPOSE 8000

CMD ["python", "server/server.py", "--host", "0.0.0.0", "--port", "8000"]