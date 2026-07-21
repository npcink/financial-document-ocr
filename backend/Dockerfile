FROM node:26-alpine AS frontend-build

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.14-slim

WORKDIR /app

LABEL org.opencontainers.image.licenses="GPL-3.0-only"

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

COPY backend/app/ ./app/
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=frontend-build /frontend/dist/ ./static/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
