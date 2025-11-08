from base.app import get_blueprint, make_nvr_manager_response
from . import service


usbcam_search = get_blueprint('usbcam-search', __name__)

@usbcam_search.route('')
def search_available_usbcam():
    return make_nvr_manager_response({'indexes': service.search_available_usbcam()})
