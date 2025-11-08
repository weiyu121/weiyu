import os
import mimetypes
from flask import Flask, make_response, Blueprint, send_file
from flask_cors import CORS

from base.exception import NVRManagerError
from config import FlaskConfig
    

app = Flask('NVR-Manager')
app.config.from_object(FlaskConfig)
CORS(app)

_blueprints = {}

def make_nvr_manager_response(data: dict=None, error: NVRManagerError=None, http_code: int=200):
    resp = {'code': error.code, 'message': error.msg} if error else {'code': 0, 'message': None}
    if data:
        resp.update(data)
    return make_response(resp, http_code)

def make_send_file_response(file_path: str, getting_error_cls: NVRManagerError, not_exists_error_cls: NVRManagerError):
    try:
        if not file_path:
            raise getting_error_cls(f'请传入文件的路径')
        if not os.path.exists(file_path):
            raise not_exists_error_cls(f'文件{file_path}不在服务器中')
        guess_mime = mimetypes.guess_type(file_path)
        if not guess_mime:
            raise getting_error_cls(f'无法将文件{file_path}根据拓展名转换为MimeType')
        return send_file(file_path, guess_mime[0])
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e, http_code=404)

# 注意，蓝图制定了前缀里有一个'/'，所以蓝图的子路径前缀应该为空字符串，而非'/'
def get_blueprint(name, imort_name, **kwarge):
    bp = _blueprints.get(name)
    if not bp:
        bp = Blueprint(name, imort_name, url_prefix=f'/{name}', **kwarge)
        _blueprints[name] = bp
    return bp

def register_all_blueprints():
    for bp in _blueprints.values():
        app.register_blueprint(bp)
