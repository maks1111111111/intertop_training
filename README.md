# Intertop Training Bot

Простой Telegram-бот для внутреннего обучения сотрудников Intertop.

## Возможности

- Команда `/start` показывает список курсов
- Курсы и уроки подхватываются автоматически из папки `courses/`
- Новые файлы `.mp3` и `.mp4` появляются в боте без изменения кода
- Уроки сортируются по числовому префиксу: `01_`, `02_`, `03_`
- Обложка курса отправляется из папки `covers/`, если файл существует

## Структура проекта

```
intertop-training/
  app/
    main.py
    handlers/
      start.py
      courses.py
    services/
      scanner.py
  covers/
    mission.jpg
    service.jpg
    brands.jpg
    cashier.jpg
  courses/
    mission/
    service/
    brands/
    cashier/
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

## Именование уроков

Файлы уроков должны начинаться с номера:

```
01_введение.mp3
02_основы.mp4
03_практика.mp3
```

Поддерживаются форматы:

- `.mp3` — отправляется как аудио
- `.mp4` — отправляется как видео

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

1. Положите обложку курса в `covers/`, например `covers/mission.jpg`
2. Добавьте уроки в нужную папку курса, например `courses/mission/01_миссия.mp3`
3. Перезапускать бота не нужно — при следующем выборе курса файлы будут прочитаны заново

## Пример наполнения

```
courses/mission/01_миссия_компании.mp3
courses/mission/02_ценности.mp3
courses/service/01_стандарты.mp4
covers/mission.jpg
covers/service.jpg
```
