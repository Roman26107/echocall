import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher

from bot.handlers.start import router as start_router
from bot.handlers.call import router as call_router
from bot.handlers.contacts import router as contacts_router
from bot.handlers.history import router as history_router
from bot.handlers.profile import router as profile_router
from bot.handlers.settings import router as settings_router
from bot.handlers.blacklist import router as blacklist_router
from bot.handlers.admin import router as admin_router
from bot.handlers.navigation import router as navigation_router
from settings import BOT_TOKEN, SYSTEM_METRICS_INTERVAL_SECONDS
from shared.db.session import init_db
from shared.db.session import run_in_session
from shared.services.monitoring import collect_local_system_metrics, record_system_status


logger = logging.getLogger(__name__)


async def collect_system_metrics_forever() -> None:
    while True:
        try:
            sample = await asyncio.to_thread(collect_local_system_metrics, 'foreign')
            await asyncio.to_thread(
                run_in_session,
                lambda session: record_system_status(session, sample),
                commit=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Periodic system metrics collection failed')
        await asyncio.sleep(SYSTEM_METRICS_INTERVAL_SECONDS)


async def main():
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN is not configured')

    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(call_router)
    dp.include_router(contacts_router)
    dp.include_router(history_router)
    dp.include_router(profile_router)
    dp.include_router(settings_router)
    dp.include_router(blacklist_router)
    dp.include_router(admin_router)
    dp.include_router(navigation_router)
    metrics_task = asyncio.create_task(collect_system_metrics_forever())

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        metrics_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await metrics_task
        await bot.session.close()


if __name__ == '__main__':
    asyncio.run(main())
