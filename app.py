from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from werkzeug.utils import secure_filename
import os


from models import db, User, Task, Category, Tag, Subtask
from forms import RegistrationForm, LoginForm, TaskForm, CategoryForm

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tasks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

# Инициализация расширений
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему для доступа к этой странице'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Создаем папку для загрузок, если её нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ========== Маршруты ==========

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter(
            (User.username == form.username.data) | (User.email == form.email.data)
        ).first()
        
        if existing_user:
            flash('Пользователь с таким именем или email уже существует', 'danger')
            return render_template('register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data)
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Теперь вы можете войти', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f'Добро пожаловать, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Базовая статистика для дашборда
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status == 'completed')
    overdue_tasks = sum(1 for t in tasks if t.is_overdue)
    in_progress_tasks = sum(1 for t in tasks if t.status == 'in_progress')
    
    completion_rate = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    return render_template('dashboard.html',
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completion_rate=completion_rate)

# Временный маршрут для проверки
@app.route('/test')
def test():
    return render_template('index.html', title='Тест', items=['Flask', 'Jinja2', 'SQLAlchemy'])

# ========== Управление задачами (CRUD) ==========

@app.route('/tasks')
@login_required
def tasks():
    """Список всех задач пользователя"""
    # Базовый запрос - только задачи текущего пользователя
    query = Task.query.filter_by(user_id=current_user.id)
    
    # Получаем параметры фильтрации из URL
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    category_filter = request.args.get('category', '')
    
    # Применяем фильтры
    if status_filter:
        query = query.filter_by(status=status_filter)
    if priority_filter:
        query = query.filter_by(priority=priority_filter)
    if category_filter and category_filter.isdigit():
        query = query.filter_by(category_id=int(category_filter))
    
    # Сортировка
    sort_by = request.args.get('sort', 'deadline')
    if sort_by == 'deadline':
        query = query.order_by(Task.deadline.asc())
    elif sort_by == 'priority':
        query = query.order_by(Task.priority.desc())
    elif sort_by == 'created_at':
        query = query.order_by(Task.created_at.desc())
    elif sort_by == 'title':
        query = query.order_by(Task.title.asc())
    else:
        query = query.order_by(Task.deadline.asc())
    
    # Поиск
    search_query = request.args.get('search', '')
    if search_query:
        query = query.filter(
            Task.title.contains(search_query) | Task.description.contains(search_query)
        )
    
    tasks_list = query.all()
    
    # Получаем категории пользователя для фильтра
    categories = Category.query.filter_by(user_id=current_user.id).all()
    
    return render_template('tasks.html', 
                         tasks=tasks_list, 
                         categories=categories,
                         current_filters={
                             'status': status_filter,
                             'priority': priority_filter,
                             'category': category_filter,
                             'sort': sort_by,
                             'search': search_query
                         })

@app.route('/task/create', methods=['GET', 'POST'])
@login_required
def task_create():
    """Создание новой задачи"""
    form = TaskForm()
    
    # Загружаем категории пользователя для выбора
    categories = Category.query.filter_by(user_id=current_user.id).all()
    form.category_id.choices = [(0, 'Без категории')] + [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        task = Task(
            title=form.title.data,
            description=form.description.data,
            status=form.status.data,
            priority=form.priority.data,
            deadline=form.deadline.data,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        
        flash('Задача успешно создана!', 'success')
        return redirect(url_for('tasks'))
    
    return render_template('task_form.html', form=form, title='Создать задачу')

@app.route('/task/<int:task_id>')
@login_required
def task_detail(task_id):
    """Просмотр одной задачи"""
    task = Task.query.get_or_404(task_id)
    
    # Проверяем, что задача принадлежит текущему пользователю
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    return render_template('task_detail.html', task=task)

@app.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def task_edit(task_id):
    """Редактирование задачи"""
    task = Task.query.get_or_404(task_id)
    
    # Проверяем доступ
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    form = TaskForm(obj=task)
    
    # Загружаем категории
    categories = Category.query.filter_by(user_id=current_user.id).all()
    form.category_id.choices = [(0, 'Без категории')] + [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        task.title = form.title.data
        task.description = form.description.data
        task.status = form.status.data
        task.priority = form.priority.data
        task.deadline = form.deadline.data
        task.category_id = form.category_id.data if form.category_id.data != 0 else None
        task.updated_at = datetime.utcnow()
        
        db.session.commit()
        flash('Задача успешно обновлена!', 'success')
        return redirect(url_for('task_detail', task_id=task.id))
    
    # Заполняем форму текущими значениями
    form.category_id.data = task.category_id if task.category_id else 0
    
    return render_template('task_form.html', form=form, title='Редактировать задачу', task=task)

@app.route('/task/<int:task_id>/delete', methods=['POST'])
@login_required
def task_delete(task_id):
    """Удаление задачи"""
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    db.session.delete(task)
    db.session.commit()
    flash('Задача удалена', 'success')
    return redirect(url_for('tasks'))

@app.route('/task/<int:task_id>/toggle-status', methods=['POST'])
@login_required
def task_toggle_status(task_id):
    """Быстрое переключение статуса задачи (для чекбокса)"""
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        return {'error': 'Нет доступа'}, 403
    
    if task.status == 'completed':
        task.status = 'pending'
    else:
        task.status = 'completed'
    
    db.session.commit()
    return {'success': True, 'new_status': task.status}


@app.route('/task/<int:task_id>/change-status', methods=['POST'])
@login_required
def task_change_status(task_id):
    """Изменение статуса задачи через выпадающий список"""
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    new_status = request.form.get('status')
    if new_status in ['pending', 'in_progress', 'completed']:
        task.status = new_status
        db.session.commit()
        
        # Сообщение об успехе
        status_names = {
            'pending': 'Ожидает',
            'in_progress': 'В работе',
            'completed': 'Выполнена'
        }
        flash(f'Статус задачи "{task.title}" изменен на "{status_names[new_status]}"', 'success')
    
    return redirect(url_for('tasks'))

# ========== Управление категориями ==========

@app.route('/categories')
@login_required
def categories():
    """Страница управления категориями"""
    user_categories = Category.query.filter_by(user_id=current_user.id).all()
    return render_template('categories.html', categories=user_categories)

@app.route('/category/create', methods=['GET', 'POST'])
@login_required
def category_create():
    """Создание новой категории"""
    form = CategoryForm()
    
    if form.validate_on_submit():
        # Проверяем, нет ли уже такой категории у пользователя
        existing = Category.query.filter_by(
            user_id=current_user.id, 
            name=form.name.data
        ).first()
        
        if existing:
            flash('Категория с таким названием уже существует', 'danger')
            return redirect(url_for('categories'))
        
        category = Category(
            name=form.name.data,
            color=form.color.data,
            user_id=current_user.id
        )
        db.session.add(category)
        db.session.commit()
        flash(f'Категория "{category.name}" создана!', 'success')
        return redirect(url_for('categories'))
    
    return render_template('category_form.html', form=form, title='Создать категорию')

@app.route('/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def category_edit(category_id):
    """Редактирование категории"""
    category = Category.query.get_or_404(category_id)
    
    if category.user_id != current_user.id:
        flash('Нет доступа к этой категории', 'danger')
        return redirect(url_for('categories'))
    
    form = CategoryForm(obj=category)
    
    if form.validate_on_submit():
        # Проверяем уникальность имени
        existing = Category.query.filter_by(
            user_id=current_user.id, 
            name=form.name.data
        ).first()
        
        if existing and existing.id != category_id:
            flash('Категория с таким названием уже существует', 'danger')
            return redirect(url_for('categories'))
        
        category.name = form.name.data
        category.color = form.color.data
        db.session.commit()
        flash(f'Категория "{category.name}" обновлена!', 'success')
        return redirect(url_for('categories'))
    
    return render_template('category_form.html', form=form, title='Редактировать категорию', category=category)

@app.route('/category/<int:category_id>/delete', methods=['POST'])
@login_required
def category_delete(category_id):
    """Удаление категории"""
    category = Category.query.get_or_404(category_id)
    
    if category.user_id != current_user.id:
        flash('Нет доступа к этой категории', 'danger')
        return redirect(url_for('categories'))
    
    # У задач, у которых была эта категория, сбрасываем category_id на NULL
    tasks_with_category = Task.query.filter_by(category_id=category_id).all()
    for task in tasks_with_category:
        task.category_id = None
    
    db.session.delete(category)
    db.session.commit()
    flash('Категория удалена', 'success')
    return redirect(url_for('categories'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы при первом запуске
    app.run(debug=True)