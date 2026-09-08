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

Telegram-бот:

```bash
python -m app.main
```

Web-приложение за reverse proxy:

```bash
python -m app.web_server
```

По умолчанию Web-сервер слушает только `127.0.0.1:8000`, доверяет proxy-заголовкам
только от `127.0.0.1`, скрывает заголовок версии сервера и работает одним
процессом. Один процесс обязателен, пока предпросмотры генерации хранятся в памяти.
Перезапуск процесса должен выполнять systemd, Docker или другой process manager.

Если reverse proxy находится на другом адресе, перечислите только его IP-адреса:

```bash
export INTERTOP_WEB_HOST=127.0.0.1
export INTERTOP_WEB_PORT=8000
export INTERTOP_FORWARDED_ALLOW_IPS=127.0.0.1,10.0.0.10
python -m app.web_server
```

Значение `*` для `INTERTOP_FORWARDED_ALLOW_IPS` запрещено. Reverse proxy должен
завершать TLS и передавать `X-Forwarded-Proto`, чтобы приложение корректно
определяло исходную HTTPS-схему.

Web и Telegram используют одни и те же пути. Для staging и production задайте
разные постоянные каталоги, чтобы окружения не могли открыть одну базу или общий
каталог загрузок:

```bash
export INTERTOP_DB_PATH=/srv/intertop-training/data/training.db
export INTERTOP_COURSES_DIR=/srv/intertop-training/courses
export INTERTOP_UPLOAD_DIR=/srv/intertop-training/uploads
```

Относительные значения разрешаются от корня проекта; если переменные не заданы,
локальный запуск продолжает использовать `data/training.db`, `courses/` и
`data/uploads/`.

Для удалённого окружения также включите deployment-профиль и перечислите
допустимые домены без схемы и пути:

```bash
export INTERTOP_ENV=staging
export INTERTOP_ALLOWED_HOSTS=training-staging.example.com
export WEB_SESSION_SECRET='уникальный случайный секрет длиной не менее 32 байт'
```

В `staging` и `production` приложение не стартует без допустимого session secret
и списка trusted hosts, запрещает wildcard `*` и всегда устанавливает session
cookie с флагом `Secure`.

Все ответы получают базовые browser security headers. В `staging` и `production`
дополнительно включается HSTS; эти окружения должны быть доступны только по HTTPS.

## Резервная копия SQLite

Для консистентной копии работающей базы используйте встроенную команду. Она
учитывает WAL, проверяет целостность снимка, атомарно публикует файл и оставляет
только указанное число последних копий:

```bash
python -m app.database.backup \
  --db data/training.db \
  --output-dir /var/backups/intertop-training \
  --keep-last 14
```

Каталог резервных копий должен находиться вне репозитория и сохраняться на
отдельном диске или в объектном хранилище.

Для восстановления сначала полностью остановите Web- и Telegram-процессы. Затем
запустите команду ниже. Перед заменой базы она проверит выбранный снимок и
автоматически сохранит текущее состояние в отдельный страховочный backup:

```bash
python -m app.database.restore \
  --backup /var/backups/intertop-training/training-backup-TIMESTAMP.sqlite3 \
  --db data/training.db \
  --safety-backup-dir /var/backups/intertop-training/pre-restore
```

Перед заменой выполняется SQLite checkpoint с нулевым ожиданием. Если база
занята активной записью, восстановление будет остановлено.

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
