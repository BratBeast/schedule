import asyncio
import logging
import pandas as pd
import datetime
from datetime import timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

API_TOKEN = '8271049801:AAEn8wu3eMezPeF1L1Ml64FMhOPTc5jwy3E'
FILE_NAME = 'schedule.csv'

COL_GROUP = 'Група'
COL_DAY = 'День'
COL_TIME = 'Час'
COL_SUBJECT = 'Предмет'
REMINDER_MINUTES = 5  # Нагадування за 5 хвилин до початку пари

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def time_to_minutes(time_str):
    """
    Конвертує час 'H:MM' або 'HH:MM' у хвилини для коректного ЧИСЛОВОГО сортування.
    """
    try:
        if pd.isna(time_str) or time_str == '':
            return -1
        time_str = str(time_str).replace('.', ':')
        h, m = map(int, time_str.split(':'))
        return h * 60 + m
    except:
        return -1


# ================= 1. BACKEND: РОБОТА З ДАНИМИ =================
class ScheduleSystem:
    def __init__(self, file_path):
        self.df = self._load_data(file_path)

    def _load_data(self, file_path):
        encodings = ['utf-8', 'cp1251', 'windows-1251', 'utf-8-sig']
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, header=0, encoding=enc, sep=None, engine='python')
                df = df.ffill().astype(str)
                for col in df.columns:
                    df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
                logging.info(f"✅ Файл успішно відкрито! (Кодування: {enc})")
                return df
            except Exception:
                continue
        logging.error("❌ Не вдалось відкрити файл жодним способом.")
        return pd.DataFrame()

    def get_groups_list(self):
        if self.df.empty or COL_GROUP not in self.df.columns: return []
        return sorted(self.df[COL_GROUP].unique().tolist())

    def filter_schedule_and_sort(self, filtered_df):
        """
        Фільтрує розклад (видаляючи теги тижнів, щоб вони не заважали) та сортує його ЧИСЛОВО за часом.
        """

        # Ми видалили логіку тижнів, але залишаємо сортування
        combined_df = filtered_df.copy().drop_duplicates()

        return combined_df.sort_values(
            by=COL_TIME,
            key=lambda col: col.apply(time_to_minutes),
            ascending=True
        )

    def get_schedule(self, group, day):
        if self.df.empty: return "Помилка файлу. Не вдалося завантажити розклад."

        filtered = self.df[
            (self.df[COL_GROUP] == group) &
            (self.df[COL_DAY].str.contains(day, case=False, na=False))
            ]

        sorted_df = self.filter_schedule_and_sort(filtered)

        if sorted_df.empty: return f"📅 **{day} ({group})**: Пар немає. 🎉"

        text = f"📅 **{day} ({group})**:\n"
        for _, row in sorted_df.iterrows():
            subject = row.get(COL_SUBJECT, '')
            subject_clean = subject.replace('(Непарний)', '').replace('(Парний)', '').strip()
            text += f"⏰ **{row.get(COL_TIME, '???')}** — {subject_clean}\n"
        return text

    def check_upcoming(self, minutes=REMINDER_MINUTES):
        if self.df.empty: return []
        now = datetime.datetime.now()
        days_map = {
            0: "ПОНЕДІЛОК", 1: "ВІВТОРОК", 2: "СЕРЕДА", 3: "ЧЕТВЕР", 4: "П'ЯТНИЦЯ"
        }
        current_day = days_map.get(now.weekday())

        if not current_day: return []

        target_datetime = now + timedelta(minutes=minutes)
        target_time = target_datetime.strftime("%H:%M")

        matches = self.df[
            (self.df[COL_DAY] == current_day) &
            (self.df[COL_TIME] == target_time)
            ]

        matches_sorted = self.filter_schedule_and_sort(matches)

        alerts = []
        for _, row in matches_sorted.drop_duplicates(subset=[COL_GROUP, COL_SUBJECT]).iterrows():
            # Нагадування має бути чистим, тому тут видаляємо теги тижнів
            subject = row[COL_SUBJECT].replace('(Непарний)', '').replace('(Парний)', '').strip()
            alerts.append((row[COL_GROUP], f"🔔 **Нагадування (за {minutes} хв)!**\n⏰ {row[COL_TIME]} — {subject}"))

        return alerts


# ================= 2. УПРАВЛІННЯ КОРИСТУВАЧАМИ =================
# user_registry: {user_id: {'group': 'ІПС-21', 'reminders': True}}
user_registry = {}

# ================= 3. FRONTEND: БОТ ТА ІНТЕРФЕЙС =================
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
schedule = ScheduleSystem(FILE_NAME)
scheduler = AsyncIOScheduler()


# --- СТАНИ ---
class St(StatesGroup):
    selecting_group = State()
    selecting_reminders = State()


# --- КЛАВІАТУРИ ---

def kb_days():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="ПОНЕДІЛОК"), KeyboardButton(text="ВІВТОРОК")],
        [KeyboardButton(text="СЕРЕДА"), KeyboardButton(text="ЧЕТВЕР"), KeyboardButton(text="П'ЯТНИЦЯ")],
        [KeyboardButton(text="⚙️ Налаштування нагадувань"), KeyboardButton(text="🚪 Змінити групу")]
    ], resize_keyboard=True)


def kb_groups():
    groups = schedule.get_groups_list()
    keyboard = [[KeyboardButton(text=g)] for g in groups]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def kb_reminders():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="✅ Увімкнути нагадування")],
        [KeyboardButton(text="❌ Вимкнути нагадування")],
        [KeyboardButton(text="⬅️ Назад до розкладу")]
    ], resize_keyboard=True)


# --- ХЕНДЛЕРИ ---

@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext):
    await msg.answer("👋 Ласкаво прошу! Оберіть свою групу:", reply_markup=kb_groups())
    await state.set_state(St.selecting_group)


@dp.message(F.text == "🚪 Змінити групу")
async def change_group(msg: types.Message, state: FSMContext):
    await start_cmd(msg, state)


@dp.message(St.selecting_group)
async def process_group_choice(msg: types.Message, state: FSMContext):
    group = msg.text
    if group not in schedule.get_groups_list():
        await msg.answer("Будь ласка, оберіть групу кнопкою!")
        return

    user_registry[msg.from_user.id] = user_registry.get(msg.from_user.id, {'reminders': False})
    user_registry[msg.from_user.id]['group'] = group

    await msg.answer(
        f"🎉 Група **{group}** збережена!\n\nЧи бажаєте ви отримувати нагадування про пари за {REMINDER_MINUTES} хвилин до початку?",
        reply_markup=kb_reminders(), parse_mode="Markdown")
    await state.set_state(St.selecting_reminders)


@dp.message(St.selecting_reminders, F.text.in_({"✅ Увімкнути нагадування", "❌ Вимкнути нагадування"}))
async def process_reminders_choice(msg: types.Message, state: FSMContext):
    user_id = msg.from_user.id

    if msg.text == "✅ Увімкнути нагадування":
        user_registry[user_id]['reminders'] = True
        status = "УВІМКНЕНО"
    else:
        user_registry[user_id]['reminders'] = False
        status = "ВИМКНЕНО"

    await msg.answer(f"Нагадування **{status}**.\nМожеш перевіряти свій розклад!",
                     reply_markup=kb_days(), parse_mode="Markdown")
    await state.clear()


@dp.message(F.text == "⚙️ Налаштування нагадувань")
async def settings_reminders(msg: types.Message, state: FSMContext):
    grp = user_registry.get(msg.from_user.id, {}).get('group')
    if not grp:
        await msg.answer("Спочатку обери групу через /start")
        return

    status = "УВІМКНЕНО" if user_registry[msg.from_user.id]['reminders'] else "ВИМКНЕНО"
    await msg.answer(f"Ваша група: **{grp}**.\nНагадування: **{status}**.\nОберіть дію:",
                     reply_markup=kb_reminders(), parse_mode="Markdown")
    await state.set_state(St.selecting_reminders)


@dp.message(F.text.in_({"ПОНЕДІЛОК", "ВІВТОРОК", "СЕРЕДА", "ЧЕТВЕР", "П'ЯТНИЦЯ"}))
async def get_sch(msg: types.Message):
    grp = user_registry.get(msg.from_user.id, {}).get('group')
    if not grp:
        await msg.answer("Спочатку обери групу через /start", reply_markup=kb_groups())
        return
    await msg.answer(schedule.get_schedule(grp, msg.text), parse_mode="Markdown")


# --- ФОНОВІ НАГАДУВАННЯ ---

async def job():
    """Перевіряє розклад і надсилає нагадування користувачам, які їх увімкнули."""

    alerts = schedule.check_upcoming()

    if not alerts:
        logging.debug("Немає запланованих нагадувань.")
        return

    for grp, txt in alerts:
        for uid, user_data in user_registry.items():
            if user_data.get('group') == grp and user_data.get('reminders') is True:
                try:
                    await bot.send_message(uid, txt, parse_mode="Markdown")
                    logging.info(f"Надіслано нагадування користувачу {uid} (Група: {grp})")
                except Exception as e:
                    logging.error(f"Помилка надсилання нагадування користувачу {uid}: {e}")


async def main():
    scheduler.add_job(job, "interval", minutes=1)  # Перевіряємо щохвилини
    scheduler.start()
    logging.info("Бот запущено! Планувальник нагадувань активний.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())