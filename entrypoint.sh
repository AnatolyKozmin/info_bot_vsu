#!/bin/sh
set -e

# Ждём, пока база будет доступна
echo "Ожидание запуска PostgreSQL..."
until pg_isready -h db -p 5432 -U vshu; do
  sleep 2
done

echo "Применяем миграции..."
python migrate.py

echo "Запуск бота..."
exec python main.py
