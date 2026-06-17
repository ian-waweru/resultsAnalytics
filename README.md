# CBC Senior School Results Analytics System

A robust **Django-based web application** designed to track, manage, and analyze student academic performance records for **Competency-Based Curriculum (CBC)** Senior Schools in Kenya.

![Django](https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)

---

## 🚀 Features

- **Student & Academic Records Management** — Add, view, and update student details and examination results.
- **Stream & Class Organization** — Dynamic segmentation by streams and class tiers.
- **CBC-Focused Assessments** — Support for tasks, allocations, and competency-based grading.
- **Performance Analytics Dashboard** — Real-time insights, top students, and stream results visualization.
- **Admin & User Management** — Secure authentication, profile management, and password handling.
- **Data Management Tools** — Built-in management commands for seeding and importing school data.
- **Responsive UI** — Clean templates with custom styling.

---

## 📁 Project Structure

```bash
resultsAnalytics/
├── manage.py
├── requirements.txt
├── .env
├── db.sqlite3
├── resultsAnalytics/              # Main Django project
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── school/                        # Main App
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── admin.py
│   ├── urls.py
│   ├── managers.py
│   ├── utils.py
│   ├── management/commands/       # Custom management commands
│   ├── migrations/
│   ├── templates/school/          # HTML Templates
│   │   ├── cbc_school_analytics_dashboard.html
│   │   ├── student_list.html
│   │   ├── stream_results.html
│   │   ├── top_students.html
│   │   ├── student_detail.html
│   │   └── ...
│   └── static/css/style.css
└── seed_data.json
```

---

## 🛠️ Tech Stack

- **Backend:** Python + Django
- **Database:** SQLite (development) / PostgreSQL (production)
- **Frontend:** HTML + CSS (Bootstrap-ready templates)
- **Configuration:** django-environ + .env file
- **Other:** Custom model managers, management commands, optimized queries

---

## 📦 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/ian-waweru/resultsAnalytics.git
cd resultsAnalytics
```

### 2. Create Virtual Environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Copy `.env.example` to `.env` (if available) or create `.env` and configure:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///db.sqlite3
# For PostgreSQL (recommended for production):
# DATABASE_URL=postgres://user:password@localhost:5432/dbname
```

### 5. Database Setup

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Seed Initial Data (Optional)

```bash
python manage.py seed_db
```

### 8. Run Development Server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

---

## 🔑 Key Pages & Features

- **Dashboard:** `/` or `/dashboard/` — CBC Analytics Overview
- **Students:** Student list, details, and performance
- **Streams & Results:** Stream-wise results analysis
- **Top Students:** Leaderboard view
- **Tasks & Allocations:** Assessment task management
- **Admin Panel:** `/admin/` — Full data management

---

## 🗄️ Database Models

The `school` app includes models for:

- Students
- Streams / Classes
- Assessment Tasks
- Results / Scores
- Allocations
- And more...

> Models are optimized with custom managers and indexes — see `DATABASE_OPTIMIZATION.md`

---

## 📊 Additional Resources

- `FRONTEND_SETUP.md` — Frontend customization guide
- `DATABASE_OPTIMIZATION.md` — Performance tuning
- `OPTIMIZATION_SUMMARY.md` — Summary of improvements
- `QUICK_REFERENCE.md` — Quick commands & tips

---

## 🤝 Contributing

1. Fork the project
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License — see the `LICENSE` file for details (create one if it doesn't exist).

---

*Made with ❤️ for Kenyan CBC Senior Schools*