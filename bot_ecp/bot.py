from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
)
import requests
import math
import datetime
import json
import logging

# Включение отладочной информации
logging.basicConfig(level=logging.DEBUG)

# Вставьте ваш токен сюда
TOKEN = '7250376634:AAFBE6vuPF1yfbuXGyfHD3wKecUcRqBGmtQ'

# Список разрешенных пользователей (ID пользователей, которые могут использовать бота)
ALLOWED_USERS = {669247439, 415542031, 641770720}  # замените на реальные идентификаторы пользователей

# Функция для проверки доступа пользователя
def is_user_allowed(user_id):
    return user_id in ALLOWED_USERS

# Функция для получения данных с вашего локального сайта
def get_data_from_site(action):
    try:
        response = requests.get(f'http://192.168.0.3/ecp/php/api.php?action={action}')  # Замените <IP-адрес вашего сервера> на реальный IP
        if response.status_code == 200:
            return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error accessing API for action '{action}': {e}")
    return []

# Функция для создания клавиатуры с кнопками
def create_reply_keyboard():
    keyboard = [
        [KeyboardButton("🔍 Поиск по фамилии")],
        [KeyboardButton("⌛️ Заканчивающиеся подписи"), KeyboardButton("🔍 Истекшие подписи")],
        [KeyboardButton("🆕 Необходимо выпустить"), KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Функция для отправки длинных сообщений
async def send_long_message(context, chat_id, text, reply_markup=None):
    message_ids = []
    for i, chunk in enumerate([text[i:i + 4096] for i in range(0, len(text), 4096)]):
        msg = await context.bot.send_message(chat_id=chat_id, text=chunk, reply_markup=reply_markup if i == len(text) // 4096 else None)
        message_ids.append(msg.message_id)
    return message_ids

# Функция для удаления сообщений
async def delete_messages(context, chat_id, message_ids):
    for message_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logging.warning(f"Failed to delete message {message_id}: {e}")

# Функция для отправки сообщений с пагинацией
async def send_paginated_message(context, chat_id, data, page, callback_prefix, reply_markup=None):
    items_per_page = 20
    total_pages = math.ceil(len(data) / items_per_page)
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page

    message = ''
    for employee in data[start_idx:end_idx]:
        message += f"ФИО: {employee['name']}\nОтдел: {employee['job']}\nДата окончания подписи: {employee['expiration_date']}\n\n"

    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Прошлая страница", callback_data=f"{callback_prefix}_{page-1}"))
    if page < total_pages - 1:
        keyboard.append(InlineKeyboardButton("Следующая страница ▶️", callback_data=f"{callback_prefix}_{page+1}"))
    # Обновление клавиатуры для добавления отдельной строки для кнопки "Назад"
    reply_markup = InlineKeyboardMarkup([
        keyboard,  # Кнопки пагинации
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')]  # Кнопка "Назад"
    ])

    message_ids = await send_long_message(context, chat_id, message, reply_markup=reply_markup)
    context.user_data['message_ids'] = message_ids
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        if 'user_ids' not in context.bot_data:
            context.bot_data['user_ids'] = set()
        context.bot_data['user_ids'].add(user_id)
        
        # Создание и отправка Reply Keyboard
        reply_keyboard = create_reply_keyboard()
        
        welcome_message = "📋 <b>Добро пожаловать!</b>\n\nВыберите действие:"
        await update.message.reply_text(
            welcome_message,
            reply_markup=reply_keyboard,
            parse_mode='HTML'
        )
        logging.info(f"User {user_id} started interaction.")
    except Exception as e:
        logging.error(f"Error in start function: {e}")
        await update.message.reply_text('Произошла ошибка. Попробуйте снова позже.')

async def all_employees(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        data = get_data_from_site('get_signatures')
        if data:
            data.sort(key=lambda x: x['name'])  # Сортировка по фамилии
            await send_paginated_message(context, update.message.chat_id, data, page, 'all_employees')
            logging.info(f"User {user_id} requested all employees.")
        else:
            await update.message.reply_text('Не удалось получить данные (all_employees).', reply_markup=create_reply_keyboard())
    except Exception as e:
        logging.error(f"Error in all_employees function: {e}")
        await update.message.reply_text('Произошла ошибка при загрузке данных. Попробуйте снова позже.', reply_markup=create_reply_keyboard())

async def expiring_signatures(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        data = get_data_from_site('get_expiring_signatures')
        logging.debug(f"Data from site (expiring_signatures): {json.dumps(data, ensure_ascii=False, indent=2)}")

        if data:
            now = datetime.datetime.now()
            expiring_data = [
                employee for employee in data
                if now <= datetime.datetime.strptime(employee['expiration_date'], '%Y-%m-%d') <= (now + datetime.timedelta(days=10))
            ]
            logging.debug(f"Filtered expiring data: {json.dumps(expiring_data, ensure_ascii=False, indent=2)}")

            if expiring_data:
                expiring_data.sort(key=lambda x: x['expiration_date'])  # Сортировка по дате окончания подписи
                await send_paginated_message(context, update.message.chat_id, expiring_data, page, 'expiring_signatures')
                logging.info(f"User {user_id} requested expiring signatures.")
            else:
                await update.message.reply_text('Нет подписей, которые скоро закончатся.', reply_markup=create_reply_keyboard())
        else:
            await update.message.reply_text('Не удалось получить данные (expiring_signatures).', reply_markup=create_reply_keyboard())
    except Exception as e:
        logging.error(f"Error in expiring_signatures function: {e}")
        await update.message.reply_text('Произошла ошибка при загрузке данных. Попробуйте снова позже.', reply_markup=create_reply_keyboard())

async def expired_signatures(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        data = get_data_from_site('get_expired_signatures')
        logging.debug(f"Data from site (expired_signatures): {json.dumps(data, ensure_ascii=False, indent=2)}")

        if data:
            expired_data = [
                employee for employee in data
                if datetime.datetime.strptime(employee['expiration_date'], '%Y-%m-%d') < datetime.datetime.now()
            ]
            logging.debug(f"Filtered expired data: {json.dumps(expired_data, ensure_ascii=False, indent=2)}")

            expired_data.sort(key=lambda x: x['expiration_date'])  # Сортировка по дате окончания подписи
            await send_paginated_message(context, update.message.chat_id, expired_data, page, 'expired_signatures')
            logging.info(f"User {user_id} requested expired signatures.")
        else:
            await update.message.reply_text('Не удалось получить данные (expired_signatures).', reply_markup=create_reply_keyboard())
    except Exception as e:
        logging.error(f"Error in expired_signatures function: {e}")
        await update.message.reply_text('Произошла ошибка при загрузке данных. Попробуйте снова позже.', reply_markup=create_reply_keyboard())

async def to_be_issued(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        data = get_data_from_site('get_to_be_issued')
        logging.debug(f"Data from site (to_be_issued): {json.dumps(data, ensure_ascii=False, indent=2)}")

        if data:
            to_be_issued_data = [
                employee for employee in data
                if employee['status'] in ['Не выпущена', 'Выпускается']
            ]
            logging.debug(f"Filtered to be issued data: {json.dumps(to_be_issued_data, ensure_ascii=False, indent=2)}")

            to_be_issued_data.sort(key=lambda x: x['expiration_date'])  # Сортировка по дате окончания подписи
            await send_paginated_message(context, update.message.chat_id, to_be_issued_data, page, 'to_be_issued')
            logging.info(f"User {user_id} requested to be issued signatures.")
        else:
            await update.message.reply_text('Не удалось получить данные (to_be_issued).', reply_markup=create_reply_keyboard())
    except Exception as e:
        logging.error(f"Error in to_be_issued function: {e}")
        await update.message.reply_text('Произошла ошибка при загрузке данных. Попробуйте снова позже.', reply_markup=create_reply_keyboard())
async def search_by_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        await update.message.reply_text('Введите фамилию для поиска:', reply_markup=create_reply_keyboard())
        context.user_data['awaiting_search_name'] = True  # Устанавливаем флаг, что ожидается ввод фамилии
        logging.info(f"User {user_id} initiated name search.")
    except Exception as e:
        logging.error(f"Error in search_by_name function: {e}")
        await update.message.reply_text('Произошла ошибка. Попробуйте снова позже.', reply_markup=create_reply_keyboard())

async def search_by_name_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    try:
        # Проверка на ожидание ввода фамилии
        if context.user_data.get('awaiting_search_name', False):
            query = update.message.text  # Получение текста сообщения от пользователя
            data = get_data_from_site('get_signatures')
            if data:
                # Фильтрация данных по фамилии
                filtered_data = [employee for employee in data if query.lower() in employee['name'].lower()]
                if filtered_data:
                    filtered_data.sort(key=lambda x: x['name'])  # Сортировка по фамилии
                    message = ''
                    for employee in filtered_data:
                        message += f"ФИО: {employee['name']}\nОтдел: {employee['job']}\nДата окончания подписи: {employee['expiration_date']}\n\n"
                    await update.message.reply_text(f'Результаты поиска:\n\n{message}', reply_markup=create_reply_keyboard())
                else:
                    await update.message.reply_text('Сотрудники с такой фамилией не найдены.', reply_markup=create_reply_keyboard())
                logging.info(f"User {user_id} performed a name search for '{query}'.")
            else:
                await update.message.reply_text('Не удалось получить данные для поиска.', reply_markup=create_reply_keyboard())
            context.user_data['awaiting_search_name'] = False  # Сбрасываем флаг после обработки
        else:
            await update.message.reply_text('Команда не распознана. Пожалуйста, используйте кнопки на клавиатуре.', reply_markup=create_reply_keyboard())
    except Exception as e:
        logging.error(f"Error in search_by_name_result function: {e}")
        await update.message.reply_text('Произошла ошибка. Попробуйте снова позже.', reply_markup=create_reply_keyboard())

async def notify_expiring_signatures(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = get_data_from_site('get_signatures')
        if data:
            now = datetime.datetime.now()
            ten_days_later = now + datetime.timedelta(days=10)
            message = 'Подписи, которые истекают через 10 дней:\n\n'
            for employee in data:
                expiration_date = datetime.datetime.strptime(employee['expiration_date'], '%Y-%m-%d')
                if expiration_date.date() == ten_days_later.date():
                    message += f"ФИО: {employee['name']}\nОтдел: {employee['job']}\nДата окончания подписи: {employee['expiration_date']}\n\n"
            
            if message == 'Подписи, которые истекают через 10 дней:\n\n':
                message += 'Нет подписей, истекающих через 10 дней.'

            for user_id in context.bot_data.get('user_ids', []):
                if is_user_allowed(user_id):  # Проверяем, разрешен ли доступ к боту
                    await context.bot.send_message(chat_id=user_id, text=message, reply_markup=create_reply_keyboard())
        logging.info("Notification for expiring signatures sent to allowed users.")
    except Exception as e:
        logging.error(f"Error in notify_expiring_signatures function: {e}") 
        for user_id in context.bot_data.get('user_ids', []):
            if is_user_allowed(user_id):  # Проверяем, разрешен ли доступ к боту
                await context.bot.send_message(chat_id=user_id, text='Произошла ошибка при уведомлении о подписях.', reply_markup=create_reply_keyboard())

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if not is_user_allowed(user_id):
        await update.message.reply_text("Извините, у вас нет доступа к этому боту.")
        return

    # Обработка нажатий кнопок
    if text == "👥 Все сотрудники с подписями":
        await all_employees(update, context)
    elif text == "🔍 Поиск по фамилии":
        await search_by_name(update, context)
    elif text == "⌛️ Заканчивающиеся подписи":
        await expiring_signatures(update, context)
    elif text == "🔍 Истекшие подписи":
        await expired_signatures(update, context)
    elif text == "🆕 Необходимо выпустить":
        await to_be_issued(update, context)
    elif text == "🔙 Назад":
        await start(update, context)
    else:
        await search_by_name_result(update, context)

def main():
    logging.debug("Starting bot...")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))  # Обработчик для Reply Keyboard

    # Создание JobQueue
    job_queue = application.job_queue
    job_queue.run_daily(notify_expiring_signatures, time=datetime.time(hour=12, minute=0, second=0))

    try:
        application.run_polling()
    except Exception as e:
        logging.error(f"An error occurred: {e}")  # Отладочное сообщение при ошибке

if __name__ == '__main__':
    main()

