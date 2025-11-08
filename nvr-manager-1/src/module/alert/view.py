from flask import request

from base.app import get_blueprint, make_nvr_manager_response, make_send_file_response
from .exception import (
    AlertImageGettingError,
    AlertImageNotExistsError,
    AlertRecordGettingError,
    AlertRecordNotExistsError
)
from . import service


alert = get_blueprint('alert', __name__)

@alert.route('/collect/<device_id>', methods=['POST'])
def add_alert(device_id: str):
    service.add_alert({**request.json, 'device_id': device_id})
    return make_nvr_manager_response()

@alert.route('')
def get_alert_list():
    return make_nvr_manager_response(service.get_alert_list(request.args))

@alert.route('/count')
def get_alert_count():
    return make_nvr_manager_response(service.get_alert_count(request.args))

@alert.route('/image')
def get_alert_image():
    return make_send_file_response(request.args.get('path'), AlertImageGettingError, AlertImageNotExistsError)

@alert.route('/record')
def get_alert_record():
    return make_send_file_response(request.args.get('path'), AlertRecordGettingError, AlertRecordNotExistsError)
