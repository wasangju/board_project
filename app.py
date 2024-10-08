from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import html
import os
import time

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sca.db'
app.config['SECRET_KEY'] = 'qwer1234'

basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    file = db.Column(db.String(100)) 
    comments = db.relationship('Comment', backref='post', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class RuleViews(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    views = db.Column(db.Integer, default=0)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    username = session.get('username')
    posts = Post.query.order_by(Post.created_at.desc()).all()
    rule_views = RuleViews.query.first().views
    login_success = session.pop('login_success', False)
    delete_success = session.pop('delete_success', False)
    not_admin = session.pop('not_admin', False)
    return render_template('index.html', posts=posts, rule_views=rule_views, username=username, login_success=login_success, delete_success=delete_success, not_admin=not_admin)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    elif request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            session['username'] = username
            session['login_success'] = True
            return redirect(url_for('index'))
        else:
            flash('아이디 또는 비밀번호가 잘못되었습니다.', 'error')
            return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.clear()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        already = session.pop('already', False)
        return render_template('register.html', already=already)
    elif request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            session['already'] = True
            return redirect(url_for('register'))
        
        new_user = User(username=username, password=password) 
        db.session.add(new_user)
        db.session.commit()
        flash('회원가입이 완료되었습니다. 로그인해주세요.')
        return redirect(url_for('login'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def post(post_id):
    edit_success = session.pop('edit_success', False)
    not_writer = session.pop('not_writer', False)
    cant_delete = session.pop('cant_delete', False)
    guest = session.pop('guest', False)
    comment_added = session.pop('comment_added', False)
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        if 'username' not in session:
            flash('댓글을 작성하려면 로그인이 필요합니다.')
            return redirect(url_for('login'))
        
        content = request.form.get('content')
        if content:
            new_comment = Comment(content=content, author=session['username'], post_id=post_id)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('post', post_id=post_id))
    
    post.views += 1
    db.session.commit()
    return render_template('post.html', post=post, edit_success=edit_success, not_writer=not_writer,cant_delete=cant_delete, guest=guest, comment_added=comment_added)

@app.route('/write', methods=['GET', 'POST'])
def write():
    if 'username' not in session:
        flash('글을 작성하려면 로그인이 필요합니다.')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        content = html.escape(content)
        author = session['username']
        
        file = request.files.get('file')
        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filename = f"{int(time.time())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        post = Post(title=title, content=content, author=author, file=filename)
        db.session.add(post)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('write.html')

@app.route('/delete/<int:post_id>', methods=['GET', 'POST'])
def delete(post_id):
    if 'username' not in session:
        session['guest'] = True
        return redirect(url_for('post', post_id=post_id))
    
    post = Post.query.get_or_404(post_id)

    if session['username'] == 'admin':
        session['cant_writer'] = False
    elif post.author != session['username']:
        session['cant_delete'] = True
        return redirect(url_for('post', post_id=post_id))
    
    Comment.query.filter_by(post_id=post_id).delete()
    
    db.session.delete(post)
    db.session.commit()
    session['delete_success'] = True
    return redirect(url_for('index'))

@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
def edit(post_id):
    
    if 'username' not in session:
        session['guest'] = True
        return redirect(url_for('post', post_id=post_id))
    
    post = Post.query.get_or_404(post_id)

    if session['username'] == 'admin':
        session['not_writer'] = False
    elif post.author != session['username']:
        session['not_writer'] = True
        return redirect(url_for('post', post_id=post_id))
    
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.content = html.escape(request.form['content']) # xss 방지

        if 'delete_file' in request.form:
            if post.file:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.file)
                if os.path.exists(file_path):
                    os.remove(file_path)
            post.file = None

        file = request.files.get('file')
        if file and allowed_file(file.filename):
            if post.file:
                old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], post.file)
                if os.path.exists(old_file_path):
                    os.remove(old_file_path)
            
            filename = secure_filename(file.filename)
            filename = f"{int(time.time())}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post.file = filename

        db.session.commit()
        session['edit_success'] = True
        return redirect(url_for('post', post_id=post.id))
    return render_template('edit.html', post=post)

@app.route('/rule')
def rule():
    rule_views = RuleViews.query.first()
    if not rule_views:
        rule_views = RuleViews(views=1)
        db.session.add(rule_views)
    else:
        rule_views.views += 1
    db.session.commit()
    return render_template('rule.html', view=rule_views.views)

@app.route('/admin')
def admin():
    if request.method == 'POST':
        session['not_admin'] = True
        return render_template('index.html')
    elif request.method == 'GET':
        return render_template('admin.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.first():
            admin = User(username='admin', password='qwer1234')
            guest = User(username='guest', password='guest')
            wasangju = User(username='wasangju', password='youknow')    
            db.session.add_all([admin, guest, wasangju])
            db.session.commit()
        if not RuleViews.query.first():
            initial_rule_views = RuleViews(views=0)
            db.session.add(initial_rule_views)
            db.session.commit()
    app.run(host='0.0.0.0', port=5001, debug=True)
