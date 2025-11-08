import os
import zipfile
import glob
import yaml
import re
import requests
from pathlib import Path
from tempfile import TemporaryFile, TemporaryDirectory
from typing import Any, Optional
from distutils.util import strtobool
from git import Repo

from config import config
from base.init import init
from base.ext import db
from base.app import app
from base.logger import get_logger
from base.threadpool import wait_muti_run
from base.setting import *
from base.methods import register_method, methods_noerror
from .model.ai_project import AIProject
from ...device.model.device import Device
from . import conda
from .exception import (
    AIProjectNotExistsError,
    AIProjectCreatingError,
    AIProjectDeletingError,
    AIProjectUpdatingError,
    AIProjectModelUpdatingError,
    AIProjectOfDefaultNotExistsError,
)


_logger = get_logger('ai.ai_project')
_env_preparing_status = {}
if config.is_rk3588():
    _public_env_name = 'nvrpro'
elif config.is_atlas200idka2():
    _public_env_name = 'base'

def _unzip_to(zip: Any, dir: str, not_zip_error: Optional[Any]=None) -> bool:
    # zip可以传file或者str
    with TemporaryFile('w+b') as temp_file:
        file = None
        if type(zip) == str:
            file = zip
        else:
            # 存到临时文件缓存中，然后解压
            file = temp_file
            zip.save(file)
            file.seek(0)

        if not zipfile.is_zipfile(file):
            if not_zip_error:
                raise not_zip_error
            return False
        zipfile.ZipFile(file).extractall(dir)

    return True

def _get_ai_project_path(id: int):
    return os.path.join(config.AIPROJECT_DIR, str(id))

@init
def makedirs():
    os.makedirs(config.AIPROJECT_DIR, exist_ok=True)

def get_ai_project_list() -> dict:
    return {
        'ai_project_list': list(map(lambda ai_pro: {'id': ai_pro.id, **_get_ai_project_info(ai_pro)}, AIProject.query.all())),
    }

def _get_ai_project_info(ai_pro: AIProject) -> dict:
    info = ai_pro.to_dict()
    info['status'] = _get_ai_project_status(ai_pro, False)['status']
    
    return dict(filter(
        lambda kv: kv[0] in [
            'name',
            'description',
            'version',
            # 'model_version',
            'git_url',
            'optional_args',
            'alert_config',
            'model_hub_id',
            'status',
            'default'
        ],
    info.items()))

def get_ai_project_info(id: int) -> dict:
    ai_pro = AIProject.query.get(id)
    if not ai_pro:
        raise AIProjectNotExistsError(f'AI项目{id}不存在')
    return _get_ai_project_info(ai_pro)

def git_url_to_ssh_url(git_url: str) -> str:
    if re.match(r'git@.*:.*', git_url) is None:
        m = re.match(r'https?://(.*?)/(.*)', git_url)
        if m is None:
            raise AIProjectCreatingError(f'AI项目创建失败，Git地址不符合规范，请设置为SSH格式或者HTTP格式的git地址')
        git_url = 'git@{}:{}'.format(m[1], m[2])
         
    if not git_url.endswith('.git'):
        git_url += '.git'
    return git_url

class NVRProConfig:
    def __init__(self, config: dict):
        # 路径配置
        self.deploy_root = None  # 部署的根目录
        self.deploy_entrypoint = None  # 部署的入口程序相对于根目录的位置（要往表里写的）
        # 描述信息
        self.name = None  # 项目名称
        self.description = None  # 项目描述
        self.version = None  # 项目版本
        # 云端配置
        self.git_url = None  # Git地址
        # 可选参数配置
        self.optional_args = None  # 可选参数
        # 报警配置
        self.alert_config = None  # 报警配置
        # Python环境配置
        self.python = False  # 是否需要准备Python环境
        self.python_new_env = None  # 新建Python环境
        self.python_requirements = None  # Python依赖
        self.python_index_url = None  # Python主索引源
        self.python_extra_index_url = None  # Python额外索引源
        try:
            if 'nvrpro' not in config:
                self._v1(config)
            elif config['nvrpro'] == 1:
                self._v1(config)
            elif config['nvrpro'] == 2:
                self._v2(config)
        except KeyError as e:
            raise ValueError(f'nvrpro配置中缺少必填字段：{e}')

    def _v1(self, config: dict):
        # 解析V1版本
        self.deploy_root = Path(config['src']['root'])
        self.deploy_entrypoint = Path(config['src']['entrypoint'])

        self.python = True
        self.python_new_env = config.get('new_env')
        self.python_requirements = config.get('requirements')
        self.python_index_url = config.get('index_url')
        self.python_extra_index_url = config.get('extra_index_url')

        self._common(config)

    def _v2(self, config: dict):
        # 解析V2版本
        self.deploy_root = Path(config['deploy']['root'])
        self.deploy_entrypoint = Path(config['deploy']['entrypoint'])

        if 'python' in config:
            python = config['python']
            self.python = True
            self.python_new_env = python.get('new_env')
            self.python_requirements = python.get('requirements')
            self.python_index_url = python.get('index_url')
            self.python_extra_index_url = python.get('extra_index_url')

        self._common(config)
    
    def _common(self, config: dict):
        # 解析通用配置
        self.name = config['name']
        self.description = config['description']
        self.version = config['version']
        self.git_url = git_url_to_ssh_url(config['git_url'])
        self.optional_args = config.get('optional_args')
        self.alert_config = config.get('alert')

def _update_ai_project(tmp_pro_root: str, tmp_dir: TemporaryDirectory, up_ai_project: Optional[AIProject]=None, **kwargs):
    # tmp_pro_root指的是有可能项目解压之后直接就是项目，或者解压之后其实是个文件夹进去之后才是项目，考虑到两种可能性，做了个判断，如果是文件夹，那就进去操作
    # temp_dir就是临时目录对象，项目初始化完之后才能删掉，得写到线程里，所以不能用环境管理器，得手动调他的删除方法
    nvrpro_config_path = Path(tmp_pro_root, 'nvrpro.yaml')

    if not nvrpro_config_path.exists():
        raise AIProjectCreatingError('AI项目创建失败，项目配置文件nvrpro.yaml不存在') \
            if up_ai_project else AIProjectUpdatingError('AI项目更新失败，项目配置文件nvrpro.yaml不存在')
    try:
        cfg = yaml.safe_load(nvrpro_config_path.read_text())
    except:
        raise AIProjectCreatingError('AI项目创建失败，nvrpro.yaml语法格式错误，解析yaml语法格式失败')

    try:
        nvrconf = NVRProConfig(cfg)
    except ValueError as e:
        raise AIProjectCreatingError(f'AI项目创建失败，{e}') \
            if up_ai_project else AIProjectUpdatingError(f'AI项目更新失败，{e}')

    # 检查项目入口是否存在
    if not (tmp_pro_root / nvrconf.deploy_root / nvrconf.deploy_entrypoint).exists():
        raise AIProjectCreatingError(f'AI项目创建失败，项目入口程序[{nvrconf.deploy_root / nvrconf.deploy_entrypoint}]不存在') \
            if up_ai_project else AIProjectUpdatingError(f'AI项目更新失败，项目入口程序[{nvrconf.deploy_root / nvrconf.deploy_entrypoint}]不存在')

    # 把Git地址处理成统一的格式，之后好用来判断是不是一个项目
    if not up_ai_project:
        # 下面是创建新项目
        conflict_pros = AIProject.query.filter(AIProject.git_url == nvrconf.git_url).all()
        if len(conflict_pros) > 0:
            raise AIProjectCreatingError(f'AI项目创建失败，该项目已存在，其与{conflict_pros[0].name}项目有着相同的项目地址：{conflict_pros[0].git_url}')

        ai_project = AIProject(
            git_url=nvrconf.git_url
        )

    else:
        # 下面是更新项目，而不是重新创建
        if nvrconf.version == up_ai_project.version and up_ai_project.env_ok:
            _logger.info(f'AI项目{up_ai_project.id}与云端版本号相同，忽略更新请求')
            return up_ai_project.id
        
        if up_ai_project.env_path:  # 如果之前环境创建失败了，那么不做这个判断
            if nvrconf.python_new_env and Path(up_ai_project.env_path).name != _public_env_name:
                # 如果之前的是新环境，现在还需要新环境，那就把之前那个删了，重新创建，毕竟不知道他需要的Python版本是否更改了，索性就把之前的环境删了
                conda.delete_env(f'nvrpro-{up_ai_project.id}')
        # 其他情况都不需要操作
        ai_project = up_ai_project
    
    ai_project.name = nvrconf.name
    ai_project.description = nvrconf.description
    ai_project.version = nvrconf.version
    ai_project.entrypoint = nvrconf.deploy_entrypoint
    ai_project.optional_args = nvrconf.optional_args
    ai_project.alert_config = nvrconf.alert_config
    ai_project.env_path = None
    ai_project.env_ok = not nvrconf.python  # 不用python就直接好
    for k, v in kwargs.items():
        ai_project[k] = v
        
    if not up_ai_project:
        db.session.add(ai_project)
    
    db.session.commit()

    # 先把项目目录删除重新创建，然后给项目文件从临时文件夹挪到它该去的地方
    id = ai_project.id
    pro_root = _get_ai_project_path(id)
    os.system(f'rm -rf {pro_root}/* && mkdir -p {pro_root} && mv {tmp_pro_root / nvrconf.deploy_root / "*"} {pro_root}/')
    if up_ai_project and ai_project.env_ok:
        _restart_ai_task(up_ai_project.id)  # 环境已经好了，直接重启

    if nvrconf.python:
        # 处理依赖安装字段
        requirements = nvrconf.python_requirements
        packages, requirements_name = None, None
        if requirements:
            if type(requirements) == list:
                packages = requirements
            elif type(requirements) == str:
                requirements_name = requirements
        
        extra_index_url = nvrconf.python_extra_index_url
        if extra_index_url:
            if type(extra_index_url) != list:
                extra_index_url = [extra_index_url]

        def log_process(log: str):
            _env_preparing_status[id]['log'] += log
        
        env_name = None
        def status_process(code: int):
            if code == 0:
                # 环境准备成功，修改数据库，并且把日志删掉即可
                with app.app_context():
                    # 得重新获取orm，不然用外面的orm修改不生效
                    ai_project = AIProject.query.get(id)
                    ai_project.env_ok = True
                    ai_project.env_path = conda.inquire_env_path(env_name)
                    db.session.commit()
                    if up_ai_project:
                        _restart_ai_task(up_ai_project.id)  # 环境准备好后重启所有AI任务
                _env_preparing_status.pop(id)
            else:
                _env_preparing_status[id]['log'] += f'\n异常退出，程序返回值为：{code}'
                _env_preparing_status[id]['done'] = True
            tmp_dir.cleanup()  # 不管环境准备成功还是失败，都把临时目录删掉

        # 环境准备的日志
        _env_preparing_status[id] = {
            'done': False,  # 进程是否退出
            'log': ''  # 日志
        }  

        if nvrconf.python_new_env:
            env_name = f'nvrpro-{id}'
            conda.create_env(
                env_name,
                nvrconf.python_new_env,
                packages,
                tmp_pro_root,
                requirements_name,
                cfg.get('index_url'),
                extra_index_url,
                log_process,
                status_process
            )
        else:
            env_name = _public_env_name
            conda.install_packages(
                env_name,
                packages,
                tmp_pro_root,
                requirements_name,
                cfg.get('index_url'),
                extra_index_url,
                log_process,
                status_process
            )
    return id

# AI任务重启
def _restart_ai_task(project_id: int):
    # 获取所有正在运行的ai任务id
    device_ids = [row[0] for row in Device.query.filter(Device.ai_project_id == project_id, Device.ai_task_enable == True).with_entities(Device.id).all()] or None

    # 重新启动所有之前运行的AI任务
    if device_ids:
        wait_muti_run(requests.post, (f'http://localhost:{config._SERVER_PORT}/ai-task/{device_id}/restart' for device_id in device_ids))
        _logger.debug(f'已重启设备{device_ids}的AI任务')

# 这个神奇的函数可以新建或者更新AI项目，zip压缩包参数对于新建和更新都可以使用，args在新建时可能会传进来在线创建的地址以及其他直传给AIProject的参数
# 而当指定了up_pro_id后，函数会运行为更新模式而不是新建，此时会忽略args
def update_ai_project(project_zip: Optional[Any]=None, args: Optional[dict]=None, up_pro_id: Optional[int]=None):
    temp_dir = TemporaryDirectory()
    root = temp_dir.name

    up_pro = AIProject.query.get(up_pro_id) if up_pro_id else None
    if up_pro_id and not up_pro:
        raise AIProjectNotExistsError(f'AI项目更新失败，AI项目{up_pro_id}不存在')

    # 如果是升级的话，必然是能取到git_url的
    git_url = args.get('git_url') if not up_pro else up_pro.git_url

    try:
        if project_zip:
            _unzip_to(project_zip, root, AIProjectCreatingError('AI项目创建失败，上传的项目文件不是zip压缩文件') if up_pro_id else AIProjectUpdatingError('AI项目更新失败，上传的项目文件不是zip压缩文件'))
        elif git_url:
            Repo.clone_from(git_url_to_ssh_url(git_url), root)
        else:
            raise AIProjectCreatingError('AI项目创建失败，请上传项目压缩包或者指定git地址')
    
        # Zip压缩包里或者git有可能会套一个最外层目录
        file_list = glob.glob(f'{root}/*')
        if len(file_list) == 1 and os.path.isdir(file_list[0]):
            # 就一个文件夹，项目在那个文件夹里面
            root =  file_list[0]
        
        if up_pro:
            return _update_ai_project(root, temp_dir, up_pro)
        else:
            return _update_ai_project(root, temp_dir, up_pro, model_hub_id=args.get('model_hub_id'), default=bool(strtobool(args.get('default'))) if 'default' in args else False)
    
    except Exception as e:
        temp_dir.cleanup()
        raise e

# def update_ai_project_model(id: int, args: dict, upload_file: Optional[Any]=None):
#     ai_project = AIProject.query.get(id)
#     if not ai_project:
#         raise AIProjectNotExistsError(f'AI项目{id}不存在')
#     version, url = args.get('version') or '未知', args.get('url')
#     model_path = os.path.join(_get_ai_project_path(id), ai_project.model_path)

#     with TemporaryDirectory() as tdir:
#         if not upload_file and not url:
#             raise AIProjectModelUpdatingError('模型更新失败，请上传更新文件或者指定更新文件的下载地址')
#         if upload_file:
#             # 尝试解压
#             if _unzip_to(upload_file, tdir):
#                 flist = glob.glob(os.path.join(tdir, '**', '*.rknn'), recursive=True)
#                 if len(flist) == 0:
#                     raise AIProjectModelUpdatingError('模型更新失败，上传的压缩包内没有找到.rknn模型文件')
#                 os.system(f'mv {flist[0]} {model_path}')
#             else:
#                 # 那就直接当这个文件是模型文件
#                 upload_file.seek(0)
#                 upload_file.save(model_path)
#         else:
#             # 下载模型文件
#             file_path = os.path.join(tdir, '.model')
#             chunk_size = 1024 * 1024
#             try:
#                 with requests.get(url, stream=True) as rf:
#                     with open(file_path, 'wb') as f:
#                         for chunk in rf.iter_content(chunk_size):
#                             if chunk:
#                                 f.write(chunk)
#             except Exception as e:
#                 raise AIProjectModelUpdatingError(f'模型更新失败，原因为：{str(e)}')
#             # 和前面一样，尝试解压
#             if _unzip_to(file_path, tdir):
#                 flist = glob.glob(os.path.join(tdir, '**', '*.rknn'), recursive=True)
#                 if len(flist) == 0:
#                     raise AIProjectModelUpdatingError('模型更新失败，下载的压缩包内没有找到.rknn模型文件')
#                 os.system(f'mv {flist[0]} {model_path}')
#             else:
#                 os.system(f'mv {file_path} {model_path}')
            
#         ai_project.model_version = version
#         db.session.commit()
#     _restart_ai_task(id)

def _get_ai_project_status(ai_pro: AIProject, get_log: Optional[bool]=False) -> dict:
    if ai_pro.env_ok:
        return {
            'status': 'Succeeded',
            'log': '项目环境初始化成功' if get_log else None
        }
    env_status = _env_preparing_status.get(ai_pro.id)  
    if env_status:
        if env_status['done']:
            return {
                'status': 'Failed',
                'log': env_status['log']
            }
        return {
            'status': 'Initializing',
            'log': env_status['log']
        }
    return {
        'status': 'Failed',
        'log': '日志已被清理，请重新更新或者删除后重新创建该AI项目'
    }

def get_ai_project_status(id: int, pars: dict) -> dict:
    ai_project = AIProject.query.get(id)
    if not ai_project:
        raise AIProjectNotExistsError(f'AI项目{id}不存在')
    return _get_ai_project_status(ai_project, bool(strtobool(pars.get('get_log'))) if 'get_log' in pars else False)

def delete_ai_project(id: int):
    ai_project = AIProject.query.get(id)
    if not ai_project:
        raise AIProjectNotExistsError(f'AI项目{id}不存在')
    
    if _get_ai_project_status(ai_project)['status'] == 'Initializing':
        raise AIProjectDeletingError(f'AI项目{id}删除失败，请等待其初始化结束')
    
    if id in _env_preparing_status:
        _env_preparing_status.pop(id)
    
    associated_devices = Device.query.filter(Device.ai_project_id == id).all()
    for device in associated_devices:
        device.ai_project_id = None
        device.ai_task_enable = None
        device.ai_task_args = None
        device.ai_alert_config = None
    
    # 给AI任务先关掉
    wait_muti_run(methods_noerror.ai_task_stop_ai_task, [device.id for device in associated_devices])

    db.session.delete(ai_project)
    db.session.commit()

    os.system(f'rm -rf {_get_ai_project_path(id)}')

    # 删除自定义conda环境
    if ai_project.env_path:
        env_name = os.path.basename(ai_project.env_path)
        if env_name != _public_env_name:
            conda.delete_env(env_name)

def set_default_ai_project(pars: dict):
    ai_project_id = pars.get('ai_project_id')
    if ai_project_id is None:
        raise AIProjectNotExistsError('无法查询到AI项目，请正确传入参数ai_project_id')
    
    ai_project = AIProject.query.get(ai_project_id)
    if not ai_project:
        raise AIProjectNotExistsError(f'AI项目{ai_project_id}不存在')
    
    current_default_aipro = AIProject.query.filter(AIProject.default==True).all()
    if current_default_aipro:
        if current_default_aipro[0].id == ai_project.id:
            # 相当于没改，就不用改数据库了
            return
        current_default_aipro[0].default = False
    ai_project.default = True
    db.session.commit()

@register_method('ai_project_get_default_ai_project')
def get_default_ai_project() -> dict:
    ai_pro = None
    ai_pros = AIProject.query.filter(AIProject.default==True).all()
    if ai_pros:
        ai_pro = ai_pros[0]
    if not ai_pro:
        raise AIProjectOfDefaultNotExistsError(f'没有默认的AI项目')
    
    return {'id': ai_pro.id, **_get_ai_project_info(ai_pro)}

@setting('ai.ai_project')
def _setting():
    return ModuleSetting({
            'project_dir': Scope(
                'AIPROJECT_DIR', 
                cast_path,
                validator=Validator.PATH_NOT_EMPTY
            )
        },
        setting_callback=lambda settings: os.system(f'mv {config.AIPROJECT_DIR} {settings["project_dir"]}')
    )
