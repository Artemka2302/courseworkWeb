FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для matplotlib
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Создаём папки для базы данных и загрузок
RUN mkdir -p instance uploads

# Открываем порт
EXPOSE 5000

ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Команда для запуска (инициализация БД + запуск)
CMD sh -c "python -c \"from app import app, db; app.app_context().push(); db.create_all()\" && gunicorn --bind 0.0.0.0:5000 app:app"