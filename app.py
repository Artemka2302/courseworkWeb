from flask import Flask, render_template

# Создаем экземпляр приложения Flask
app = Flask(__name__)

# Декоратор route связывает URL с функцией ниже
@app.route('/')
def index():
    # Данные, которые мы хотим передать в шаблон
    page_title = "Мой первый проект на Flask и Jinja2"
    items = ["Flask", "Jinja2", "Python", "HTML"]
    
    # Функция render_template:
    # 1. Ищет файл 'index.html' в папке 'templates'
    # 2. Передает переменные title и items в шаблон
    return render_template('index.html', title=page_title, items=items)

# Запуск приложения, если файл выполняется напрямую
if __name__ == '__main__':
    # debug=True автоматически перезагружает сервер при изменениях в коде
    app.run(debug=True)