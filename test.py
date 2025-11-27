# test_schedule.py (КОМІТ 2 - Базові тести)
import pytest
import pandas as pd
import os
import datetime
from datetime import timedelta
# Імпортуємо необхідні класи та функції з основного файлу bot.py
from bot import ScheduleSystem, time_to_minutes, COL_GROUP, COL_DAY, COL_TIME, COL_SUBJECT, REMINDER_MINUTES
# Імпортуємо модуль datetime, як він використовується в bot.py, щоб підмінити його
import bot # Імпортуємо модуль bot для підміни

# Вказуємо шлях до тестових даних
TEST_FILE = 'temp_test_data.csv'

# Головний фікстура: налаштування та очищення
@pytest.fixture(scope="session")
def setup_teardown_data():
    """Створює тимчасовий тестовий файл та об'єкт ScheduleSystem."""
    # Тестові дані з парами, які свідомо записані у неправильному порядку (12:20 перед 8:40)
    test_data = f"{COL_GROUP},{COL_DAY},{COL_TIME},{COL_SUBJECT}\n" + \
                "ІПС-21,ПОНЕДІЛОК,12:20,ООП (лек)\n" + \
                "ІПС-21,ПОНЕДІЛОК,8:40,Дискретна математика (пр)\n" + \
                "ІПС-21,ПОНЕДІЛОК,14:00,Філософія (лек)\n" + \
                "ІПС-22,ПОНЕДІЛОК,14:00,Філософія (лек)\n" + \
                "ІПС-22,СЕРЕДА,10:35,Алгоритми (пр)\n"

    # Створюємо тимчасовий файл
    with open(TEST_FILE, 'w', encoding='utf-8') as f:
        f.write(test_data)

    # Створюємо об'єкт ScheduleSystem на основі тестових даних
    schedule = ScheduleSystem(TEST_FILE)

    yield schedule

    # Очищаємо за собою (видаляємо тестовий файл після завершення)
    if os.path.exists(TEST_FILE):
        os.remove(TEST_FILE)


# --- ТЕСТОВІ ФУНКЦІЇ ---

def test_time_conversion():
    """Перевірка коректності перетворення часу для сортування (критичний fix)."""
    assert time_to_minutes("8:40") == 520
    assert time_to_minutes("10:35") == 635
    assert time_to_minutes("12:20") == 740
    assert time_to_minutes("") == -1
    assert time_to_minutes("??") == -1

def test_group_list(setup_teardown_data):
    """Перевірка, чи клас правильно знаходить всі унікальні групи."""
    expected_groups = ['ІПС-21', 'ІПС-22']
    assert sorted(setup_teardown_data.get_groups_list()) == expected_groups

def test_schedule_sorting_is_correct(setup_teardown_data):
    """Тестує, чи розклад повертається у правильному хронологічному порядку."""

    df_monday = setup_teardown_data.df[setup_teardown_data.df[COL_DAY] == 'ПОНЕДІЛОК']

    df_sorted = setup_teardown_data.filter_schedule_and_sort(df_monday)

    # Очікуваний порядок часу: 8:40, 12:20, 14:00, 14:00
    sorted_times = df_sorted[COL_TIME].tolist()

    assert sorted_times == ['8:40', '12:20', '14:00', '14:00']

    def test_get_schedule_output_format(setup_teardown_data):
        """
        Тестує, чи метод get_schedule повертає коректний, відформатований рядок.
        """
        result = setup_teardown_data.get_schedule('ІПС-21', 'ПОНЕДІЛОК')

        # Перевіряємо ключові елементи у вихідному рядку:
        assert 'ПОНЕДІЛОК (ІПС-21)' in result
        assert '⏰ **8:40** — Дискретна математика (пр)\n' in result
        assert '⏰ **12:20** — ООП (лек)\n' in result
        assert '⏰ **14:00** — Філософія (лек)\n' in result
        assert '??? — ' not in result

    def test_check_upcoming_no_alert(setup_teardown_data, monkeypatch):
        """
        Тестує, чи метод check_upcoming не видає нагадування, якщо час не збігається.
        """
        # Встановлюємо поточний час на 10:00 (Понеділок, далеко від будь-якої пари)
        test_time = datetime.datetime(2025, 11, 24, 10, 0, 0)  # Дата - Понеділок!

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return test_time

        # Підміняємо сам клас datetime у модулі bot.datetime
        monkeypatch.setattr(bot.datetime, 'datetime', MockDatetime)

        # Пари, що починаються о 10:05 (10:00 + 5 хв)
        alerts = setup_teardown_data.check_upcoming(minutes=REMINDER_MINUTES)

        # Очікуємо порожній список нагадувань
        assert alerts == []

    def test_check_upcoming_success(setup_teardown_data, monkeypatch):
        """
        Тестує, чи метод check_upcoming правильно генерує нагадування за 5 хв до пари 8:40.
        """
        # Встановлюємо поточний час на 8:35 (Понеділок, 5 хв до 8:40)
        test_time = datetime.datetime(2025, 11, 24, 8, 35, 0)  # Дата - Понеділок!

        class MockDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return test_time

        # Підміняємо сам клас datetime у модулі bot.datetime
        monkeypatch.setattr(bot.datetime, 'datetime', MockDatetime)

        # Пари, що починаються о 8:40 (8:35 + 5 хв)
        alerts = setup_teardown_data.check_upcoming(minutes=REMINDER_MINUTES)

        # Очікувані нагадування:
        expected_alert = ('ІПС-21', '🔔 **Нагадування (за 5 хв)!**\n⏰ 8:40 — Дискретна математика (пр)')

        # Перевіряємо, чи нагадування було згенеровано
        assert expected_alert in alerts
        assert len(alerts) == 1