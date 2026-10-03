FROM python:3.11-slim

WORKDIR /app

# 複製程式碼與資源
COPY . /app

# 設定 Render 傳入的 PORT 環境變數，預設 10000
ENV PORT=10000

EXPOSE 10000

CMD ["python", "server.py"]
