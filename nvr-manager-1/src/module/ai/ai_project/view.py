from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


ai_project = get_blueprint('ai-project', __name__)

@ai_project.route('', methods=['POST'])
def create_ai_project():
    return make_nvr_manager_response({'id': service.update_ai_project(request.files.get('project_zip'), request.form)})
    
@ai_project.route('')
def get_ai_project_list():
    return make_nvr_manager_response(service.get_ai_project_list())

@ai_project.route('/<int:id>', methods=['PATCH'])
def update_ai_project(id: int):
    service.update_ai_project(request.files.get('project_zip'), up_pro_id=id)
    return make_nvr_manager_response()

# @ai_project.route('/<int:id>/model', methods=['PATCH'])
# def update_ai_project_model(id: int):
#     service.update_ai_project_model(id, request.form, request.files.get('model'))
#     return make_nvr_manager_response()
    
@ai_project.route('/<int:id>')
def get_ai_project_info(id: int):
    return make_nvr_manager_response(service.get_ai_project_info(id))
    
@ai_project.route('/<int:id>/status')
def get_ai_project_status(id: int):
    return make_nvr_manager_response(service.get_ai_project_status(id, request.args))

@ai_project.route('/<int:id>', methods=['DELETE'])
def delete_ai_project(id: int):
    service.delete_ai_project(id)
    return make_nvr_manager_response()

@ai_project.route('/default', methods=['PATCH'])
def set_default_ai_project():
    service.set_default_ai_project(request.json)
    return make_nvr_manager_response()

@ai_project.route('/default')
def get_default_ai_project():
    return make_nvr_manager_response(service.get_default_ai_project())
