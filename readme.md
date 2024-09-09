Inventory Management System
This is a simple web-based inventory management system built using Flask and SQLAlchemy, designed to manage inventory items with the ability to import and export data using CSV files.
---

Features:
- CRUD operations: Create, read, update, and delete inventory items (item name, quantity, price).
- CSV Import/Export: Easily export the inventory list to a CSV file and import inventory data from a CSV file, replacing old data.
- Sorting: Sort inventory items by name, quantity, or price in ascending or descending order.
- Flash Messages: Informative messages displayed to the user after each action (e.g., item added, updated, or deleted).
- User-Friendly UI: Responsive, intuitive design with action buttons (add, edit, delete, export, import).
- Cancel Actions: Cancel buttons in edit and import modes, allowing users to return to the main page without making changes.
---

Technology Stack:
- Backend: Flask (Python), SQLAlchemy (SQLite database).
- Frontend: HTML, CSS (using flexbox for layout), Bootstrap-style buttons.
- CSV Support: Python csv module for handling CSV files.
---



Setup Instructions:
1.Open a terminal or command prompt

2.Activate the virtual environment:

-On Windows:
Enter and run *venv\Scripts\activate*

-On macOS/Linux:
Enter and run *source venv/bin/activate*

3.Enter and run *python "Your File location"\app.py* 

4.Open the browser and go to http://127.0.0.1:5000/ to view the inventory management dashboard.
