FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости отдельным слоем: правка кода не пересобирает их заново.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Бот работает от непривилегированного пользователя.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

CMD ["sh", "-c", "alembic upgrade head && python -m bot"]
