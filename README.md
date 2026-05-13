# УмныеВрата

Система автоматического распознавания номерных знаков и управления доступом на охраняемых объектах (КПП, парковки, жилые комплексы, предприятия).

Система идентифицирует транспортные средства по видеопотоку в реальном времени, сверяет номера с белым списком, инициирует открытие шлагбаума/ворот и предоставляет операторам веб-интерфейс для управления.

## Архитектура

```
Камеры (RTSP / файл)
        │
        ▼
┌──────────────┐   HTTP события   ┌───────────────────┐   REST + WebSocket
│  ML-сервис   │ ───────────────► │  Backend-сервис   │ ◄────────────────── Браузер
│  порт 8000   │ ◄─────────────── │  порт 8001        │
└──────────────┘  управление      └───────────────────┘
```

| Сервис   | Директория           | Порт | Описание                                        |
|----------|----------------------|------|-------------------------------------------------|
| ML       | `services/ml/`       | 8000 | Детекция и распознавание номерных знаков (YOLOv8-Pose + ONNX OCR) |
| Backend  | `services/backend/`  | 8001 | REST API, бизнес-логика, БД, WebSocket-хаб      |
| Frontend | `services/frontend/` | 3000 | Веб-панель для операторов и администраторов     |

## Быстрый запуск (Docker Compose)

```powershell
# 1. Клонировать репозиторий
git clone <repo-url>
cd nomera

# 2. Убедиться, что файлы моделей на месте (см. раздел "Модели" ниже)

# 3. Поднять все сервисы
docker compose up --build -d

# 4. Проверить статус
docker compose ps

# 5. Открыть веб-панель
#    http://localhost:3000
#    Логин: admin  |  Пароль: admin123
```

Проверка здоровья сервисов:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8001/api/v1/health
```

## Локальный запуск без Docker

**ML-сервис:**
```powershell
cd services/ml
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

**Backend-сервис** (новый терминал):
```powershell
cd services/backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

**Frontend-сервис** (новый терминал):
```powershell
cd services/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

## Конфигурация

Корневой `.env` (уже есть в репозитории для разработки):

```env
ML_API_KEY=dev-secret-key-change-in-production
BACKEND_API_KEY=dev-backend-key-change-in-production
```

Ключевые переменные окружения:

| Переменная | Сервис | Описание |
|---|---|---|
| `ML_DETECTOR_ENGINE` | ML | `keypoint` (по умолчанию) или `fast-alpr` |
| `ML_FRAME_SKIP` | ML | Обрабатывать каждый N-й кадр (по умолчанию: 5) |
| `ML_AUTO_START` | ML | Автозапуск пайплайна при старте (по умолчанию: false) |
| `DATABASE_URL` | Backend | SQLite по умолчанию; для прода — PostgreSQL |
| `JWT_SECRET` | Backend | Сменить перед деплоем в продакшн |

Полное описание всех переменных — в [TECH.md](TECH.md).

## Использование

1. Открыть `http://localhost:3000` и войти под учётной записью администратора.
2. В табе **«Камеры»** добавить камеру (RTSP-URL или тестовый видеофайл) и нажать **«Запустить распознавание»**.
3. В табе **«Номера»** настроить белый список — добавить номера с разрешёнными днями и временным окном.
4. Новые детекции появляются в табе **«Журнал»** в реальном времени.
5. Заявки от водителей (через мобильное приложение) отображаются в разделе **«Заявки»** — одобрить или отклонить.

Подробное руководство для операторов — в [USER_FLOW.md](USER_FLOW.md).

## Полезные команды

```powershell
# Логи сервисов
docker compose logs -f ml
docker compose logs -f backend
docker compose logs -f frontend

# Пересборка отдельного сервиса
docker compose up --build -d ml

# Остановка
docker compose down

# Запуск/остановка ML-пайплайна через API
Invoke-RestMethod -Method Post http://localhost:8001/api/v1/ml/start
Invoke-RestMethod -Method Post http://localhost:8001/api/v1/ml/stop

# Последние подтверждённые детекции
Invoke-RestMethod "http://localhost:8001/api/v1/detections?limit=20"
```

## Чеклист для продакшн-деплоя

- [ ] Сменить `ML_API_KEY`, `BACKEND_API_KEY`, `JWT_SECRET` на случайные строки
- [ ] Изменить пароль администратора по умолчанию
- [ ] Настроить HTTPS-прокси (nginx / Caddy)
- [ ] Переключить БД на PostgreSQL
- [ ] Настроить постоянный volume для снимков (`static/logs/`)
- [ ] Включить GPU в Docker-конфигурации ML

## Документация

- [TECH.md](TECH.md) — архитектура, стек, инструкция по развёртыванию, реестр фич
- [USER_FLOW.md](USER_FLOW.md) — руководство пользователя (администратор, охранник)

## Решение проблем

| Проблема | Причина | Решение |
|---|---|---|
| ML-контейнер не поднимается | Нет GPU / CUDA-драйверов | Запустить ML без Docker с `onnxruntime-cpu` |
| Нет детекций в интерфейсе | Пайплайн не запущен | Нажать «Запустить распознавание» в табе «Камеры» |
| Порт занят | Конфликт с другим процессом | Изменить маппинг в `docker-compose.yml` |
| Ошибка «модель не найдена» | Отсутствуют файлы моделей | Разместить файлы моделей согласно разделу выше |
