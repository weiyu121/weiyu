from flask import request
from base.app import get_blueprint, make_nvr_manager_response

from . import service


iot_485 = get_blueprint('iot/485', __name__)

@iot_485.route('/driver/start', methods=['POST'])
def enable_driver():
    return make_nvr_manager_response(service.enable_driver())

@iot_485.route('/driver/stop', methods=['POST'])
def stop_driver():
    return make_nvr_manager_response(service.stop_driver())

@iot_485.route('/driver')
def get_driver():
    return make_nvr_manager_response(service.get_driver())

@iot_485.route('/driver', methods=['PATCH'])
def set_driver():
    return make_nvr_manager_response(service.set_driver(request.json))

@iot_485.route('/data')
def get_json_data():
    return make_nvr_manager_response({'data': service.get_json_data()})
