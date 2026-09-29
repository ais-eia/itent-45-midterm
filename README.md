# LiteChat Midterm Project

## Requirements

- Python 3.12.3

## Setup and Run

From a fresh clone, run these commands from the repository root:

```sh
python3.12 -m venv env
source env/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

The development server is available at <http://localhost:8000/>.

`.env.example` contains placeholders for local development. Replace them in your local `.env` as needed; never commit `.env` or real provider credentials.
