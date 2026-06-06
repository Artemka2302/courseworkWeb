from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, DateTimeField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from datetime import datetime

class RegistrationForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')

class TaskForm(FlaskForm):
    title = StringField('Название задачи', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Описание')
    status = SelectField('Статус', choices=[
        ('pending', 'Ожидает'),
        ('in_progress', 'В работе'),
        ('completed', 'Выполнена')
    ])
    priority = SelectField('Приоритет', choices=[
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий')
    ])
    deadline = DateTimeField('Дедлайн (ГГГГ-ММ-ДД ЧЧ:ММ)', format='%Y-%m-%d %H:%M')
    submit = SubmitField('Сохранить')

class CategoryForm(FlaskForm):
    name = StringField('Название категории', validators=[DataRequired(), Length(max=50)])
    color = SelectField('Цвет', choices=[
        ('#6c757d', 'Серый'),
        ('#0d6efd', 'Синий'),
        ('#198754', 'Зеленый'),
        ('#dc3545', 'Красный'),
        ('#fd7e14', 'Оранжевый'),
        ('#6f42c1', 'Фиолетовый'),
        ('#d63384', 'Розовый'),
        ('#20c997', 'Бирюзовый'),
        ('#ffc107', 'Желтый'),
    ], default='#6c757d')
    submit = SubmitField('Сохранить')

class TaskForm(FlaskForm):
    title = StringField('Название задачи', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Описание')
    status = SelectField('Статус', choices=[
        ('pending', 'Ожидает'),
        ('in_progress', 'В работе'),
        ('completed', 'Выполнена')
    ])
    priority = SelectField('Приоритет', choices=[
        ('low', 'Низкий'),
        ('medium', 'Средний'),
        ('high', 'Высокий')
    ])
    deadline = DateTimeField('Дедлайн (ГГГГ-ММ-ДД ЧЧ:ММ)', format='%Y-%m-%d %H:%M', validators=[DataRequired()])
    category_id = SelectField('Категория', coerce=int, choices=[], default=0)  # Добавить это поле
    submit = SubmitField('Сохранить')