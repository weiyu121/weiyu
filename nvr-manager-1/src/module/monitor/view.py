from base.app import get_blueprint, make_nvr_manager_response
from . import service


monitor = get_blueprint('monitor', __name__)

@monitor.route('')
def get_system_info():
    return make_nvr_manager_response(service.get_system_info())
