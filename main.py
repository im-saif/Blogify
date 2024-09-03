import smtplib
from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, ForeignKey
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

import config
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

app = Flask(__name__);
app.config['SECRET_KEY'] = config.FLASK_KEY
ckeditor = CKEditor(app)
Bootstrap5(app)
gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = config.DB_URI
db = SQLAlchemy(model_class=Base)
db.init_app(app)


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    email: Mapped[str] = mapped_column(String(250), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(999), nullable=False)
    posts: Mapped[list['BlogPost']] = relationship(back_populates="author")
    comments: Mapped[list['Comment']] = relationship(back_populates='author')


class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped['User'] = relationship(back_populates='posts')
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments: Mapped[list['Comment']] = relationship(back_populates='post')


class Comment(db.Model):
    __tablename__ = "comments"
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped['User'] = relationship(back_populates='comments')
    post_id: Mapped[int] = mapped_column(ForeignKey("blog_posts.id"))
    post: Mapped['BlogPost'] = relationship(back_populates='comments')
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)


with app.app_context():
    db.create_all()


@login_manager.user_loader
def user_loader(user_id):
    return User.query.get(int(user_id))


@app.route('/register', methods=["POST", "GET"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        new_user = User(
            name=form.name.data,
            email=form.email.data,
            password=generate_password_hash(form.password.data, 'pbkdf2:sha256:600000', 8)
        )
        if db.session.execute(db.select(User).where(User.email == new_user.email)).scalar():
            flash("This email already exists! Log in now.", 'error')
            return render_template("register.html", form=form)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html", form=form)


@app.route('/login', methods=["POST", "GET"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('get_all_posts'))
        else:
            flash('Incorrect email or password! try again!', 'error')

    return render_template("login.html", form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts, home=True)


@app.route('/posts/<name>')
def posts_by_user(name):
    user = db.session.execute(db.select(User).where(User.name == name.title())).scalar()
    if user:
        return render_template("index.html", all_posts=user.posts, home=False)
    return abort(404)


@app.route("/post/<int:post_id>", methods=["POST", "GET"])
def show_post(post_id):
    form = CommentForm()
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        new_comment = Comment(text=form.comment.data, author_id=current_user.id, post_id=post_id)
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for('show_post', post_id=post_id))
    return render_template("post.html", post=requested_post, form=form, comments=requested_post.comments)


def admin_only(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and current_user.id == 1:
            return func(*args,**kwargs)
        else:
            return abort(403)
    return wrapper


@app.route("/new-post", methods=["GET", "POST"])
@login_required
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route('/contact', methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template('contact.html', method=request.method)

    name = request.form["name"]
    email = request.form["email"]
    phone = request.form["phone"]
    msg = request.form["message"]

    mail = f"name: {name}\nemail: {email}\nphone: {phone}\nmsg: {msg}"
    connection = smtplib.SMTP("smtp.gmail.com")
    connection.starttls()
    connection.login(user=config.EMAIL, password=config.APP_PASSWORD)
    connection.sendmail(from_addr=config.EMAIL, to_addrs=config.EMAIL, msg=f"Subject:New Message!\n\n{mail}")
    connection.sendmail(from_addr=config.EMAIL, to_addrs=email, msg=f"Subject: Blogify Contact\n\nYour message has been received and sent to the admin. Thanks for contributing!")
    connection.close()

    return render_template('contact.html', method=request.method)


if __name__ == "__main__":
    app.run(debug=False)
