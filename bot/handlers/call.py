import asyncio
import html

from aiogram import F, types, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext

from bot.states.callbacks import MainMenuCallback, CallCallback
from bot.states.fsm import CallState
from bot.keyboards.call import (
    call_username_kb,
    user_not_found_kb,
    call_user_card_kb,
    call_kb,
    active_call_exists_kb,
    back_and_main_kb,
    call_finished_kb,
    confirm_remove_finished_contact_kb,
    confirm_remove_user_contact_kb,
)
from bot.utils.screens import (
    show_screen,
    delete_user_message,
    safe_callback_answer,
)
from shared.db.session import run_in_session
from shared.services.users import get_user_username, get_user_id
from shared.services.calls import (
    start_call,
    decline_call_user,
    get_call_status,
    leave_or_end_call_by_user,
    save_participant_screen_by_token,
    get_call_finished_context,
    get_latest_participant_screen,
)
from shared.services.contacts import (
    add_contact,
    remove_contact,
    add_favorite,
    remove_favorite,
    list_contact_users,
)
from settings import DOMAIN
from shared.exceptions import (
    ActiveCallExistsError,
    CallError,
    IncomingCallForbiddenError,
    CallNotFoundError,
    ParticipantNotFoundError,
)

router = Router()

CALL_USERNAME_TEXT = (
    'Выберите контакт из избранного\n'
    'или введите ник 👇'
)

USER_NOT_FOUND_TEXT = (
    '❌ Пользователь не найден\n\n'
    'Проверьте правильность ника и попробуйте снова\n\n'
    'Если пользователя ещё нет в боте,\n'
    'вы можете пригласить его👇'
)

CALL_USER_CARD_TEXT = (
    'Нашли пользователя 👤\n\n'
    '<b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    'Готовы позвонить? 📞'
)

USER_NOT_FOUND_ERROR_TEXT = (
    '⚠️ Пользователь больше недоступен\n\n'
    'Перейдите в главное меню и попробуйте снова'
)

CONFIRM_REMOVE_FINISHED_CONTACT_TEXT = (
    '⚠️ Вы уверены, что хотите удалить пользователя\n\n'
    '<b>{display_name}</b>\n'
    '<code>{username}</code>\n\n'
    'из контактов?'
)

INCOMING_CALL_NOTIFICATION_TEXT = (
    '🔔 <b>Вам звонят!</b>\n\n'
    '📞 <b>{display_name}</b> хочет созвониться с вами.\n\n'
    'Откройте сообщение звонка ниже, чтобы ответить или отклонить вызов.'
)

incoming_notification_tasks: dict[int, asyncio.Task] = {}


def get_favorite_contacts(user_id: int):
    return run_in_session(
        lambda session: list_contact_users(
            session=session,
            user_id=user_id,
            favorites_only=True,
        )
    )


async def show_call_username_screen(
        message: types.Message,
        state: FSMContext,
        user_id: int,
        page: int = 0,
) -> None:
    await state.set_state(CallState.username)
    await state.update_data(call_favorites_page=page)

    await show_screen(
        message=message,
        state=state,
        caption=CALL_USERNAME_TEXT,
        reply_markup=call_username_kb(
            favorites=get_favorite_contacts(user_id),
            page=page,
        ),
    )


def build_call_finished_text(action: str, context: dict) -> str:
    action_titles = {
        'cancel': '❌ Звонок отменён.',
        'decline': '📵 Звонок отклонён.',
        'end': '📴 Звонок завершён.',
        'updated': '✅ Готово.',
    }

    title = action_titles.get(action, '📴 Звонок завершён.')

    if context.get('is_direct') and context.get('other_user'):
        other_user = context['other_user']
        username = f'@{other_user.username}' if other_user.username else 'без ника'

        return (
            f'{title}\n\n'
            'Собеседник:\n'
            f'<b>{html.escape(other_user.display_name)}</b>\n'
            f'<code>{html.escape(username)}</code>'
        )

    other_users = context.get('other_users') or []
    users_text = '\n'.join(
        f'• {html.escape(user.display_name)}'
        for user in other_users
    )

    return (
        f'{title}\n\n'
        'Групповой звонок завершён.'
        f'{chr(10) + users_text if users_text else ""}'
    )


def build_call_finished_markup(context: dict):
    if not context.get('is_direct'):
        return back_and_main_kb()

    return call_finished_kb(
        call_id=context['call'].id,
        is_favorite=context['is_favorite'],
        is_contact=context['is_contact'],
    )


async def edit_saved_call_screen(
        bot,
        participant,
        text: str,
        reply_markup=None,
) -> None:
    if bot is None:
        return

    if not participant.telegram_chat_id or not participant.telegram_message_id:
        return

    try:
        await bot.edit_message_text(
            chat_id=participant.telegram_chat_id,
            message_id=participant.telegram_message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML',
        )
    except TelegramBadRequest as error:
        if 'message is not modified' in error.message:
            return

        if 'message to edit not found' in error.message:
            return

        raise


async def send_or_update_call_screen(
        bot,
        chat_id: int,
        text: str,
        reply_markup,
        previous_participant=None,
) -> tuple[int, int] | None:
    if bot is None:
        return None

    if (
        previous_participant is not None
        and previous_participant.telegram_chat_id
        and previous_participant.telegram_message_id
    ):
        try:
            msg = await bot.edit_message_text(
                chat_id=previous_participant.telegram_chat_id,
                message_id=previous_participant.telegram_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode='HTML',
            )

            return msg.chat.id, msg.message_id
        except TelegramBadRequest as error:
            if 'message is not modified' in error.message:
                return (
                    previous_participant.telegram_chat_id,
                    previous_participant.telegram_message_id,
                )

            if 'message to edit not found' not in error.message:
                raise

    msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML',
    )

    return msg.chat.id, msg.message_id


async def repeat_incoming_call_notification(
        bot,
        chat_id: int,
        call_id: int,
        caller_name: str,
        interval: int,
) -> None:
    interval = max(3, interval)
    notification_message = None

    try:
        while True:
            status = run_in_session(
                lambda session: get_call_status(session, call_id)
            )

            if status != 'ringing':
                return

            notification_message = None

            try:
                notification_message = await bot.send_message(
                    chat_id=chat_id,
                    text=INCOMING_CALL_NOTIFICATION_TEXT.format(
                        display_name=html.escape(caller_name),
                    ),
                    parse_mode='HTML',
                )
            except TelegramBadRequest:
                return

            await asyncio.sleep(2)

            if notification_message is not None:
                try:
                    await bot.delete_message(
                        chat_id=chat_id,
                        message_id=notification_message.message_id,
                    )
                except TelegramBadRequest:
                    pass
                notification_message = None

            await asyncio.sleep(max(0, interval - 2))
    except asyncio.CancelledError:
        if notification_message is not None:
            try:
                await bot.delete_message(
                    chat_id=chat_id,
                    message_id=notification_message.message_id,
                )
            except TelegramBadRequest:
                pass
        raise
    finally:
        incoming_notification_tasks.pop(call_id, None)


def stop_incoming_call_notification(call_id: int) -> None:
    task = incoming_notification_tasks.pop(call_id, None)

    if task is not None and not task.done():
        task.cancel()


async def update_other_call_screens(
        bot,
        action: str,
        context: dict,
) -> None:
    if not context.get('is_direct'):
        return

    call = context['call']

    for other_participant in context.get('other_participants', []):
        other_context = run_in_session(
            lambda session: get_call_finished_context(
                session=session,
                call_id=call.id,
                user_id=other_participant.user_id,
            )
        )

        await edit_saved_call_screen(
            bot=bot,
            participant=other_context['participant'],
            text=build_call_finished_text(action, other_context),
            reply_markup=build_call_finished_markup(other_context),
        )


@router.callback_query(MainMenuCallback.filter(F.action == 'call'))
async def call_entry_handler(
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
            reply_markup=back_and_main_kb(),
        )
        return

    await show_call_username_screen(
        message=callback.message,
        state=state,
        user_id=user.id,
    )


@router.callback_query(CallCallback.filter(F.action == 'favorites_page'))
async def call_favorites_page_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: CallCallback,
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
            reply_markup=back_and_main_kb(),
        )
        return

    await show_call_username_screen(
        message=callback.message,
        state=state,
        user_id=user.id,
        page=callback_data.page,
    )


@router.callback_query(CallCallback.filter(F.action == 'select'))
async def call_select_favorite_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: CallCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    if not callback_data.username:
        return

    user = run_in_session(
        lambda session: get_user_username(session, callback_data.username)
    )

    if not user:
        await show_screen(
            message=callback.message,
            state=state,
            caption=USER_NOT_FOUND_ERROR_TEXT,
            reply_markup=back_and_main_kb(),
        )
        return

    await state.update_data(call_favorites_page=callback_data.page)

    await show_screen(
        message=callback.message,
        state=state,
        caption=CALL_USER_CARD_TEXT.format(
            display_name=user.display_name,
            username=user.username,
        ),
        reply_markup=call_user_card_kb(user.username),
    )


@router.message(CallState.username)
async def call_username_handler(message: types.Message, state: FSMContext):
    if not message.text:
        await delete_user_message(message)

        await show_screen(
            message=message,
            state=state,
            caption='❌ Введите ник текстом.',
        )
        return

    if not message.from_user:
        return

    await delete_user_message(message)

    username = message.text.strip().lower()

    if '/' in username:
        username = username.split('/')[-1]

    username = username.lstrip('@')

    if not username:
        await show_screen(
            message=message,
            state=state,
            caption='❌ Укажите ник',
        )
        return

    user = run_in_session(
        lambda session: get_user_username(session, username)
    )

    if not user:
        await show_screen(
            message=message,
            state=state,
            caption=USER_NOT_FOUND_TEXT,
            reply_markup=user_not_found_kb(),
        )
        return

    if user.telegram_id == message.from_user.id:
        await show_screen(
            message=message,
            state=state,
            caption='❌ Нельзя позвонить самому себе',
        )
        return

    await show_screen(
        message=message,
        state=state,
        caption=CALL_USER_CARD_TEXT.format(
            display_name=user.display_name,
            username=user.username,
        ),
        reply_markup=call_user_card_kb(user.username),
    )


@router.callback_query(CallCallback.filter(F.action.in_({
    'confirm',
    'recall',
})))
async def call_start_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: CallCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    creator = run_in_session(
        lambda session: get_user_id(session, callback.from_user.id)
    )

    if not creator:
        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '⚠️ Ошибка пользователя.\n\n'
                'Перейдите в главное меню и попробуйте снова'
            ),
            reply_markup=back_and_main_kb(),
        )
        return

    if callback_data.action == 'confirm':
        username = callback_data.username

        if not username:
            await show_screen(
                message=callback.message,
                state=state,
                caption=USER_NOT_FOUND_ERROR_TEXT,
                reply_markup=back_and_main_kb(),
            )
            return

        callee = run_in_session(
            lambda session: get_user_username(session, username)
        )

        if not callee:
            await show_screen(
                message=callback.message,
                state=state,
                caption=USER_NOT_FOUND_ERROR_TEXT,
                reply_markup=back_and_main_kb(),
            )
            return

    elif callback_data.action == 'recall':
        call_id = callback_data.call_id

        if call_id is None:
            await show_screen(
                message=callback.message,
                state=state,
                caption='⚠️ Не удалось определить звонок для перезвона.',
                reply_markup=back_and_main_kb(),
            )
            return

        try:
            context = run_in_session(
                lambda session: get_call_finished_context(
                    session=session,
                    call_id=call_id,
                    user_id=creator.id,
                )
            )
        except (CallNotFoundError, ParticipantNotFoundError):
            await show_screen(
                message=callback.message,
                state=state,
                caption='⚠️ Звонок уже недоступен для перезвона.',
                reply_markup=back_and_main_kb(),
            )
            return

        callee = context.get('other_user')

        if callee is None:
            await show_screen(
                message=callback.message,
                state=state,
                caption=(
                    '⚠️ Повторный звонок для групповых звонков '
                    'будет добавлен позже.'
                ),
                reply_markup=back_and_main_kb(),
            )
            return

    else:
        return

    if callee.id == creator.id:
        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '⚠️ Вы выбрали свой ник — позвонить себе нельзя\n\n'
                'Перейдите в главное меню и попробуйте снова'
            ),
            reply_markup=back_and_main_kb(),
        )
        return

    try:
        call_data = run_in_session(
            lambda session: start_call(
                session=session,
                creator_id=creator.id,
                callee_id=callee.id,
            ),
            commit=True,
        )

    except ActiveCallExistsError as error:
        call = error.call
        users = error.users

        user_text = ''
        if users:
            active_user = users[0]
            user_text = (
                f'👤 {active_user["display_name"]}\n'
                f'@{active_user["username"]}\n'
            )

        # time_text = ''
        # if call and call.get('created_at'):
        #     time_text = f'🕒 {call["created_at"]:%H:%M}\n'

        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '⚠️ У вас есть незавершённый звонок\n\n'
                f'{user_text}'
                'Завершить его?'
            ),
            reply_markup=active_call_exists_kb(call['id'] if call else None),
        )
        return

    except IncomingCallForbiddenError:
        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '🚫 Пользователь сейчас не принимает звонки.\n\n'
                'Возможно, у него включено ограничение входящих звонков.'
            ),
            reply_markup=back_and_main_kb(),
        )
        return

    except CallError:
        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '⚠️ Произошла ошибка\n\n'
                'Попробуйте ещё раз.\n'
                'Если проблема повторится — напишите в поддержку.'
            ),
            reply_markup=back_and_main_kb(),
        )
        return

    creator_url = f'{DOMAIN}/{call_data["creator_token"]}'
    callee_url = f'{DOMAIN}/{call_data["callee_token"]}'

    creator_message = await show_screen(
        message=callback.message,
        state=state,
        caption=(
            f'📞 Звоним {callee.display_name}\n\n'
            '⏳ Ожидаем ответа...'
        ),
        reply_markup=call_kb(
            creator_url,
            is_caller=True,
            call_id=call_data['call_id'],
        ),
    )

    if creator_message:
        run_in_session(
            save_participant_screen_by_token,
            call_data['creator_token'],
            creator_message.chat.id,
            creator_message.message_id,
            commit=True,
        )

    if callback.bot is None:
        return

    previous_callee_participant = run_in_session(
        lambda session: get_latest_participant_screen(
            session=session,
            user_id=callee.id,
            exclude_call_id=call_data['call_id'],
        )
    )

    callee_screen = await send_or_update_call_screen(
        bot=callback.bot,
        chat_id=callee.telegram_id,
        text=(
            '📞 Входящий звонок\n\n'
            f'{creator.display_name} хочет созвониться с вами.'
        ),
        reply_markup=call_kb(
            callee_url,
            is_caller=False,
            call_id=call_data['call_id'],
        ),
        previous_participant=previous_callee_participant,
    )

    if callee_screen:
        callee_chat_id, callee_message_id = callee_screen

        run_in_session(
            save_participant_screen_by_token,
            call_data['callee_token'],
            callee_chat_id,
            callee_message_id,
            commit=True,
        )

    if callee.call_notification_mode == 'enabled':
        stop_incoming_call_notification(call_data['call_id'])
        incoming_notification_tasks[call_data['call_id']] = asyncio.create_task(
            repeat_incoming_call_notification(
                bot=callback.bot,
                chat_id=callee.telegram_id,
                call_id=call_data['call_id'],
                caller_name=creator.display_name,
                interval=callee.call_notification_interval,
            )
        )


@router.callback_query(CallCallback.filter(F.action.in_({
    'cancel',
    'decline',
    'end',
})))
async def call_control_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: CallCallback,
):
    await safe_callback_answer(callback)

    if not isinstance(callback.message, types.Message):
        return

    call_id = callback_data.call_id

    if call_id is None:
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Не удалось определить звонок.',
            reply_markup=back_and_main_kb(),
        )
        return

    stop_incoming_call_notification(call_id)

    user = run_in_session(
        lambda session: get_user_id(session, callback.from_user.id)
    )

    if not user:
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Пользователь не найден. Повторите попытку.',
            reply_markup=back_and_main_kb(),
        )
        return

    try:
        if callback_data.action in {'cancel', 'decline'}:
            run_in_session(
                lambda session: decline_call_user(
                    session=session,
                    call_id=call_id,
                    user_id=user.id,
                ),
                commit=True,
            )

            context = run_in_session(
                lambda session: get_call_finished_context(
                    session=session,
                    call_id=call_id,
                    user_id=user.id,
                )
            )

            await update_other_call_screens(
                bot=callback.bot,
                action=callback_data.action,
                context=context,
            )

            await show_screen(
                message=callback.message,
                state=state,
                caption=build_call_finished_text(
                    callback_data.action,
                    context,
                ),
                reply_markup=build_call_finished_markup(context),
            )
            return

        if callback_data.action == 'end':
            run_in_session(
                lambda session: leave_or_end_call_by_user(
                    session=session,
                    call_id=call_id,
                    user_id=user.id,
                ),
                commit=True,
            )

            context = run_in_session(
                lambda session: get_call_finished_context(
                    session=session,
                    call_id=call_id,
                    user_id=user.id,
                )
            )

            await update_other_call_screens(
                bot=callback.bot,
                action='end',
                context=context,
            )

            await show_screen(
                message=callback.message,
                state=state,
                caption=build_call_finished_text('end', context),
                reply_markup=build_call_finished_markup(context),
            )
            return

    except (CallNotFoundError, ParticipantNotFoundError):
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Звонок уже недоступен.',
            reply_markup=back_and_main_kb(),
        )
        return


@router.callback_query(CallCallback.filter(F.action.in_({
    'favorite',
    'remove_favorite',
    'add_contact',
    'confirm_remove_contact',
    'remove_contact_confirmed',
    'back_finished',
})))
async def call_contact_action_handler(
        callback: types.CallbackQuery,
        state: FSMContext,
        callback_data: CallCallback,
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
            caption='⚠️ Пользователь не найден. Повторите попытку.',
            reply_markup=back_and_main_kb(),
        )
        return

    try:
        if callback_data.call_id is not None:
            context = run_in_session(
                lambda session: get_call_finished_context(
                    session=session,
                    call_id=callback_data.call_id,
                    user_id=user.id,
                )
            )

            other_user = context.get('other_user')

            if other_user is None:
                await show_screen(
                    message=callback.message,
                    state=state,
                    caption=(
                        '⚠️ Для групповых звонков управление контактами '
                        'будет добавлено позже.'
                    ),
                    reply_markup=build_call_finished_markup(context),
                )
                return

            contact_user_id = other_user.id

        elif callback_data.username:
            other_user = run_in_session(
                lambda session: get_user_username(
                    session,
                    callback_data.username,
                )
            )

            if other_user is None:
                await show_screen(
                    message=callback.message,
                    state=state,
                    caption=USER_NOT_FOUND_ERROR_TEXT,
                    reply_markup=back_and_main_kb(),
                )
                return

            contact_user_id = other_user.id
            context = None

        else:
            await show_screen(
                message=callback.message,
                state=state,
                caption='⚠️ Не удалось определить пользователя.',
                reply_markup=back_and_main_kb(),
            )
            return

        if contact_user_id == user.id:
            await show_screen(
                message=callback.message,
                state=state,
                caption='❌ Нельзя добавить самого себя в контакты.',
                reply_markup=back_and_main_kb(),
            )
            return

        action = callback_data.action

        if action == 'back_finished':
            if callback_data.call_id is not None and context is not None:
                await show_screen(
                    message=callback.message,
                    state=state,
                    caption=build_call_finished_text('updated', context),
                    reply_markup=build_call_finished_markup(context),
                )
            return

        if action == 'confirm_remove_contact':
            if callback_data.call_id is not None and context is not None:
                username = (
                    f'@{other_user.username}'
                    if other_user.username
                    else 'без ника'
                )

                await show_screen(
                    message=callback.message,
                    state=state,
                    caption=CONFIRM_REMOVE_FINISHED_CONTACT_TEXT.format(
                        display_name=html.escape(other_user.display_name),
                        username=html.escape(username),
                    ),
                    reply_markup=confirm_remove_finished_contact_kb(
                        callback_data.call_id,
                    ),
                )
                return

            if callback_data.username:
                username = (
                    f'@{other_user.username}'
                    if other_user.username
                    else 'без ника'
                )

                await show_screen(
                    message=callback.message,
                    state=state,
                    caption=CONFIRM_REMOVE_FINISHED_CONTACT_TEXT.format(
                        display_name=html.escape(other_user.display_name),
                        username=html.escape(username),
                    ),
                    reply_markup=confirm_remove_user_contact_kb(
                        callback_data.username,
                    ),
                )
                return

            return

        run_in_session(
            lambda session: {
                'favorite': add_favorite,
                'remove_favorite': remove_favorite,
                'add_contact': add_contact,
                'remove_contact_confirmed': remove_contact,
            }[action](
                session,
                user.id,
                contact_user_id,
            ),
            commit=True,
        )

        if callback_data.call_id is not None:
            context = run_in_session(
                lambda session: get_call_finished_context(
                    session=session,
                    call_id=callback_data.call_id,
                    user_id=user.id,
                )
            )

            await show_screen(
                message=callback.message,
                state=state,
                caption=build_call_finished_text('updated', context),
                reply_markup=build_call_finished_markup(context),
            )
            return

        action_text = {
            'favorite': '⭐ Пользователь добавлен в избранное.',
            'remove_favorite': '⭐ Пользователь удалён из избранного.',
            'add_contact': '👤 Пользователь добавлен в контакты.',
            'remove_contact_confirmed': '🗑 Контакт удалён.',
        }[action]

        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                f'{action_text}\n\n'
                f'<b>{html.escape(other_user.display_name)}</b>\n'
                f'<code>@{html.escape(other_user.username or "")}</code>'
            ),
            reply_markup=back_and_main_kb(),
        )

    except (CallNotFoundError, ParticipantNotFoundError):
        await show_screen(
            message=callback.message,
            state=state,
            caption='⚠️ Звонок уже недоступен.',
            reply_markup=back_and_main_kb(),
        )
        return

    except CallError:
        await show_screen(
            message=callback.message,
            state=state,
            caption=(
                '⚠️ Произошла ошибка\n\n'
                'Попробуйте ещё раз.'
            ),
            reply_markup=back_and_main_kb(),
        )
        return
