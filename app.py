from flask import Flask, render_template, request, redirect, url_for, send_file, flash, make_response
from flask_sqlalchemy import SQLAlchemy
import csv
from io import StringIO, BytesIO
from datetime import datetime

app = Flask(__name__)

# Configurations for SQLAlchemy and secret key for flashing messages
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.secret_key = 'supersecretkey'
db = SQLAlchemy(app)

# Database model for inventory items
class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    item_number = db.Column(db.String(100), nullable=False) 
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    last_changed = db.Column(db.DateTime, nullable=True)

# Function to get the current theme from cookies
def get_theme():
    return request.cookies.get('theme', 'light')

# Route for the main inventory page with sorting functionality
@app.route('/')
def index():
    # Get sorting parameters from URL query strings
    sort_by = request.args.get('sort_by', 'date_added')
    order = request.args.get('order', 'asc')

    if order == 'asc':
        items = InventoryItem.query.order_by(
            db.asc(InventoryItem.date_added), 
            db.asc(InventoryItem.item_name),  
            db.asc(InventoryItem.item_number), 
            db.asc(InventoryItem.quantity)   
        ).all()
    else:
        items = InventoryItem.query.order_by(
            db.desc(InventoryItem.date_added), 
            db.desc(InventoryItem.item_name), 
            db.desc(InventoryItem.item_number),
            db.desc(InventoryItem.quantity)   
        ).all()

    theme = get_theme()

    # Render the index.html page with the sorted items and theme
    return render_template('index.html', items=items, mode='index', sort_by=sort_by, order=order, theme=theme)

# Route for adding new items to the inventory
@app.route('/add', methods=['POST'])
def add_item():
    # Get item data from the form
    item_number = request.form['item_number']
    item_name = request.form['item_name']
    quantity = request.form['quantity']
    price = request.form['price']

    # Create a new inventory item
    new_item = InventoryItem(item_number=item_number, item_name=item_name, quantity=quantity, price=price)

    # Add the item to the database
    db.session.add(new_item)
    db.session.commit()

    # Flash a success message to the user
    flash('Item added successfully!', 'success')

    # Redirect back to the index page
    return redirect(url_for('index'))

# Route for editing an existing item
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_item(id):
    # Fetch the item by its ID, return 404 error if not found
    item = InventoryItem.query.get_or_404(id)

    if request.method == 'POST':
        updated_item_name = request.form['item_name']
        updated_item_number = request.form['item_number']
        updated_quantity = int(request.form['quantity'])
        updated_price = float(request.form['price'])
        updated_date_added = datetime.strptime(request.form['date_added'], '%Y-%m-%d')

        # Check if any values have changed
        if (updated_item_number == item.item_number and
                updated_item_name == item.item_name and
                updated_quantity == item.quantity and
                updated_price == item.price and
                updated_date_added == item.date_added):
            
            # Flash a message that nothing has changed
            flash('Nothing has been changed', 'info')
        else:
            item.item_number = updated_item_number
            item.item_name = updated_item_name
            item.quantity = updated_quantity
            item.price = updated_price
            item.date_added = updated_date_added
            item.last_changed = datetime.utcnow() 
            db.session.commit()
            flash('Item updated successfully!', 'success')

        # Redirect back to the index page
        return redirect(url_for('index'))

    theme = get_theme()

    # If the request is GET, render the index.html in 'edit' mode with the item details and theme
    return render_template('index.html', item=item, mode='edit', theme=theme)

# Route for deleting an item
@app.route('/delete/<int:id>')
def delete_item(id):
    # Fetch the item by its ID, return 404 error if not found
    item = InventoryItem.query.get_or_404(id)

    db.session.delete(item)
    db.session.commit()

    # Flash a success message to the user
    flash('Item deleted successfully!', 'success')

    # Redirect back to the index page
    return redirect(url_for('index'))

# Route for exporting inventory to a CSV file
@app.route('/export')
def export_csv():
    # Query all items in the inventory
    items = InventoryItem.query.all()

    # Generate CSV data in memory
    si = StringIO()  # Use StringIO to generate CSV in memory
    writer = csv.writer(si) 
    writer.writerow(['Date Added', 'Item Name', 'ID', 'Quantity', 'Price', 'Last Changed'])  # Write CSV headers

    # Write each item's data to the CSV, format the date as 'YYYY/MM/DD' for both dates
    for item in items:
        date_added = item.date_added.strftime('%Y/%m/%d')

        last_changed = item.last_changed.strftime('%Y/%m/%d') if item.last_changed else ''

        # Write the row with properly formatted dates
        writer.writerow([
            date_added,              # Format date_added to 'YYYY/MM/DD'
            item.item_name,          # Item name
            item.id,                 # ID
            item.quantity,           # Quantity
            item.price,              # Price
            last_changed             # Last changed (formatted or empty)
        ])

    # Get the CSV data as a string and encode it to bytes
    output = si.getvalue().encode('utf-8')
    si.close()  # Close the StringIO object

    # Return the CSV as a downloadable file
    return send_file(
        BytesIO(output),  
        mimetype='text/csv', 
        as_attachment=True,  
        download_name='inventory.csv'  # Name the CSV file
    )

# Route for importing inventory from a CSV file and replacing old data
@app.route('/import', methods=['GET', 'POST'])
def import_csv():
    if request.method == 'POST':
        # Get the uploaded file
        file = request.files['file']

        # If no file is uploaded, flash an error message and redirect
        if not file:
            flash('No file uploaded!', 'danger')
            return redirect(url_for('import_csv'))

        # Clear all existing items from the database before importing new data
        InventoryItem.query.delete()
        db.session.commit()

        # Read the CSV data
        stream = StringIO(file.stream.read().decode('UTF8'))
        reader = csv.reader(stream)
        next(reader)  # Skip the header row

        # Add each row from the CSV as a new inventory item
        for row in reader:
            # Handle date_added and last_changed date formats (allow empty last_changed)
            date_added = datetime.strptime(row[0], '%Y/%m/%d')  # Assuming the CSV has the format 'YYYY/MM/DD'
            item_name = row[1]
            item_number = row[2]
            quantity = int(row[3])
            price = float(row[4])
            
            # If last_changed is present, format it; otherwise, set it to None
            last_changed = datetime.strptime(row[5], '%Y/%m/%d') if row[5] else None

            # Create a new inventory item
            new_item = InventoryItem(
                date_added=date_added, 
                item_name=item_name,
                item_number=item_number,
                quantity=quantity,
                price=price,
                last_changed=last_changed  # Can be None if not present in the CSV
            )

            # Add the item to the database session
            db.session.add(new_item)

        # Commit all changes to the database
        db.session.commit()

        # Flash a success message
        flash('CSV imported successfully!', 'success')

        # Redirect back to the index page
        return redirect(url_for('index'))

    theme = get_theme()

    # Render the index.html in 'import' mode to display the import form and theme
    return render_template('index.html', mode='import', theme=theme)

# Route to toggle the theme
@app.route('/toggle_theme')
def toggle_theme():
    # Get the current theme from cookies
    current_theme = request.cookies.get('theme', 'light')
    # Toggle the theme
    new_theme = 'dark' if current_theme == 'light' else 'light'
    # Create a response object
    resp = redirect(request.referrer or url_for('index'))
    # Set the new theme in cookies
    resp.set_cookie('theme', new_theme, max_age=60*60*24*365)  # Cookie expires in 1 year
    return resp

# Initialize the database and create the required tables if they don't exist
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
