from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
import os
from werkzeug.utils import secure_filename
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['UPLOAD_FOLDER'] = 'static/img'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')  
    balance = db.Column(db.Float, default=0.0)
    address = db.Column(db.String(200))
    
    def set_password(self, password):
        self.password = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    image = db.Column(db.String(100))
    stock = db.Column(db.Integer, default=10)

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship('Product')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    items = db.relationship('OrderItem', backref='order')
    user = db.relationship('User', backref='orders')  

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    product = db.relationship('Product')

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='manager').first():
        manager = User(username='manager', role='manager', balance=0)
        manager.set_password('manager123')
        db.session.add(manager)
        db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято!', 'error')
            return redirect(url_for('register'))
        
        new_user = User(username=username, balance=1000)
        new_user.set_password(password) 
        db.session.add(new_user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash(f'Добро пожаловать, {username}!', 'success')
            
            if user.role == 'manager':
                return redirect(url_for('manager_panel'))
            else:
                return redirect(url_for('shop'))
        else:
            flash('Неверное имя пользователя или пароль!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы успешно вышли из системы.', 'info')
    return redirect(url_for('index'))

@app.route('/shop')
def shop():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))
    
    products = Product.query.all()
    return render_template('shop.html', products=products)

@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    cart_item = CartItem.query.filter_by(user_id=user_id, product_id=product_id).first()
    
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItem(user_id=user_id, product_id=product_id)
        db.session.add(cart_item)
    
    db.session.commit()
    flash('Товар добавлен в корзину!', 'success')
    return redirect(url_for('shop'))

@app.route('/cart', methods=['GET', 'POST'])
def cart():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    if request.method == 'POST' and 'coupon' in request.form:
        coupon = request.form['coupon']
        user = User.query.get(user_id)
        
        if coupon == 'ELITE500':
            user.balance += 500
            flash('Купон на 500 рублей применен!', 'success')
        elif coupon == 'ELITE1000':
            user.balance += 1000
            flash('Купон на 1000 рублей применен!', 'success')
        else:
            flash('Неверный купон!', 'error')
        
        db.session.commit()
        return redirect(url_for('cart'))
    
    if request.method == 'POST' and 'address' in request.form:
        address = request.form['address']
        user = User.query.get(user_id)
        cart_items = CartItem.query.filter_by(user_id=user_id).all()
        
        if not cart_items:
            flash('Ваша корзина пуста!', 'error')
            return redirect(url_for('cart'))
        
        total = sum(item.product.price * item.quantity for item in cart_items)
        
        if user.balance < total:
            flash('Недостаточно средств на балансе!', 'error')
            return redirect(url_for('cart'))
        
        from datetime import datetime
        order = Order(
            user_id=user_id,
            total=total,
            address=address,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(order)
        db.session.commit()
        
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                price=item.product.price
            )
            db.session.add(order_item)
            item.product.stock -= item.quantity
            db.session.delete(item)
        
        user.balance -= total
        db.session.commit()
        
        flash(f'Заказ оформлен! Номер заказа: {order.id}', 'success')
        return redirect(url_for('profile'))
    
    cart_items = CartItem.query.filter_by(user_id=user_id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    user = User.query.get(user_id)
    
    return render_template('cart.html', cart_items=cart_items, total=total, user=user)

@app.route('/remove_from_cart/<int:item_id>')
def remove_from_cart(item_id):
    if 'user_id' not in session:
        flash('Пожалуйста, войните в систему.', 'warning')
        return redirect(url_for('login'))
    
    cart_item = CartItem.query.get(item_id)
    if cart_item and cart_item.user_id == session['user_id']:
        db.session.delete(cart_item)
        db.session.commit()
        flash('Товар удален из корзины.', 'info')
    
    return redirect(url_for('cart'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Пожалуйста, войдите в систему.', 'warning')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = User.query.get(user_id)
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.id.desc()).all()
    
    return render_template('profile.html', user=user, orders=orders)

@app.route('/manager')
def manager_panel():
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    try:
        orders = Order.query.all()
        
        from collections import defaultdict
        sales_by_date = defaultdict(float)
        
        for order in orders:
            date = order.date.split()[0]
            sales_by_date[date] += order.total
        
        dates = sorted(sales_by_date.keys())
        amounts = [sales_by_date[date] for date in dates]
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(dates, amounts, marker='o')
        ax.set_title('Продажи по дням')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Сумма (руб)')
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        img = io.BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight')
        img.seek(0)
        plot_url = base64.b64encode(img.getvalue()).decode('utf8')
        
        plt.close(fig)
        
        products = Product.query.all()
        orders = db.session.query(Order, User).join(User, Order.user_id == User.id)\
                  .order_by(Order.id.desc()).all()
        
        return render_template('manager.html', 
                            products=products, 
                            orders=orders, 
                            plot_url=plot_url)
    
    except Exception as e:
        print(f"Ошибка при создании графика: {e}")
        flash('Ошибка при создании отчета', 'error')
        return redirect(url_for('manager_panel'))
    
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        stock = int(request.form['stock'])
        
        if 'image' not in request.files:
            flash('Не выбрано изображение товара!', 'error')
            return redirect(request.url)
        
        image = request.files['image']
        if image.filename == '':
            flash('Не выбрано изображение товара!', 'error')
            return redirect(request.url)
        
        if image:
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            
            new_product = Product(
                name=name,
                price=price,
                description=description,
                image=filename,
                stock=stock
            )
            
            db.session.add(new_product)
            db.session.commit()
            
            flash('Товар успешно добавлен!', 'success')
            return redirect(url_for('manager_panel'))
    
    return render_template('add_product.html')

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    product = Product.query.get(product_id)
    if product:
        if product.image:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product.image))
            except:
                pass
        
        db.session.delete(product)
        db.session.commit()
        flash('Товар успешно удален!', 'success')
    
    return redirect(url_for('manager_panel'))

@app.route('/delete_order/<int:order_id>')
def delete_order(order_id):
    if 'user_id' not in session or session.get('role') != 'manager':
        flash('Доступ запрещен!', 'error')
        return redirect(url_for('index'))
    
    order = Order.query.get(order_id)
    if order:
        OrderItem.query.filter_by(order_id=order.id).delete()
        db.session.delete(order)
        db.session.commit()
        flash('Заказ успешно удален!', 'success')
    
    return redirect(url_for('manager_panel'))

if __name__ == '__main__':
    app.run(debug=True)