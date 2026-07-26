# Intertop Training Bot

Простой Telegram-бот для внутреннего обучения сотрудников Intertop.

## Возможности

- Команда `/start` показывает список курсов
- Курсы, уроки и тесты подхватываются автоматически из папки `courses/`
- Уроки описываются JSON-метаданными и медиафайлами в подпапках
- После завершения курса доступен итоговый тест (если есть `quiz.json`)
- Прогресс обучения и результаты тестов сохраняются в SQLite

Подробный формат контента: **[docs/content-contract.md](docs/content-contract.md)**

## Структура проекта

```
intertop-training/
  app/
    main.py
    handlers/
      start.py
      courses.py
      quiz.py
    services/
      scanner.py
      course_sync.py
    repositories/
    database/
  courses/
    {course_slug}/
      course.json
      cover.jpg              # optional
      quiz.json              # optional
      {lesson_slug}/
        lesson.json
        image.jpg            # optional
        narration.mp3        # optional
  data/
    training.db
  docs/
    content-contract.md
  requirements.txt
  .env.example
```

## Курсы

| Папка     | Название                              |
|-----------|---------------------------------------|
| mission   | Миссия и ценности компании            |
| service   | Стандарты обслуживания клиентов       |
| brands    | История брендов и технологии          |
| cashier   | Кассовая дисциплина                   |

## Структура урока

Каждый урок — отдельная подпапка с файлом `lesson.json`:

```
courses/brands/
  course.json
  lesson_01/
    lesson.json
    image.jpg
    narration.mp3
```

Поддерживаемые медиафайлы (фиксированные имена, см. [content-contract.md](docs/content-contract.md)):

- `cover.jpg` / `cover.png` / … — обложка курса
- `image.jpg` / `image.png` / … — изображение урока
- `narration.mp3` / `narration.m4a` / … — озвучка урока

## Установка

1. Создайте виртуальное окружение Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Создайте файл `.env`:

```bash
cp .env.example .env
```

4. Укажите токен бота от [@BotFather](https://t.me/BotFather):

```
BOT_TOKEN=123456789:ABC...
```

## Запуск

```bash
python -m app.main
```

## Добавление контента

1. Создайте папку курса в `courses/`, например `courses/mission/`
2. Добавьте `course.json` с названием и порядком сортировки
3. Для каждого урока создайте подпапку с `lesson.json` и медиафайлами
4. Опционально: положите `cover.jpg` в папку курса и `quiz.json` для итогового теста
5. **Перезапустите бота** после добавления или переименования уроков (синхронизация с БД выполняется при старте)

Формат всех JSON-файлов описан в [docs/content-contract.md](docs/content-contract.md).

## Пример наполнения

```
courses/mission/
  course.json
  cover.jpg
  lesson_01/
    lesson.json
    narration.mp3
courses/brands/
  course.json
  quiz.json
  lesson_01/
    lesson.json
    image.jpg
    narration.mp3
```
