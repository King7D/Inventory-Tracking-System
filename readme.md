# EVO Inventory Tracking

A pragmatic inventory web app built with Flask + SQLAlchem*. It provides a clean dashboard, CSV import/export, reorder alerts, and timezone-aware timestamps that follow the computer running the app.

## Features

- **Dashboard**
  - Columns: Date Added, Item Name, SKU, Available, On-Transit, Total, Reorder Point, Price, Total Value, Last Changed
  - Total = Available + On-Transit
  - Orange highlight + page banner when Total ≤ Reorder Point
  - Sort by date, name, SKU, price, available, or "needs reorder"
  - Search and pagination; light/dark theme toggle

- **Items**
  - Fields: SKU, Name, Price, On-hand, On-Transit, Reorder Point
  - On-hand updates the physical quantity in the default location
  - Available = On-hand − Allocated (allocated assumed 0 unless extended)

- **CSV Import & Export**
  - Export/Import header (required):  
    `Date Added, Item Name, SKU, Available, On-Transit, Total, Reorder Point, Price, Total Value, Last Changed`
  - Import is a two-step wizard: Upload → Preview → Commit (Upsert/Merge or Replace All)
  - Minutes-level timestamp support (HH:MM)

- **Timezone Awareness**
  - Displays and exports in local (computer) timezone
  - Stores datetimes internally in UTC (naive) for consistency

- **Auth & Roles**
  - Login with seeded users (`users_config.py`)
  - Roles: `admin`, `ops`, `buyer`, `viewer` (mutations restricted)
  - CSRF protection

## Tech Stack

- Flask, SQLAlchemy, Flask-Login, Flask-WTF
- SQLite by default (use `DATABASE_URL` to switch)
- `tzlocal` for system timezone detection
- Simple HTML/CSS UI (dark-mode friendly)

## Setup Instructions:

1.Open a terminal or command prompt

2.Activate the virtual environment:

-On Windows:
Enter and run *venv\Scripts\activate*

-On macOS/Linux:
Enter and run *source venv/bin/activate*

3.Enter and run *python "Your File location"\app.py* 

4.Open the browser and go to http://127.0.0.1:5000/ to view the inventory management dashboard.

## Requirements:
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask-WTF
- email-validator
- tzlocal

---

## Screenshots:
<img width="1010" height="670" alt="evo1" src="https://github.com/user-attachments/assets/3ef1025d-a863-4bf2-b7fe-c7a8bb741288" />
<img width="1286" height="614" alt="evo2" src="https://github.com/user-attachments/assets/1fd3ca68-6373-4aad-8546-4e73e1190d49" />
<img width="1237" height="594" alt="evo3" src="https://github.com/user-attachments/assets/50831024-9fa7-42f6-b63d-ba0550fd1b7c" />
<img width="1239" height="508" alt="evo4" src="https://github.com/user-attachments/assets/1dc6dd2a-9133-4873-9bc1-ac341162a34a" />




