import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from reportlab.pdfgen import canvas 
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from io import BytesIO 

# Setup
app = Flask(__name__)

# Database  setup
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'student_finance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app) 

# Database Table 
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    amount = db.Column(db.Float, nullable=False) 
    type = db.Column(db.String(10), nullable=False)
    # Allocation choice: 'Tuition' or 'General'
    allocation = db.Column(db.String(10), nullable=True) 


# Function to execute the data collection
def get_financial_summary():
    transactions = Transaction.query.order_by(Transaction.date.desc()).all()
    
    # sum for the total of the categories
    total_tuition_cost = sum(t.amount for t in transactions if 
                             t.type == 'Expense' and t.category == 'Tuition')

    tuition_aid_applied = sum(t.amount for t in transactions if 
                              t.type == 'Income' and t.allocation == 'Tuition')

    total_tuition_left = total_tuition_cost - tuition_aid_applied
    
    general_income = sum(t.amount for t in transactions if 
                         t.type == 'Income' and t.allocation == 'General')
    
    general_expenses = sum(t.amount for t in transactions if 
                           t.type == 'Expense' and t.category != 'Tuition')
 
    total_balance = general_income - general_expenses

    income_categories = db.session.query(
        Transaction.category, db.func.sum(Transaction.amount)
    ).filter(Transaction.type == 'Income', Transaction.allocation == 'General').group_by(Transaction.category).all()

    expense_categories = db.session.query(
        Transaction.category, db.func.sum(Transaction.amount)
    ).filter(Transaction.type == 'Expense', Transaction.category != 'Tuition').group_by(Transaction.category).all()

    chart_data = {
        'income_labels': [c[0] for c in income_categories],
        'income_values': [c[1] for c in income_categories],
        'expense_labels': [c[0] for c in expense_categories],
        'expense_values': [abs(c[1]) for c in expense_categories],
    }

    # return
    return transactions, general_income, general_expenses, total_balance, chart_data, total_tuition_left, total_tuition_cost


# Function to download pdf data
def generate_pdf_report(transactions, general_income, general_expenses, total_balance):
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "Student Financial Report")
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 110, f"General Income (Funds for Expenses): ${general_income:,.2f}")
    p.drawString(250, height - 110, f"General Expenses: ${general_expenses:,.2f}")
    p.drawString(450, height - 110, f"Net Balance: ${total_balance:,.2f}")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "Transaction History")
    
    y_pos = height - 185
    row_height = 15
    for t in transactions:
        p.setFillColor(colors.black)
        
        p.drawString(50, y_pos, t.date.strftime('%Y-%m-%d'))
        p.drawString(150, y_pos, t.type)
        p.drawString(250, y_pos, t.category)
        p.drawString(350, y_pos, t.description if t.description else '-')
        
        p.setFillColor(colors.black)
        p.drawString(450, y_pos, f"${t.amount:,.2f}")
            
        y_pos -= row_height

    p.save()
    buffer.seek(0)
    return buffer

# Routes (Webpage URLs)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # adding new transactions
        date = request.form['date']
        type = request.form['type']
        category = request.form['category']
        description = request.form['description']
        amount = float(request.form['amount'])
        
        # where will it go?
        allocation = request.form.get('allocation') 

        new_transaction = Transaction(
            date=datetime.strptime(date, '%Y-%m-%d').date(),
            type=type,
            category=category,
            description=description,
            amount=amount,
            allocation=allocation
        )
        
        db.session.add(new_transaction)
        db.session.commit()
        return redirect(url_for('index'))

    # load dashboard
    transactions, general_income, general_expenses, total_balance, chart_data, total_tuition_left, total_tuition_cost = get_financial_summary()
    
    # HTML
    return render_template(
        'index.html', 
        transactions=transactions, 
        general_income=general_income, 
        general_expenses=general_expenses, 
        total_balance=total_balance,
        chart_data=chart_data,
        total_tuition_left=total_tuition_left,
        total_tuition_cost=total_tuition_cost
    )

@app.route('/delete/<int:id>', methods=['POST'])
def delete_transaction(id):
    # Handle deleting a transaction
    transaction_to_delete = Transaction.query.get_or_404(id)
    db.session.delete(transaction_to_delete)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/report/pdf')
def generate_report():
    # Handle PDF generation request
    transactions, general_income, general_expenses, total_balance, _, _ , _= get_financial_summary()
    
    pdf_buffer = generate_pdf_report(transactions, general_income, general_expenses, total_balance)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name='financial_report.pdf',
        mimetype='application/pdf'
    )

# Run the app
if __name__ == '__main__':
    with app.app_context():
        db.create_all() 
    app.run(debug=True)