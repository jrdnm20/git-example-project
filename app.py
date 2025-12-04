import os
from datetime import datetime
from flask_login import UserMixin, LoginManager, login_user, logout_user, current_user, login_required
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
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
app.config['SECRET_KEY'] = 'your_super_secret_key_change_me_in_production'

db = SQLAlchemy(app) 

# login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False) 
    transactions = db.relationship('Transaction', backref='user', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# database Table 
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    amount = db.Column(db.Float, nullable=False) 
    type = db.Column(db.String(10), nullable=False)

    # choice: tuition or general total balance
    allocation = db.Column(db.String(10), nullable=True) 

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# function to execute the data collection
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

    # pdf sizing
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    #this is the summary part
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "Student Financial Report")
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 110, f"General Income (Funds for Expenses): ${general_income:,.2f}")
    p.drawString(250, height - 110, f"General Expenses: ${general_expenses:,.2f}")
    p.drawString(450, height - 110, f"Net Balance: ${total_balance:,.2f}")
    
    # header for transaction history
    # ISSUE WHERE ITS OVERFLOWING OVER THE LETTER, FIX LATER
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 150, "Transaction History")
    
    p.setFont("Helvetica-Bold", 10)
    p.setFillColor(colors.gray)
    p.drawString(50, height - 175, "Date")
    p.drawString(130, height - 175, "Type")
    p.drawString(190, height - 175, "Category")
    p.drawString(310, height - 175, "Description") 
    p.drawString(450, height - 175, "Fund")
    p.drawString(520, height - 175, "Amount") 
    
    #  line to seperate
    p.line(50, height - 180, width - 50, height - 180)

    # rows for the transaction history
    y_pos = height - 195 
    row_height = 15
    p.setFont("Helvetica", 10)

    for t in transactions:
        # page break check
        if y_pos < 72:
            p.showPage()
            y_pos = height - 50 # Reset Y position for new page
            p.setFont("Helvetica", 10)

        p.setFillColor(colors.black)
        

        p.drawString(50, y_pos, t.date.strftime('%Y-%m-%d'))
        p.drawString(130, y_pos, t.type)
        p.drawString(190, y_pos, t.category)
        
        # make sure that description is not too long
        description_text = (t.description[:20] + '...') if t.description and len(t.description) > 20 else t.description
        p.drawString(310, y_pos, description_text if description_text else '-')
        
        p.drawString(450, y_pos, t.allocation if t.allocation else '-')
        p.drawString(520, y_pos, f"${t.amount:,.2f}")
            
        y_pos -= row_height # Move down for the next row

    p.save()
    buffer.seek(0)
    return buffer

# routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'] 
        user = User.query.filter_by(username=username).first()
        
        if user and user.password == password:
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Login Failed. Check username and password.', 'danger')
            
    return render_template('login.html', action='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'warning')
            return redirect(url_for('register'))

        
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('login.html', action='register')

@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
# make loggin in required to access
@login_required
def index():
    if request.method == 'POST':
        #transactions
        date = request.form['date']
        type = request.form['type']
        category = request.form['category']
        description = request.form['description']
        amount = float(request.form['amount'])

        tuition_percent_raw = request.form.get('tuition_percent', '0')
        tuition_percent = float(tuition_percent_raw) / 100.0
        general_percent = 1.0 - tuition_percent
        
        input_date = datetime.strptime(date, '%Y-%m-%d').date()

        # allow users to split income, so  put a certain amount to pay tuition and have the rest go to total balance
        if type == 'Income' and tuition_percent > 0 and tuition_percent < 1.0:
            #tution allocation
            tuition_amount = amount * tuition_percent
            tuition_transaction = Transaction(
                date=input_date,
                type='Income',
                category=category,
                description=f"{description} (Tuition Allocation: {tuition_percent*100:.0f}%)",
                amount=tuition_amount,
                allocation='Tuition'
            )
            db.session.add(tuition_transaction)

            # total balance (general) allocation
            general_amount = amount * general_percent
            general_transaction = Transaction(
                date=input_date,
                type='Income',
                category=category,
                description=f"{description} (General Allocation: {general_percent*100:.0f}%)",
                amount=general_amount,
                allocation='General'
            )
            db.session.add(general_transaction)

    
        else:
            # set the allocation based on the transaction type and split choice
            if type == 'Income':
                # ff tuition_percent is 1.0 (100%), allocate to Tuition
                if tuition_percent == 1.0:
                    allocation = 'Tuition'
                # if tuition_percent is 0.0 (0%), allocate to General
                else: # This covers 0% split and the original Income handling
                    allocation = 'General'
            else:
                # expenses do not need an allocation value for the balance calculation
                allocation = None 

        new_transaction = Transaction(
            date=input_date,
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

@app.route('/transfer_to_tuition', methods=['POST'])
@login_required
def transfer_to_tuition():
    amount = float(request.form['transfer_amount'])
    
    #for the expenses, deduct the amount from the total general balance
    expense_transaction = Transaction(
        date=datetime.utcnow().date(),
        type='Expense',
        category='Transfer',
        description='Transfer to Tuition Fund (from General)',
        amount=amount,
        allocation='General' # This ensures it lowers the General Balance
    )
    db.session.add(expense_transaction)

    # for the income, add the amount to tuition 
    income_transaction = Transaction(
        date=datetime.utcnow().date(),
        type='Income',
        category='Transfer',
        description='Tuition Payment (from General Balance)',
        amount=amount,
        allocation='Tuition' 
    )
    db.session.add(income_transaction)
    
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/delete/<int:id>', methods=['POST'])
def delete_transaction(id):
    # Handle deleting a transaction
    transaction_to_delete = Transaction.query.get_or_404(id)
    db.session.delete(transaction_to_delete)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/report/pdf')
@login_required
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