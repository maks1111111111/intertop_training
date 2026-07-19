import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.database.database import init_db
from app.handlers import courses, start


def _get_base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


async def main() -> None:
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    base_dir = _get_base_dir()
    init_db(base_dir)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp["base_dir"] = base_dir

    dp.include_router(start.router)
    dp.include_router(courses.router)

    logging.info("Бот запущен. Каталог курсов: %s", base_dir / "courses")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
