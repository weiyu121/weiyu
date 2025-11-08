from flask import session, request

from base.app import get_blueprint, make_nvr_manager_response, app
from .exception import (
    UserNotLogin,
    UserAlreadyLogin
)
from . import service


auth = get_blueprint('auth', __name__)

@auth.route('/password', methods=['PATCH'])
def set_password():
    service.set_passwrod(request.json)
    return make_nvr_manager_response()

@auth.route('/password')
def get_password():
    return make_nvr_manager_response({'password': service.get_password()})

@auth.route('/question', methods=['POST'])
def add_question():
    return make_nvr_manager_response({'id': service.add_question(request.json)})

@auth.route('/question')
def get_questions():
    return make_nvr_manager_response(service.get_questions())

@auth.route('/question/<int:id>')
def get_question(id: int):
    return make_nvr_manager_response(service.get_question(id))

@auth.route('/question/<int:id>', methods=['DELETE'])
def delete_question(id: int):
    service.delete_question(id)
    return make_nvr_manager_response()

@auth.route('/login', methods=['POST'])
def login():
    if 'logined' not in session:
        service.login(request.json)
        session['logined'] = True
        session.permanent = True
        return make_nvr_manager_response()
    else:
        raise UserAlreadyLogin('已登录')

@auth.route('/logout', methods=['POST'])
def logout():
    session.pop('logined', None)
    return make_nvr_manager_response()

@app.before_request
def auth_login():
    if session.get('logined') \
        or request.path.startswith('/auth') \
        or request.path == '/' \
        or not request.user_agent.string.lower().startswith('mozilla') \
        or request.method == 'GET' and request.path.startswith('/setting'):  # FIX: 为了让登录页面的字也更改，放行这个接口
        return None
    auth = request.args.get('auth')
    if auth:
        service.login({'password': auth})
        return None
    return make_nvr_manager_response(error=UserNotLogin('用户未登录，访问禁止'))
