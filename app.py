from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from celery import Celery
import datetime

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///todo.db'
app.config['BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='armanii787890@gmail.com',
    MAIL_PASSWORD='Armanii_098787',
)

db = SQLAlchemy(app)
mail = Mail(app)

def make_celery(app):
    celery = Celery(app.import_name, broker=app.config['BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task
    class ContextTask(TaskBase):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery

celery = make_celery(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.Integer, nullable=False)
    due_date = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    reminder_date = db.Column(db.String(50), nullable=True)
    reminder_time = db.Column(db.String(5), nullable=False, default='5')
    email = db.Column(db.String(150), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class UserPreferences(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    theme = db.Column(db.String(50), nullable=True)
    font = db.Column(db.String(50), nullable=True)
    color = db.Column(db.String(50), nullable=True)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            user_preferences = UserPreferences(user_id=new_user.id)
            db.session.add(user_preferences)
            db.session.commit()
            flash('Registration successful')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            session['user_id'] = user.id
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    sort_by = request.args.get('sort_by', 'due_date')
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(sort_by).all()
    user_preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
    return render_template('index.html', tasks=tasks, preferences=user_preferences)

@app.route('/add', methods=['POST'])
@login_required
def add_task():
    task_name = request.form.get('task')
    priority = request.form.get('priority')
    due_date = request.form.get('due_date')
    category = request.form.get('category')
    reminder_date = request.form.get('reminder_date')
    reminder_time = request.form.get('reminder_time')
    email = request.form.get('email')

    if task_name and priority and due_date and reminder_date and reminder_time and email:
        new_task = Task(task=task_name, priority=priority, due_date=due_date, category=category, reminder_date=reminder_date, reminder_time=reminder_time, email=email, user_id=current_user.id)
        db.session.add(new_task)
        db.session.commit()

        reminder_datetime = datetime.datetime.strptime(f"{reminder_date} {reminder_time}", '%Y-%m-%d %H:%M')
        send_reminder.apply_async(args=[current_user.id, new_task.task, email], eta=reminder_datetime)
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
@login_required
def delete_task(task_id):
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        db.session.delete(task)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        theme = request.form.get('theme')
        font = request.form.get('font')
        color = request.form.get('color')
        preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
        if preferences:
            preferences.theme = theme
            preferences.font = font
            preferences.color = color
            db.session.commit()
        return redirect(url_for('index'))
    preferences = UserPreferences.query.filter_by(user_id=current_user.id).first()
    return render_template('settings.html', preferences=preferences)

@celery.task
def send_reminder(user_id, task, email):
    user = User.query.get(user_id)
    msg = Message('Task Reminder', recipients=[email], body=f"Reminder: Your task '{task}' is due soon!")
    mail.send(msg)

if __name__ == "__main__":
    app.run(debug=True)
