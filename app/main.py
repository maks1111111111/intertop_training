import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.database import initialize_database
from app.handlers import courses, start
from app.services.course_sync import sync_courses

def _get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


async def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. "
            "Скопируйте .env.example в .env и укажите токен."
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    project_dir = _get_base_dir()
    base_dir = project_dir / "courses"
    db_path = project_dir / "data" / "training.db"

    initialize_database(db_path)
    sync_courses(
    base_dir=base_dir,
    db_path=db_path,
)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    dp["base_dir"] = base_dir
    dp["db_path"] = db_path

    dp.include_router(start.router)
    dp.include_router(courses.router)

    logging.info("База данных подготовлена: %s", db_path)
    logging.info("Бот запущен. Каталог курсов: %s", base_dir)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())