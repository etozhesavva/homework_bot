import logging
import os
import time

from dotenv import load_dotenv
import requests
import telegram

import exceptions

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
NOT_SEND_MESSAGE = 'Не удалось отправить сообщение: {error}'
INVALID_STATUS = 'Неожиданный статус д/з {status}'
STATUS_CHANGE = 'Изменился статус проверки работы "{homework_name}". {verdict}'
GLITCH = 'Сбой в работе программы: {error}'
INVALID_CODE = (
    'Ошибка запроса - {code}\n',
    'Информация:\n{url}\n{headers}\n{params}'
)
ERROR = (
    'Ошибка {error} - {meaning}\n',
    '{url}\n{headers}\n{params}'
)
NO_ANSWER = (
    'Не удалось получить ответ от сервера:\n{error}\n'
    '{url}\n{headers}\n{params}'
)
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Высылает в чат измененный статус работы или сообщает об ошибке."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as error:
        logging.exception(NOT_SEND_MESSAGE.format(error=error))


def get_api_answer(current_timestamp):
    """Отправляеет запрос к API домашки на эндпоинт."""
    url = ENDPOINT
    date = {'from_date': current_timestamp}
    request_parametrs = dict(url=url, headers=HEADERS, params=date)
    try:
        response = requests.get(**request_parametrs)
    except requests.exceptions.RequestException as error:
        raise ConnectionError(NO_ANSWER.format(
            error=error,
            **request_parametrs
        ))
    response_json = response.json()
    for error in ('code', 'error'):
        if error in response_json:
            raise RuntimeError(ERROR.format(
                error=error,
                meaning=response_json[error],
                **request_parametrs
            ))
    if response.status_code != 200:
        raise RuntimeError(INVALID_CODE.format(
            code=response.status_code,
            **request_parametrs
        ))
    return response_json


def check_response(response):
    """Проверять полученный ответ на корректность."""
    homework = response['homeworks'][0]
    if not isinstance(response, dict):
        raise TypeError('API вернул неожиданный тип данных')
    if 'homeworks' in response:
        if isinstance(response['homeworks'], list):
            return response['homeworks']
    raise exceptions.ResponseDataError(
        INVALID_STATUS.format(status=homework['status'])
    )


def parse_status(homework):
    """Проверка изменения статуса."""
    homework_status = homework['status']
    verdict = HOMEWORK_VERDICTS[homework['status']]
    if not verdict:
        message_verdict = "Такого статуса нет в словаре"
        raise KeyError(message_verdict)
    if homework_status not in HOMEWORK_VERDICTS:
        message_homework_status = "Такого статуса не существует"
        raise KeyError(message_homework_status)
    if "homework_name" not in homework:
        message_homework_name = "Такого имени не существует"
        raise KeyError(message_homework_name)
    return STATUS_CHANGE.format(
        homework_name=homework['homework_name'],
        verdict=HOMEWORK_VERDICTS[homework['status']]
    )


def check_tokens():
    """Проверка наличия необходимых переменных окружения."""
    is_critical = True
    if not PRACTICUM_TOKEN:
        is_critical = False
        logging.critical(
            'Отсутствует обязательная переменная окружения PRACTICUM_TOKEN')
    elif not TELEGRAM_TOKEN:
        is_critical = False
        logging.critical(
            'Отсутствует обязательная переменная окружения TELEGRAM_TOKEN')
    elif not TELEGRAM_CHAT_ID:
        is_critical = False
        logging.critical(
            'Отсутствует обязательная переменная окружения TELEGRAM_CHAT_ID')
    return is_critical


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        exit()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time()) - RETRY_TIME
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homework = check_response(response)
            if homework:
                status_message = parse_status(homework)
                send_message(bot, status_message)
            else:
                logging.debug(
                    "Статус задания не изменился с последней проверки"
                )
            current_timestamp = response.get('current_date', current_timestamp)
        except Exception as error:
            message = GLITCH.format(error)
            logging.error(message, stack_info=True)
            send_message(bot, message)
        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s, %(levelname)s, %(lineno)s, %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(__file__ + '.log')
        ]
    )
    main()
