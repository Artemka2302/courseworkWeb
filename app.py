from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
import os
import matplotlib
matplotlib.use('Agg')  # Используем backend без GUI
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime, timedelta
from collections import defaultdict

from models import db, User, Task, Category, Tag, Subtask, RecurringRule, Attachment
from forms import RegistrationForm, LoginForm, TaskForm, CategoryForm

# ========== Декоратор для проверки прав администратора ==========
def admin_required(func):
    """Декоратор: доступ только для администратора"""
    from functools import wraps
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'danger')
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash('У вас нет прав доступа к этой странице', 'danger')
            return redirect(url_for('dashboard'))
        return func(*args, **kwargs)
    return decorated_view


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
    """Дашборд с аналитикой и графиками"""
    
    # Получаем все задачи пользователя
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status == 'completed')
    overdue_tasks = sum(1 for t in tasks if t.is_overdue)
    in_progress_tasks = sum(1 for t in tasks if t.status == 'in_progress')
    
    completion_rate = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    # ===== 1. Распределение по приоритетам (круговая диаграмма) =====
    priority_counts = {'high': 0, 'medium': 0, 'low': 0}
    for task in tasks:
        priority_counts[task.priority] += 1
    
    fig1, ax1 = plt.subplots(figsize=(6, 4))
    priority_labels = ['Высокий', 'Средний', 'Низкий']
    priority_sizes = [priority_counts['high'], priority_counts['medium'], priority_counts['low']]
    priority_colors = ['#dc3545', '#ffc107', '#0dcaf0']
    
    # Убираем пустые значения
    non_empty = [(l, s, c) for l, s, c in zip(priority_labels, priority_sizes, priority_colors) if s > 0]
    if non_empty:
        labels, sizes, colors = zip(*non_empty)
        ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
        ax1.axis('equal')
    else:
        ax1.text(0.5, 0.5, 'Нет данных', ha='center', va='center')
        ax1.axis('off')
    
    # Сохраняем график в base64
    buf1 = BytesIO()
    plt.savefig(buf1, format='png', bbox_inches='tight')
    buf1.seek(0)
    priority_chart = base64.b64encode(buf1.getvalue()).decode('utf-8')
    plt.close()
    
    # ===== 2. Динамика выполнения по дням (последние 7 дней) =====
    today = datetime.utcnow().date()
    daily_completed = defaultdict(int)
    
    for task in tasks:
        if task.status == 'completed' and task.updated_at:
            completed_date = task.updated_at.date()
            days_ago = (today - completed_date).days
            if 0 <= days_ago <= 6:
                daily_completed[completed_date] += 1
    
    # Сортируем по дате
    dates = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    completed_counts = [daily_completed[date] for date in dates]
    date_labels = [d.strftime('%d.%m') for d in dates]
    
    fig2, ax2 = plt.subplots(figsize=(8, 4))
    bars = ax2.bar(date_labels, completed_counts, color='#198754')
    ax2.set_xlabel('Дата')
    ax2.set_ylabel('Выполнено задач')
    ax2.set_title('Динамика выполнения задач за последние 7 дней')
    ax2.set_xticks(range(len(date_labels)))
    ax2.set_xticklabels(date_labels, rotation=45)
    
    # Добавляем значения на столбцы
    for bar, count in zip(bars, completed_counts):
        if count > 0:
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                    str(count), ha='center', va='bottom')
    
    buf2 = BytesIO()
    plt.savefig(buf2, format='png', bbox_inches='tight')
    buf2.seek(0)
    daily_chart = base64.b64encode(buf2.getvalue()).decode('utf-8')
    plt.close()
    
    # ===== 3. Распределение по категориям =====
    category_counts = defaultdict(int)
    for task in tasks:
        if task.category:
            category_counts[task.category.name] += 1
        else:
            category_counts['Без категории'] += 1
    
    # Топ-5 категорий
    top_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    fig3, ax3 = plt.subplots(figsize=(6, 4))
    if top_categories:
        cat_labels = [c[0] for c in top_categories]
        cat_sizes = [c[1] for c in top_categories]
        ax3.barh(cat_labels, cat_sizes, color='#0d6efd')
        ax3.set_xlabel('Количество задач')
        ax3.set_title('Топ-5 категорий по количеству задач')
    else:
        ax3.text(0.5, 0.5, 'Нет данных', ha='center', va='center')
        ax3.axis('off')
    
    buf3 = BytesIO()
    plt.savefig(buf3, format='png', bbox_inches='tight')
    buf3.seek(0)
    category_chart = base64.b64encode(buf3.getvalue()).decode('utf-8')
    plt.close()
    
    # ===== 4. Самая продуктивная неделя =====
    weekly_stats = defaultdict(int)
    for task in tasks:
        if task.status == 'completed' and task.updated_at:
            week_num = task.updated_at.isocalendar()[1]
            year = task.updated_at.year
            weekly_stats[(year, week_num)] += 1
    
    if weekly_stats:
        best_week = max(weekly_stats, key=weekly_stats.get)
        best_week_count = weekly_stats[best_week]
        best_week_str = f"{best_week[0]}, неделя {best_week[1]}"
    else:
        best_week_str = "Нет данных"
        best_week_count = 0
    
    return render_template('dashboard.html',
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completion_rate=completion_rate,
                         priority_chart=priority_chart,
                         daily_chart=daily_chart,
                         category_chart=category_chart,
                         best_week_str=best_week_str,
                         best_week_count=best_week_count)



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
    
    categories = Category.query.filter_by(user_id=current_user.id).all()
    form.category_id.choices = [(0, 'Без категории')] + [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        # Если дедлайн не указан, ставим None
        deadline = form.deadline.data if form.deadline.data else None
        
        task = Task(
            title=form.title.data,
            description=form.description.data,
            status=form.status.data,
            priority=form.priority.data,
            deadline=deadline,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            user_id=current_user.id
        )
        db.session.add(task)
        db.session.commit()
        
        # Создаем правило повторения, если задача повторяющаяся
        if form.is_recurring.data:

            print("=== ДИАГНОСТИКА ===")
            print("recurrence_interval.data:", form.recurrence_interval.data)
            print("recurrence_frequency.data:", form.recurrence_frequency.data)
            print("deadline:", deadline)
            # Для повторяющейся задачи без дедлайна используем текущую дату как стартовую
            start_date = deadline if deadline else datetime.utcnow()
            interval = form.recurrence_interval.data if form.recurrence_interval.data else 1
            
            rule = RecurringRule(
                frequency=form.recurrence_frequency.data,
                interval=interval,
                end_date=form.recurrence_end_date.data if form.recurrence_end_date.data else None,
                next_date=calculate_next_date(start_date, form.recurrence_frequency.data, interval),
                is_active=True,
                task_id=task.id
            )
            db.session.add(rule)
            db.session.commit()
        
        flash('Задача успешно создана!', 'success')
        return redirect(url_for('tasks'))
    
    return render_template('task_form.html', form=form, title='Создать задачу')

def calculate_next_date(current_date, frequency, interval):
    """Рассчитывает следующую дату для повторяющейся задачи"""
    if not current_date:
        return None
    
    if frequency == 'daily':
        return current_date + timedelta(days=interval)
    elif frequency == 'weekly':
        return current_date + timedelta(weeks=interval)
    elif frequency == 'monthly':
        # Простое добавление месяцев (упрощённо)
        next_month = current_date.month + interval
        next_year = current_date.year + (next_month - 1) // 12
        next_month = ((next_month - 1) % 12) + 1
        try:
            return current_date.replace(year=next_year, month=next_month)
        except ValueError:
            return current_date.replace(year=next_year, month=next_month, day=28)
    return None

@app.route('/task/<int:task_id>/complete-and-renew', methods=['POST'])
@login_required
def task_complete_and_renew(task_id):
    """Отметить задачу выполненной и создать следующую по правилу повторения"""
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Нет доступа', 'danger')
        return redirect(url_for('tasks'))
    
    if task.status == 'completed':
        flash('Задача уже выполнена', 'info')
        return redirect(url_for('tasks'))
    
    # Отмечаем текущую задачу выполненной
    task.status = 'completed'
    task.updated_at = datetime.utcnow()
    db.session.commit()
    
    # Если есть правило повторения и оно активно
    if task.recurring_rule and task.recurring_rule.is_active:
        rule = task.recurring_rule
        
        # Проверяем, не достигнута ли дата окончания
        if rule.end_date and rule.end_date <= datetime.utcnow():
            rule.is_active = False
            db.session.commit()
            flash('Задача выполнена! (Повторение завершено по достижении даты окончания)', 'success')
            return redirect(url_for('tasks'))
        
        # Создаём новую задачу
        new_task = Task(
            title=task.title,
            description=task.description,
            status='pending',
            priority=task.priority,
            deadline=rule.next_date,
            category_id=task.category_id,
            user_id=current_user.id
        )
        db.session.add(new_task)
        db.session.commit()
        
        # Обновляем правило для новой задачи
        new_rule = RecurringRule(
            frequency=rule.frequency,
            interval=rule.interval,
            end_date=rule.end_date,
            next_date=calculate_next_date(rule.next_date, rule.frequency, rule.interval),
            is_active=True,
            task_id=new_task.id
        )
        db.session.add(new_rule)
        
        # Деактивируем старое правило
        rule.is_active = False
        db.session.commit()
        
        flash(f'Задача выполнена! Создана следующая задача на {new_task.deadline.strftime("%d.%m.%Y")}', 'success')
    
    return redirect(url_for('tasks'))


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
    
    if task.user_id != current_user.id:
        flash('У вас нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    form = TaskForm(obj=task)
    
    categories = Category.query.filter_by(user_id=current_user.id).all()
    form.category_id.choices = [(0, 'Без категории')] + [(c.id, c.name) for c in categories]
    
    # Заполняем поля повторения, если они есть
    if task.recurring_rule:
        form.is_recurring.data = True
        form.recurrence_frequency.data = task.recurring_rule.frequency
        form.recurrence_interval.data = task.recurring_rule.interval
        form.recurrence_end_date.data = task.recurring_rule.end_date
    
    if form.validate_on_submit():
        # Если дедлайн не указан, ставим None
        deadline = form.deadline.data if form.deadline.data else None
        
        task.title = form.title.data
        task.description = form.description.data
        task.status = form.status.data
        task.priority = form.priority.data
        task.deadline = deadline
        task.category_id = form.category_id.data if form.category_id.data != 0 else None
        task.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Обновляем правило повторения
        if form.is_recurring.data:
            start_date = deadline if deadline else datetime.utcnow()
            if task.recurring_rule:
                task.recurring_rule.frequency = form.recurrence_frequency.data
                task.recurring_rule.interval = form.recurrence_interval.data
                task.recurring_rule.end_date = form.recurrence_end_date.data if form.recurrence_end_date.data else None
                task.recurring_rule.next_date = calculate_next_date(start_date, form.recurrence_frequency.data, form.recurrence_interval.data)
            else:
                rule = RecurringRule(
                    frequency=form.recurrence_frequency.data,
                    interval=form.recurrence_interval.data,
                    end_date=form.recurrence_end_date.data if form.recurrence_end_date.data else None,
                    next_date=calculate_next_date(start_date, form.recurrence_frequency.data, form.recurrence_interval.data),
                    is_active=True,
                    task_id=task.id
                )
                db.session.add(rule)
        else:
            if task.recurring_rule:
                db.session.delete(task.recurring_rule)
        
        db.session.commit()
        flash('Задача успешно обновлена!', 'success')
        return redirect(url_for('task_detail', task_id=task.id))
    
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


# ========== Управление подзадачами ==========

@app.route('/subtask/create/<int:task_id>', methods=['POST'])
@login_required
def subtask_create(task_id):
    """Создание новой подзадачи"""
    task = Task.query.get_or_404(task_id)
    
    # Проверяем доступ
    if task.user_id != current_user.id:
        flash('Нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    subtask_title = request.form.get('title', '').strip()
    if subtask_title:
        subtask = Subtask(
            title=subtask_title,
            task_id=task_id
        )
        db.session.add(subtask)
        db.session.commit()
        flash('Подзадача добавлена!', 'success')
    else:
        flash('Название подзадачи не может быть пустым', 'danger')
    
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/subtask/<int:subtask_id>/toggle', methods=['POST'])
@login_required
def subtask_toggle(subtask_id):
    """Переключение статуса подзадачи (выполнена/не выполнена)"""
    subtask = Subtask.query.get_or_404(subtask_id)
    task = subtask.parent_task
    
    # Проверяем доступ через родительскую задачу
    if task.user_id != current_user.id:
        flash('Нет доступа', 'danger')
        return redirect(url_for('tasks'))
    
    # Переключаем статус
    subtask.is_completed = not subtask.is_completed
    db.session.commit()
    
    # Если все подзадачи выполнены, можно автоматически завершить задачу (опционально)
    # if task.progress == 100 and task.status != 'completed':
    #     task.status = 'completed'
    #     db.session.commit()
    #     flash('Все подзадачи выполнены! Задача завершена.', 'success')
    
    return redirect(url_for('task_detail', task_id=task.id))

@app.route('/subtask/<int:subtask_id>/delete', methods=['POST'])
@login_required
def subtask_delete(subtask_id):
    """Удаление подзадачи"""
    subtask = Subtask.query.get_or_404(subtask_id)
    task = subtask.parent_task
    task_id = task.id
    
    # Проверяем доступ
    if task.user_id != current_user.id:
        flash('Нет доступа', 'danger')
        return redirect(url_for('tasks'))
    
    db.session.delete(subtask)
    db.session.commit()
    flash('Подзадача удалена', 'success')
    
    return redirect(url_for('task_detail', task_id=task_id))

# ========== Календарь ==========

@app.route('/calendar')
@login_required
def calendar_view():
    """Календарь с дедлайнами задач"""
    # Получаем месяц и год из параметров URL
    current_year = request.args.get('year', type=int)
    current_month = request.args.get('month', type=int)
    
    now = datetime.utcnow()
    if not current_year:
        current_year = now.year
    if not current_month:
        current_month = now.month
    
    # Первый день месяца
    first_day = date(current_year, current_month, 1)
    
    # Определяем день недели первого дня (0 - понедельник, 6 - воскресенье)
    start_weekday = first_day.weekday()
    
    # Количество дней в месяце
    if current_month == 12:
        next_month = date(current_year + 1, 1, 1)
    else:
        next_month = date(current_year, current_month + 1, 1)
    days_in_month = (next_month - first_day).days
    
    # Собираем все дни месяца в список
    calendar_days = []
    for i in range(1, days_in_month + 1):
        calendar_days.append(date(current_year, current_month, i))
    
    # Получаем задачи пользователя с дедлайнами
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    
    # Группируем задачи по дате дедлайна
    tasks_by_date = {}
    for task in tasks:
        if task.deadline:
            task_date = task.deadline.date()
            if task_date not in tasks_by_date:
                tasks_by_date[task_date] = []
            tasks_by_date[task_date].append(task)
    
    # Создаем календарную сетку (6 недель по 7 дней)
    calendar_grid = []
    week = []
    
    # Добавляем пустые дни перед первым днем месяца
    for i in range(start_weekday):
        week.append(None)
    
    # Добавляем дни месяца
    for day in calendar_days:
        day_info = {
            'date': day,
            'day': day.day,
            'tasks': tasks_by_date.get(day, []),
            'is_today': day == now.date()
        }
        week.append(day_info)
        
        if len(week) == 7:
            calendar_grid.append(week)
            week = []
    
    # Добавляем пустые дни в конец последней недели
    if week:
        while len(week) < 7:
            week.append(None)
        calendar_grid.append(week)
    
    # Названия дней недели
    weekdays = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС']
    
    # Названия месяцев на русском
    month_names = {
        1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель',
        5: 'Май', 6: 'Июнь', 7: 'Июль', 8: 'Август',
        9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
    }
    
    # Навигация по месяцам
    prev_month = current_month - 1
    prev_year = current_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    
    next_month = current_month + 1
    next_year = current_year
    if next_month == 13:
        next_month = 1
        next_year += 1
    
    return render_template('calendar.html',
                         calendar_grid=calendar_grid,
                         weekdays=weekdays,
                         month_name=month_names[current_month],
                         year=current_year,
                         current_month=current_month,
                         current_year=current_year,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year)


# ========== Личный кабинет ==========

@app.route('/profile')
@login_required
def profile():
    """Личный кабинет пользователя"""
    return render_template('profile.html', user=current_user)

@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    """Смена пароля"""
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    # Проверяем текущий пароль
    if not check_password_hash(current_user.password_hash, current_password):
        flash('Текущий пароль введен неверно', 'danger')
        return redirect(url_for('profile'))
    
    # Проверяем длину нового пароля
    if len(new_password) < 6:
        flash('Новый пароль должен содержать минимум 6 символов', 'danger')
        return redirect(url_for('profile'))
    
    # Проверяем совпадение паролей
    if new_password != confirm_password:
        flash('Пароли не совпадают', 'danger')
        return redirect(url_for('profile'))
    
    # Меняем пароль
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    flash('Пароль успешно изменен!', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/settings', methods=['POST'])
@login_required
def profile_settings():
    """Обновление настроек профиля"""
    timezone = request.form.get('timezone', 'Europe/Moscow')
    current_user.timezone = timezone
    db.session.commit()
    
    flash('Настройки сохранены!', 'success')
    return redirect(url_for('profile'))

# ========== Управление вложениями ==========

@app.route('/task/<int:task_id>/attachment/upload', methods=['POST'])
@login_required
def upload_attachment(task_id):
    """Загрузка файла-вложения к задаче"""
    task = Task.query.get_or_404(task_id)
    
    if task.user_id != current_user.id:
        flash('Нет доступа к этой задаче', 'danger')
        return redirect(url_for('tasks'))
    
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('task_detail', task_id=task.id))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('task_detail', task_id=task.id))
    
    if file:
        # Сохраняем файл
        filename = secure_filename(file.filename)
        # Добавляем временную метку к имени файла, чтобы избежать дублирования
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2:
            filename = f"{name_parts[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{name_parts[1]}"
        else:
            filename = f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Создаём папку пользователя
        user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
        os.makedirs(user_folder, exist_ok=True)
        
        filepath = os.path.join(user_folder, filename)
        file.save(filepath)
        
        # Сохраняем запись в БД
        attachment = Attachment(
            filename=file.filename,  # Оригинальное имя
            filepath=filepath,
            task_id=task.id
        )
        db.session.add(attachment)
        db.session.commit()
        
        flash(f'Файл "{file.filename}" загружен!', 'success')
    
    return redirect(url_for('task_detail', task_id=task.id))

@app.route('/attachment/<int:attachment_id>/delete', methods=['POST'])
@login_required
def delete_attachment(attachment_id):
    """Удаление вложения"""
    attachment = Attachment.query.get_or_404(attachment_id)
    task = attachment.task
    
    if task.user_id != current_user.id:
        flash('Нет доступа', 'danger')
        return redirect(url_for('tasks'))
    
    # Удаляем файл с диска
    if os.path.exists(attachment.filepath):
        os.remove(attachment.filepath)
    
    db.session.delete(attachment)
    db.session.commit()
    
    flash('Вложение удалено', 'success')
    return redirect(url_for('task_detail', task_id=task.id))

@app.route('/attachment/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    """Скачивание вложения"""
    from flask import send_file
    
    attachment = Attachment.query.get_or_404(attachment_id)
    task = attachment.task
    
    if task.user_id != current_user.id:
        flash('Нет доступа', 'danger')
        return redirect(url_for('tasks'))
    
    if os.path.exists(attachment.filepath):
        return send_file(attachment.filepath, as_attachment=True, download_name=attachment.filename)
    else:
        flash('Файл не найден на сервере', 'danger')
        return redirect(url_for('task_detail', task_id=task.id))
    
# ========== Административная панель ==========

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    """Главная страница админ-панели"""
    users = User.query.all()
    tasks = Task.query.all()
    categories = Category.query.all()
    attachments = Attachment.query.all()
    
    return render_template('admin/index.html',
                         users=users,
                         tasks=tasks,
                         categories=categories,
                         attachments=attachments)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Управление пользователями"""
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>/toggle-role', methods=['POST'])
@login_required
@admin_required
def admin_toggle_role(user_id):
    """Назначить/снять роль администратора"""
    user = User.query.get_or_404(user_id)
    
    # Нельзя изменить роль самому себе
    if user.id == current_user.id:
        flash('Нельзя изменить роль самого себя', 'danger')
        return redirect(url_for('admin_users'))
    
    if user.role == 'admin':
        user.role = 'user'
        flash(f'Пользователь "{user.username}" лишён прав администратора', 'warning')
    else:
        user.role = 'admin'
        flash(f'Пользователь "{user.username}" назначен администратором', 'success')
    
    db.session.commit()
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Удаление пользователя (со всеми его задачами)"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Нельзя удалить самого себя', 'danger')
        return redirect(url_for('admin_users'))
    
    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь "{user.username}" удалён', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/tasks')
@login_required
@admin_required
def admin_tasks():
    """Просмотр всех задач системы"""
    tasks = Task.query.all()
    users = User.query.all()
    
    status_filter = request.args.get('status', '')
    user_filter = request.args.get('user', '')
    
    query = Task.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if user_filter and user_filter.isdigit():
        query = query.filter_by(user_id=int(user_filter))
    
    tasks = query.all()
    
    return render_template('admin/tasks.html', 
                         tasks=tasks, 
                         users=users,
                         status_filter=status_filter,
                         user_filter=user_filter)

@app.route('/admin/categories')
@login_required
@admin_required
def admin_categories():
    """Управление справочниками (категории всех пользователей)"""
    categories = Category.query.all()
    users = User.query.all()
    
    user_filter = request.args.get('user', '')
    if user_filter and user_filter.isdigit():
        categories = Category.query.filter_by(user_id=int(user_filter)).all()
    
    return render_template('admin/categories.html', 
                         categories=categories, 
                         users=users,
                         user_filter=user_filter)

@app.route('/admin/attachments')
@login_required
@admin_required
def admin_attachments():
    """Контроль файлов (все вложения системы)"""
    attachments = Attachment.query.all()
    return render_template('admin/attachments.html', attachments=attachments)

@app.route('/admin/attachment/<int:attachment_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_attachment(attachment_id):
    """Удаление вложения (администратор)"""
    attachment = Attachment.query.get_or_404(attachment_id)
    
    if os.path.exists(attachment.filepath):
        os.remove(attachment.filepath)
    
    db.session.delete(attachment)
    db.session.commit()
    flash('Вложение удалено', 'success')
    return redirect(url_for('admin_attachments'))

@app.route('/admin/statistics')
@login_required
@admin_required
def admin_statistics():
    """Общая аналитика по системе"""
    total_users = User.query.count()
    total_tasks = Task.query.count()
    total_categories = Category.query.count()
    total_attachments = Attachment.query.count()
    
    # Задачи по статусам
    pending_tasks = Task.query.filter_by(status='pending').count()
    in_progress_tasks = Task.query.filter_by(status='in_progress').count()
    completed_tasks = Task.query.filter_by(status='completed').count()
    
    # Самый активный пользователь
    from sqlalchemy import func
    most_active = db.session.query(
        User.username, 
        func.count(Task.id).label('task_count')
    ).join(Task, User.id == Task.user_id).group_by(User.id).order_by(func.count(Task.id).desc()).first()
    
    # Пользователи с ролями
    admin_count = User.query.filter_by(role='admin').count()
    user_count = User.query.filter_by(role='user').count()
    
    return render_template('admin/statistics.html',
                         total_users=total_users,
                         total_tasks=total_tasks,
                         total_categories=total_categories,
                         total_attachments=total_attachments,
                         pending_tasks=pending_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completed_tasks=completed_tasks,
                         most_active=most_active,
                         admin_count=admin_count,
                         user_count=user_count)

@app.route('/admin/export')
@login_required
@admin_required
def admin_export():
    """Служебная выгрузка всех данных (JSON)"""
    import json
    
    users_data = []
    for user in User.query.all():
        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'registered_at': user.registered_at.strftime('%Y-%m-%d %H:%M:%S') if user.registered_at else None
        })
    
    tasks_data = []
    for task in Task.query.all():
        tasks_data.append({
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'priority': task.priority,
            'deadline': task.deadline.strftime('%Y-%m-%d %H:%M:%S') if task.deadline else None,
            'user_id': task.user_id
        })
    
    data = {
        'export_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'statistics': {
            'total_users': len(users_data),
            'total_tasks': len(tasks_data)
        },
        'users': users_data,
        'tasks': tasks_data
    }
    
    filename = f'admin_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    return json.dumps(data, ensure_ascii=False, indent=2), 200, {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': f'attachment; filename={filename}'
    }

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  
    app.run(debug=True)