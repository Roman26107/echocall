from aiogram import types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext


SCREEN_ID = 'screen_id'
SCREEN_TYPE = 'screen_type'

TEXT_SCREEN = 'text'
PHOTO_SCREEN = 'photo'


async def delete_user_message(message: types.Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def safe_callback_answer(callback: types.CallbackQuery) -> None:
    try:
        await callback.answer()
    except TelegramBadRequest as error:
        if 'query is too old' in error.message:
            return

        if 'query ID is invalid' in error.message:
            return

        if 'response timeout expired' in error.message:
            return

        raise


async def set_screen_data(
        state: FSMContext,
        message_id: int,
        screen_type: str) -> None:
    await state.update_data({
        SCREEN_ID: message_id,
        SCREEN_TYPE: screen_type,
    })


async def show_screen(
        message: types.Message,
        state: FSMContext,
        caption: str,
        photo: types.InputFile | str | None = None,
        reply_markup: types.InlineKeyboardMarkup | None = None,
) -> types.Message | None:
    data = await state.get_data()
    screen_id = data.get(SCREEN_ID)
    screen_type = data.get(SCREEN_TYPE)

    new_screen_type = PHOTO_SCREEN if photo is not None else TEXT_SCREEN

    if not message.bot:
        return None

    if screen_id and screen_type == new_screen_type:
        try:
            if photo is not None:
                msg = await message.bot.edit_message_media(
                    chat_id=message.chat.id,
                    message_id=screen_id,
                    media=types.InputMediaPhoto(
                        media=photo,
                        caption=caption,
                        parse_mode='HTML',
                    ),
                    reply_markup=reply_markup,
                )
            else:
                msg = await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=screen_id,
                    text=caption,
                    reply_markup=reply_markup,
                    parse_mode='HTML',
                )
            return msg

        except TelegramBadRequest as error:
            if 'message is not modified' in error.message:
                return message

            if 'message to edit not found' in error.message:
                screen_id = None
                screen_type = None
            else:
                raise

    old_screen_id = screen_id

    if photo is not None:
        msg = await message.answer_photo(
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode='HTML',
        )
        await set_screen_data(state, msg.message_id, PHOTO_SCREEN)
    else:
        msg = await message.answer(
            text=caption,
            reply_markup=reply_markup,
            parse_mode='HTML',
        )
        await set_screen_data(state, msg.message_id, TEXT_SCREEN)

    if old_screen_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=old_screen_id,
            )
        except TelegramBadRequest:
            pass

    return msg


async def clear_fsm_keep_screen(state: FSMContext) -> None:
    data = await state.get_data()

    screen_id = data.get(SCREEN_ID)
    screen_type = data.get(SCREEN_TYPE)

    await state.clear()

    if screen_id:
        await state.update_data(
            **{
                SCREEN_ID: screen_id,
                SCREEN_TYPE: screen_type,
            }
        )
