from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from enum import Enum

db = SQLAlchemy()

# Вспомогательная таблица для связи многие-ко-многим (Task <-> Tag)
task_tags = db.Table('task_tags',
    db.Column('task_id', db.Integer, db.ForeignKey('task.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    timezone = db.Column(db.String(50), default='Europe/Moscow')
    role = db.Column(db.String(20), default='user')  # 'user' или 'admin'
    
    # Связи
    tasks = db.relationship('Task', backref='author', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='user', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<User {self.username}>'

class Category(db.Model):
    __tablename__ = 'category'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(7), default='#6c757d')  # HEX цвет
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    tasks = db.relationship('Task', backref='category', lazy=True)
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Tag(db.Model):
    __tablename__ = 'tag'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def __repr__(self):
        return f'<Tag {self.name}>'

class Task(db.Model):
    __tablename__ = 'task'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    priority = db.Column(db.String(20), default='medium')  # low, medium, high
    deadline = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Внешние ключи
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)
    
    # Связи
    subtasks = db.relationship('Subtask', backref='parent_task', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=task_tags, backref='tasks', lazy='dynamic')
    attachments = db.relationship('Attachment', backref='task', lazy=True, cascade='all, delete-orphan')
    recurring_rule = db.relationship('RecurringRule', backref='task', uselist=False, cascade='all, delete-orphan')
    
    @property
    def progress(self):
        """Расчет процента выполнения на основе подзадач"""
        if not self.subtasks:
            return 100 if self.status == 'completed' else 0
        completed = sum(1 for st in self.subtasks if st.is_completed)
        return int((completed / len(self.subtasks)) * 100)
    
    @property
    def is_overdue(self):
        """Проверка просрочена ли задача"""
        if self.status == 'completed':
            return False
        if self.deadline and self.deadline < datetime.utcnow():
            return True
        return False
    
    def __repr__(self):
        return f'<Task {self.title}>'

class Subtask(db.Model):
    __tablename__ = 'subtask'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    
    def __repr__(self):
        return f'<Subtask {self.title}>'

class Attachment(db.Model):
    __tablename__ = 'attachment'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    
    def __repr__(self):
        return f'<Attachment {self.filename}>'

class RecurringRule(db.Model):
    __tablename__ = 'recurring_rule'
    
    id = db.Column(db.Integer, primary_key=True)
    frequency = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly
    interval = db.Column(db.Integer, default=1)  # каждые N дней/недель/месяцев
    end_date = db.Column(db.DateTime, nullable=True)
    next_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False, unique=True)
    
    def __repr__(self):
        return f'<RecurringRule {self.frequency} every {self.interval}>'