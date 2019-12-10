from flask import render_template, redirect, url_for, flash, jsonify
from flask.json import jsonify
from flask import request
from . import main
import re
from app import db
import time
from flask_login import login_required, current_user, login_user, logout_user
from .forms import Login_form, Register_user_form
from ..model import User, Role, Book_basic, Book, Borrow_log, Return_log
import random
from ..decorators import online_required
from sqlalchemy import or_
import operator
from functools import reduce


def flatten(l):
    for el in l:
        if hasattr(el, "__iter__") or isinstance(el, list):
            for sub in flatten(el):
                yield sub
        else:
            yield el





@main.route('/login', methods=['GET', 'POST'])
def login():
    form = Login_form()
    if form.validate_on_submit():
        temp = User.query.filter_by(user_id=form.login_user_id.data).first()
        if temp:
            if temp.varify(form.login_user_password.data):
                if current_user.is_authenticated:
                    flash('用户已经登陆，请先登出')
                else:
                    login_user(temp)
                    flash('成功登陆')
                    return redirect(url_for('main.index'))
            else:
                flash('账户密码错误')
        else:
            flash('账户不存在')
    return render_template('login.html', form=form)


@main.route('/logout')
@login_required
@online_required
def logout():
    logout_user()
    flash('您已经成功登出')
    return redirect(url_for('main.index'))



# 处理分词之后的模糊搜索
def fuzzy_search(keyword):
    answers = []
    if not keyword:
        return None
    for word in keyword:
        print('ffff', word)
        if word[1] == 'isbn':
            temp = Book_basic.query.filter_by(book_basic_isbn=word[0]).first()
            print('isbn', temp)
            if temp:
                answers.append(temp)
        elif word[1] == 'book_id':
            temp = Book.query.filter_by(book_id=word[0]).first()
            if temp:
                answers.append(temp)
        elif word[1] == 'book_name_or_author':
            fuzzy_word = '%' + word[0] + '%'
            fuzzy_rule = or_(*[Book_basic.book_basic_name.like(fuzzy_word), Book_basic.book_basic_author.like(fuzzy_word)])
            temp = Book_basic.query.filter(fuzzy_rule).all()
            if temp:
                temp = [x for x in flatten(temp)]
                for x in temp:
                    answers.append(x)
    print('answers', answers)
    if answers:
        temp = []
        x = []
        for i, ans in enumerate(answers):
            if (i+1) % 3 == 0:
                temp.append(ans)
                x.append(temp)
                temp = []
            else:
                temp.append(ans)
        if temp:
            x.append(temp)
        return x
    return None

@main.route('/', methods=['GET', 'POST'])
def index():
        # return redirect(url_for('main.login'))
    keyword = request.form.get('keyword')
    if keyword:
        regex = '\\s+'
        keyword = re.split(regex, keyword)
        search = []
        # 筛选出字母、字母数字混合，删除，isbn的标记
        print(keyword)
        for word in keyword:
            if word == '':
                continue
            if word.encode('utf-8').isalpha():
                search.append((word, 'book_name_or_author'))
            elif re.search('^[0-9]{13}$', word):
                search.append((word, 'isbn'))
            elif re.search('^[0-9]{16}$', word):
                search.append((word, 'book_id'))
            else:
                search.append((word, 'book_name_or_author'))
        print(search)
        show = fuzzy_search(search)
        print('here', show)
        if not show: # 无任何搜索结果
            flash('数据库暂无您所需要的书籍，请试试其他关键词吧！')
            time.sleep(1)
            return redirect(url_for('main.index'))
    else:
        books_num = Book_basic.query.count()
        books_choices = [i+1 for i in range(books_num-5)]
        seed = int(time.clock())
        random.seed(seed)
        show = []
        for i in range(3):
            choice = random.sample(books_choices, 3)
            temp = []
            for j in choice:
                x = Book_basic.query.limit(1).offset(j).first()
                temp.append(x)
            show.append(temp)
    return render_template('index.html', row=show)


@main.route('/help_borrow_book', methods=['POST'])
@online_required
def help_borrow_book():
    # 先查询用户有没有达到借阅上限
    # 再检查书籍有没有余量
    # 执行借书操作，随机分配1个可用书籍id号，书籍余量-1，用户可借阅剩余数量-1，插入借阅记录
    message_info = ''
    book_basic_isbn = request.form['book_basic_isbn']
    user_id = current_user.user_id
    user = User.query.filter_by(user_id=user_id).first()
    book_basic = Book_basic.query.filter_by(book_basic_isbn=book_basic_isbn).first()
    book_basic_status = book_basic.get_book_basic_status()
    flag = 0
    if not current_user.is_authenticated:
        message_info = '借书请先登陆！'
        return jsonify(book_basic_remain_num=book_basic_status[1]-flag, message_info=message_info)
    if user.user_remain_book_num < 1:
        message_info = f'借阅失败，已经达到借阅书籍上限 {user.user_role.role_book_limit} 本'
    else:
        if book_basic_status[1] < 1:
            message_info = f'借阅失败，该书 {book_basic.book_basic_name} 目前没有余量'
        else:
            flag = 1
            book = Book.query.filter_by(book_isbn=book_basic_isbn, book_borrowed=False).first()
            book.borrow_this_book(user_id=user_id)
            message_info = f'学号为 {user.user_id} 的用户成功借阅书籍id为 {book.book_id} 的 {book_basic.book_basic_name} 图书'
    return jsonify(book_basic_remain_num=book_basic_status[1]-flag, message_info=message_info)



@main.route('/register', methods=['GET', 'POST'])
def register():
    form = Register_user_form()
    if form.validate_on_submit():
        if User.query.filter_by(user_id=form.register_user_id.data).first():
            flash('该学号已经注册')
        else:
            new_user = User(form.register_user_id.data, form.register_user_name.data, form.register_user_password.data)
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功，请登录')
            return redirect(url_for('main.login'))
    return render_template('register.html', form=form)


@main.route('/profile', methods=['GET', 'POST'])
@online_required
def profile():
    x = request.form.get('user_id')
    current_user1 = current_user._get_current_object()
    if x:
        regex = '^[0-9]{6}$'
        if re.findall(regex, x) and re.findall(regex, x)[0] == x:
            user = User.query.filter_by(user_id=x).first()
            if user:
                current_user1 = user
            else:
                flash('该用户不存在')
                return redirect(url_for('main.index'))
        else:
            flash('请输入正确格式的用户id，6位数字组成')
            return redirect(url_for('main.index'))
    user_info = [
        ('用户学号', current_user1.user_id),
        ('用户姓名', current_user1.user_name),
        ('用户等级', current_user1.user_role_name),
        ('用户借阅上限', current_user1.user_role.role_book_limit),
        ('用户可借数量', current_user1.user_remain_book_num)
    ]
    user_id = current_user1.user_id
    info = []
    info_label = ['序号', '借阅人姓名', '借阅人学号', '借阅书籍名称', '借阅书籍id', '借阅或归还时间', '状态']
    borrow = Borrow_log.query.filter_by(borrow_user_id=user_id).all()
    i = 0
    for i, one in enumerate(borrow):
        temp = [
            i + 1, current_user1.user_name, user_id,
            one.borrow_book.book_basic.book_basic_name,
            one.borrow_book_id, one.borrow_time,
            '未归还'
        ]
        info.append(temp)
    returned = Return_log.query.filter_by(return_user_id=user_id).limit(10).offset(0)
    for j, one in enumerate(returned):
        temp = [
            i + j + 2,
            current_user1.user_name, user_id,
            one.return_book.book_basic.book_basic_name,
            one.return_book_id, one.return_time,
            '已归还'
        ]
        info.append(temp)

    return render_template('profile.html', user_info=user_info, info_label=info_label, info=info)