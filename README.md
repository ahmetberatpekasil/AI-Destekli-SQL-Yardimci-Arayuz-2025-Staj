# Django + PostgreSQL + Gemini (google-genai) Starter

Bu depo, Django ile geliştirilmiş bir web uygulaması iskeletidir. Yapılandırmalar `.env` dosyasından okunur; gizli anahtarlar ve veritabanı bilgileri koda gömülmez. Veritabanı: PostgreSQL. AI entegrasyonu: `google-genai` (Python).

## Gereksinimler
- Python 3.10+
- PostgreSQL 13+
- pip ve (önerilir) sanal ortam (venv)

## Hızlı Başlangıç
```bash
git clone https://github.com/ahmetberatpekasil/AI-Destekli-SQL-Yardimci-Arayuz-2025-Staj.git
cd AI-Destekli-SQL-Yardimci-Arayuz-2025-Staj

python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate
# macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver
```

## Ortam Değişkenleri (.env örneği)
```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASS=your_db_password
SECRET_KEY=your_django_secret_key
DEBUG=True
```

Notlar:
- DEBUG üretimde False olmalıdır.
- `.env` dosyası repoya eklenmez (bkz. `.gitignore`).

## settings.py Özet (dotenv + PostgreSQL)
```python
# config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASS"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# Gemini anahtarı (ihtiyaca göre kodunuzda kullanın)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

LANGUAGE_CODE = "tr-tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

## requirements.txt (önerilen)
Aşağıdaki içeriği proje köküne requirements.txt olarak kaydedin:
```
Django>=4.2
python-dotenv>=1.0
psycopg2-binary>=2.9
google-genai
```

Not: Kodda `from google import genai` ve `from google.genai import types` kullanıyorsanız paket adı `google-genai` olmalıdır.

## Proje Yapısı (örnek)
```
project-root/
├─ manage.py
├─ requirements.txt
├─ README.md
├─ .gitignore
├─ config/                 # proje ayarları (settings, urls, wsgi, asgi)
│  ├─ __init__.py
│  ├─ settings.py
│  ├─ urls.py
│  ├─ wsgi.py
│  └─ asgi.py
├─ app_name/               # örnek Django uygulaması
│  ├─ migrations/
│  ├─ __init__.py
│  ├─ admin.py
│  ├─ apps.py
│  ├─ models.py
│  ├─ tests.py
│  └─ views.py
└─ .env                    # ortam değişkenleri (git'e dahil edilmez)
```

## .gitignore (önerilen)
```
# Python
__pycache__/
*.pyc
*.pyo
*.pyd

# Django
db.sqlite3
media/

# Environment
.env
venv/

# IDE / Editor
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```
