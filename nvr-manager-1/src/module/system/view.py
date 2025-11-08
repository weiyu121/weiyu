from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


system = get_blueprint('system', __name__)

@system.route('/upgrade', methods=["POST"])
def system_upgrade():
    service.system_upgrade(request.json)
    return make_nvr_manager_response()

@system.route('/upgrade/status')
def get_system_upgrade_status():
    return make_nvr_manager_response(service.get_system_upgrade_status())

@system.route('/upgrade/check')
def check_upgrade():
    return make_nvr_manager_response(service.check_upgrade())

@system.route('/upgrade/log')
def get_upgrade_log():
    return make_nvr_manager_response(service.get_upgrade_log())

@system.route('/modelhub/list')
def get_modelhub_list():
    return make_nvr_manager_response(service.get_modelhub_list())

@system.route('')
def get_system_info():
    return make_nvr_manager_response(service.get_system_info())

@system.route('/time', methods=["POST"])
def set_system_time():
    return make_nvr_manager_response(service.set_system_time(request.json))

@system.route('/reboot', methods=["POST"])
def reboot():
    return make_nvr_manager_response(service.reboot())

@system.route('/reset/data', methods=["POST"])
def reset_data():
    return make_nvr_manager_response(service.reset_data())
