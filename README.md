# 🤖 Schedule Bot (Telegram)

## Опис проєкту
Цей бот призначений для надання розкладу занять та автоматичних нагадувань студентам через Telegram.

## Технології
* Python
* aiogram (для Telegram API)
* pandas (для роботи з розкладом)
* apscheduler (для планування нагадувань)

## Запуск
1. Встановіть залежності: `pip install aiogram pandas apscheduler`
2. Оновіть `API_TOKEN` у файлі `bot.py`.
3. Запустіть бота: `python bot.py`

## Тестування
Для запуску тестів:
1. Встановіть pytest: `pip install pytest`
2. Запустіть тести: `pytest`