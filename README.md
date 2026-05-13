# Nomera Demo (ML + Backend + Frontend)

Легкий демо-контур для распознавания номеров:
- `ml` (FastAPI + fast-alpr) читает видео, детектит номера и отправляет raw/confirmed события.
- `backend` (FastAPI) принимает события от ML, хранит их в памяти и транслирует во frontend по WebSocket.
- `frontend` (Vue + Vite) показывает видео, bbox overlay и лог подтвержденных номеров.

## Архитектура и порты
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8001`
- ML API: `http://localhost:8000`

Поток данных:
1. Нажимаем `Start ML` во frontend.
2. Frontend дергает backend `POST /api/v1/ml/start`.
3. Backend проксирует команду в ML.
4. ML начинает обработку `services/ml/example_video.mp4`, шлет raw и confirmed в backend.
5. Backend рассылает события во frontend через `ws://localhost:8001/api/v1/ws`.

## Быстрый запуск через Docker Compose

### 1) Подготовка
В корне проекта должен быть файл `.env` (уже есть в репо). Пример:

```env
ML_API_KEY=dev-secret-key-change-in-production
BACKEND_API_KEY=dev-backend-key-change-in-production
```

Проверьте, что файл видео существует:
- `services/ml/example_video.mp4`

### 2) Поднять стек
Из корня проекта:

```powershell
docker compose up --build -d
docker compose ps
```

### 3) Открыть UI и запустить pipeline
1. Откройте `http://localhost:3000`
2. Нажмите `Start ML`
3. Должны появиться bbox на видео и записи в логе справа.

### 4) Проверка health

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:8001/api/v1/health
```

## Полезные команды

Логи:

```powershell
docker compose logs -f ml
docker compose logs -f backend
docker compose logs -f frontend
```

Остановка:

```powershell
docker compose down
```

Пересборка конкретного сервиса:

```powershell
docker compose up --build -d ml
docker compose up --build -d backend
docker compose up --build -d frontend
```

## Мини smoke-check backend API

Статус ML через backend:

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/ml/status
```

Запуск/остановка ML через backend:

```powershell
Invoke-RestMethod -Method Post http://localhost:8001/api/v1/ml/start
Invoke-RestMethod -Method Post http://localhost:8001/api/v1/ml/stop
```

Список confirmed детекций:

```powershell
Invoke-RestMethod "http://localhost:8001/api/v1/detections?limit=20"
```

## Локальный запуск по сервисам (без Docker)

Ниже вариант для Windows PowerShell.

### 1) ML service

```powershell
cd services/ml
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python main.py
```

### 2) Backend service (в новом терминале)

```powershell
cd services/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env -Force
python main.py
```

### 3) Frontend service (в новом терминале)

```powershell
cd services/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

После этого откройте `http://localhost:3000`.

## Что важно знать
- `ML_AUTO_START=false`: камера регистрируется на старте ML, но pipeline не запускается автоматически.
- Синхронизация bbox и видео идет по `timestamp_seconds` из raw событий.
- Backend хранит историю только в памяти (после рестарта очищается).
- Модели (`services/ml/models/`) не хранятся в git — нужно подложить вручную перед запуском.

## Если что-то не стартует
- Порт занят: освободите `3000`, `8000`, `8001` или поменяйте mapping в `docker-compose.yml`.
- Нет GPU/драйверов для CUDA: ML контейнер может не подняться. Для локального CPU-режима обычно проще запускать ML сервис без Docker и отдельно адаптировать зависимости под CPU.
- Нет bbox в UI: проверьте, что нажат `Start ML`, открыт WS (`/api/v1/ws`) и в логах backend приходят `raw_detection`.
- ML циклически рестартится на старте: обычно это значит, что не найден/пустой кэш `services/ml/venv/Lib/site-packages/data` и контейнер не может достучаться до `models.vsp.net.ua`. Либо подключите VPN и прогрейте модели, либо проверьте монтирование кэша.
