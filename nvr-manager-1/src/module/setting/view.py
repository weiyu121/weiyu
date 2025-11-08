from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from base import setting as service
from .exception import UpdateSettingError


setting = get_blueprint('setting', __name__)

@setting.route('')
def get_settings():
    return make_nvr_manager_response(service.get_settings())

@setting.route('', methods=['PATCH'])
def update_settings():
    try:
        return make_nvr_manager_response(service.update_settings(request.json))
    except ValueError as e:
        raise UpdateSettingError(str(e))
