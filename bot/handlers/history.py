import html

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from bot.keyboards.history import HISTORY_PER_PAGE, history_card_kb, history_list_kb
from bot.states.callbacks import HistoryCallback, MainMenuCallback
from bot.utils.screens import safe_callback_answer, show_screen
from shared.db.session import run_in_session
from shared.services.history import get_call_history_item, list_call_history
from shared.services.users import get_user_id


router = Router()

HISTORY_TEXT = (
    '📋 <b>История звонков</b>\n\n'
    'Последние звонки отсортированы от новых к старым.\n\n'
    'Показано: {shown_from}-{shown_to} из {total}'
)

EMPTY_HISTORY_TEXT = (
    '📋 <b>История звонков</b>\n\n'
    'Пока здесь пусто.'
)

HISTORY_CARD_TEXT = (
    '📞 <b>{title}</b>\n\n'
    'Статус: <b>{status}</b>\n'
    'Начало: <code>{started_at}</code>\n'
    'Завершён: <code>{ended_at}</code>\n'
    'Длительность: <code>{duration}</code>\n\n'
    '{participants}'
)


def _normalize_page(page: int, total: int) -> int:
    if total <= 0:
        return 0

    max_page = (total - 1) // HISTORY_PER_PAGE
    return max(0, min(page, max_page))


def _participants_text(item: dict) -> str:
    if item['is_direct'] and item.get('other_user') is not None:
        other_user = item['other_user']
        username = f'@{other_user.username}' if other_user.username else 'без ника'
        return (
            'Собеседник:\n'
            f'<b>{html.escape(other_user.display_name)}</b>\n'
            f'<code>{html.escape(username)}</code>'
        )

    users = item.get('other_users') or []
    if not users:
        return 'Участники: групповой звонок'

    return 'Участники:\n' + '\n'.join(
        f'• {html.escape(user.display_name)}'
        for user in users
    )


async def show_history_list(
    message: types.Message,
    state: FSMContext,
    user_id: int,
    page: int = 0,
) -> None:
    items = run_in_session(
        lambda session: list_call_history(session=session, user_id=user_id)
    )

    page = _normalize_page(page, len(items))

    if not items:
        caption = EMPTY_HISTORY_TEXT
    else:
        caption = HISTORY_TEXT.format(
            shown_from=page * HISTORY_PER_PAGE + 1,
            shown_to=min((page + 1) * HISTORY_PER_PAGE, len(items)),
            total=len(items),
        )

    await show_screen(
        message=message,
        state=state,
        caption=caption,
        reply_markup=history_list_kb(items=items, page=page),
    )


async def show_history_card(
    message: types.Message,
    state: FSMContext,
    user_id: int,
    call_id: int,
    page: int = 0,
) -> None:
    item = run_in_session(
        lambda session: get_call_history_item(
            session=session,
            user_id=user_id,
            call_id=call_id,
        )
    )

    if item is None:
        await show_history_list(
            message=message,
            state=state,
            user_id=user_id,
            page=page,
        )
        return

    await show_screen(
        message=message,
        state=state,
        caption=HISTORY_CARD_TEXT.format(
            title=html.escape(item['title']),
            status=html.escape(item['status_text']),
            started_at=item['call_started_at_text'],
            ended_at=item['ended_at_text'],
            duration=item['duration_text'],
            participants=_participants_text(item),
        ),
        reply_markup=history_card_kb(item=item, page=page),
    )


@router.callback_query(MainMenuCallback.filter(F.action == 'history'))
async def history_entry_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    user = run_in_session(
        lambda session: get_user_id(session, callback.from_user.id)
    )

    if not user:
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    await show_history_list(
        message=callback.message,
        state=state,
        user_id=user.id,
    )


@router.callback_query(HistoryCallback.filter(F.action.in_({'list', 'card'})))
async def history_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    callback_data: HistoryCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    user = run_in_session(
        lambda session: get_user_id(session, callback.from_user.id)
    )

    if not user:
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Пользователь не найден. Нажмите /start.',
        )
        return

    if callback_data.action == 'list' or callback_data.call_id is None:
        await show_history_list(
            message=callback.message,
            state=state,
            user_id=user.id,
            page=callback_data.page,
        )
        return

    await show_history_card(
        message=callback.message,
        state=state,
        user_id=user.id,
        call_id=callback_data.call_id,
        page=callback_data.page,
    )
