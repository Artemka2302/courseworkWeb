from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from werkzeug.utils import secure_filename
import os
import matplotlib
matplotlib.use('Agg')  # Используем backend без GUI
import matplotlib.pyplot as plt
from io import BytesIO
import base64
from datetime import datetime, timedelta
from collections import defaultdict

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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Создаем таблицы при первом запуске
    app.run(debug=True)