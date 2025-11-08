from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


source = get_blueprint('source', __name__)

@source.route('', methods=['POST'])
def register_source():
    return make_nvr_manager_response({'id': service.register_source(request.json)})
    
@source.route('/<id>')
def get_source(id: str):
    return make_nvr_manager_response(service.get_source(id))

@source.route('')
def get_sources():
    return make_nvr_manager_response({'source_list': service.get_source_list()})

@source.route('/<id>', methods=['PATCH'])
def patch_source(id: str):
    return make_nvr_manager_response(service.patch_source(id, request.json))

@source.route('/<id>', methods=['DELETE'])
def delete_source(id: str):
    return make_nvr_manager_response(service.delete_source(id))
