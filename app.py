from flask import Flask, render_template, request, redirect, url_for, send_file, flash
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


# Route for the main inventory page with sorting functionality
@app.route('/')
def index():
    # Get sorting parameters from URL query strings
    sort_by = request.args.get('sort_by', 'date_added')  # Sort by 'item_name' by default
    order = request.args.get('order', 'asc')  # Default sorting order is ascending

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

    # Render the index.html page with the sorted items
    return render_template('index.html', items=items, mode='index', sort_by=sort_by, order=order)

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
        # Get the updated values from the form
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
            # If values are changed, update the item's attributes and commit
            item.item_number = updated_item_number
            item.item_name = updated_item_name
            item.quantity = updated_quantity
            item.price = updated_price
            item.date_added = updated_date_added
            db.session.commit()
            flash('Item updated successfully!', 'success')

        # Redirect back to the index page
        return redirect(url_for('index'))

    # If the request is GET, render the index.html in 'edit' mode with the item details
    return render_template('index.html', item=item, mode='edit')

# Route for deleting an item
@app.route('/delete/<int:id>')
def delete_item(id):
    # Fetch the item by its ID, return 404 error if not found
    item = InventoryItem.query.get_or_404(id)

    # Delete the item from the database
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
    writer = csv.writer(si)  # Initialize the CSV writer
    writer.writerow(['Date Added', 'Item Name', 'ID', 'Quantity', 'Price'])  # Write CSV headers

    # Write each item's data to the CSV, format the date as 'YYYY-MM-DD'
    for item in items:
        writer.writerow([item.date_added.strftime('%Y-%m-%d'), item.item_name, item.id, item.quantity, item.price])

    # Get the CSV data as a string and encode it to bytes
    output = si.getvalue().encode('utf-8')
    si.close()  # Close the StringIO object

    # Return the CSV as a downloadable file
    return send_file(
        BytesIO(output),  
        mimetype='text/csv', 
        as_attachment=True,  
        download_name='inventory.csv' 
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
            # Parse the date and other values (Date Added, Item Name, ID, Quantity, Price)
            date_added = datetime.strptime(row[0], '%Y-%m-%d')  # Parse the date from 'YYYY-MM-DD' format
            item_name = row[1]
            item_number = row[2]
            quantity = int(row[3])
            price = float(row[4])

            # Create a new inventory item
            new_item = InventoryItem(
                date_added=date_added,  # Use the parsed date
                item_name=item_name,
                item_number=item_number,
                quantity=quantity,
                price=price
            )

            # Add the item to the database session
            db.session.add(new_item)

        # Commit all changes to the database
        db.session.commit()

        # Flash a success message
        flash('CSV imported successfully!', 'success')

        # Redirect back to the index page
        return redirect(url_for('index'))

    # Render the index.html in 'import' mode to display the import form
    return render_template('index.html', mode='import')

# Initialize the database and create the required tables if they don't exist
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
