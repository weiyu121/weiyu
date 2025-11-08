from flask import send_file

from base.app import get_blueprint, make_nvr_manager_response
from . import service


device = get_blueprint('device', __name__)

@device.route('')
def get_device_list():
    return make_nvr_manager_response(service.get_device_list())

@device.route('/<id>')
def get_device_info(id: str):
    return make_nvr_manager_response(service.get_device_info(id))

@device.route('/<id>/capture')
def get_device_capture(id: str):
    return send_file(service.get_device_capture(id), 'image/jpeg')
