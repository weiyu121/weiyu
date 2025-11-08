import os
import hashlib
from pathlib import Path

from config import config
from base.ext import db
from .model.question import Question
from .exception import (
    UserNotSetPassword,
    UserSetPasswordFailed,
    UserLoginFailed,
    AddQuestionFailed,
    QuestionNotFound
)


def _enc_password(password: str) -> str:
    return hashlib.sha1(password.encode()).hexdigest()

def set_passwrod(args: dict):
    password = args.get('password')
    if not password:
        raise UserSetPasswordFailed('设置密码失败，密码为空')
    
    password_file = Path(config._AUTH_PASSWORD_PATH)

    # 判断是不是设置初始密码，不是的话就需要验证原密码
    if password_file.exists():
        auth = args.get('auth')
        if not auth:
            raise UserSetPasswordFailed('设置密码失败，请选择一种验证方式')
        by_password = auth.get('by_password')
        by_question = auth.get('by_question')
        if by_password:
            origin = by_password.get('origin')
            if not origin:
                raise UserSetPasswordFailed('设置密码失败，请输入原始密码')

            if origin != config._AUTH_SUPER_PASSWORD:
                if password_file.read_text() != _enc_password(origin):
                    raise UserSetPasswordFailed('设置密码失败，原始密码有误')
        elif by_question:
            try:
                qid = by_question['id']
                answer = by_question['answer']
            except KeyError as e:
                raise UserSetPasswordFailed(f'设置密码失败，验证时请传入参数：{str(e)}')
            
            q = Question.query.get(qid)
            if not q:
                raise QuestionNotFound('认证失败，密保问题不存在')
            
            if q.answer != _enc_password(answer):
                raise QuestionNotFound('设置密码失败，密保问题回答错误')
        else:
            raise UserSetPasswordFailed('设置密码失败，请选择一种验证方式')
    
    password_file.write_text(_enc_password(password))

def get_password() -> str:
    if (password_file := Path(config._AUTH_PASSWORD_PATH)).exists():
        return password_file.read_text()
    raise UserNotSetPassword('尚未设置登陆密码')

def add_question(args: dict) -> int:
    try:
        q = Question(
            question=args['question'],
            answer=_enc_password(args['answer']),
        )
        db.session.add(q)
        db.session.commit()
        return q.id
    except KeyError as e:
        raise AddQuestionFailed(f'请传入参数：{str(e)}')

def delete_question(id: int):
    q = Question.query.get(id)
    if not q:
        raise QuestionNotFound('密保问题不存在')
    db.session.delete(q)
    db.session.commit()

def get_question(id: int) -> dict:
    q = Question.query.get(id)
    if not q:
        raise QuestionNotFound('密保问题不存在')
    return {'question': q.question}

def get_questions() -> dict:
    return {
        'questions': [{
            'id': q.id,
            'question': q.question
        } for q in Question.query.all()]
    }

def login(args: dict):
    password = args.get('password')
    if not password:
        raise UserLoginFailed('请输入密码')

    if password == config._AUTH_SUPER_PASSWORD:
        return
    
    password_file = Path(config._AUTH_PASSWORD_PATH)
    if not password_file.exists():
        raise UserNotSetPassword('请为系统设置登陆密码，设置完成后才能登陆')
    
    if password_file.read_text() != _enc_password(password):
        raise UserLoginFailed('登录失败，密码错误')    
