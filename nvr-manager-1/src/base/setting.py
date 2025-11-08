# 提供设置能力，可以用在每个模块中对一些参数进行设置
import json
from typing import Callable, Any
from pathlib import Path
from distutils.util import strtobool

from config import config
from base.init import init


_modules = {}

# bool类型转换最好用这个函数，别用内置bool强制转换，这个函数可以把bool，int，str都转为bool
def cast_bool(value: Any) -> bool:
    if type(value) == str:
        value = strtobool(value)
    return bool(value)

# 路径类型的都用这个，会将相对路径都转为绝对路径
def cast_path(value: Any) -> str:
    return str(Path(value).resolve())

# 公共验证器，比较通用的都先写到这里面，然后直接用就行了
class Validator:

    @staticmethod
    def PATH_NOT_EMPTY(path: str):
        if Path(path).exists():
            raise ValueError(f'路径{path}所指向的位置不为空')
    
    @staticmethod
    def FILE_EXISTS(path: str):
        '''该路径存在非目录的文件则验证失败'''
        path = Path(path)
        if path.exists() and path.is_file():
            raise ValueError(f'路径{path}已存在一个同名的非目录文件')

    @staticmethod
    def TIME(time: str):
        try:
            from datetime import datetime
            datetime.strptime(time, '%H:%M:%S')
        except:
            raise ValueError('请传入[时:分:秒]这样的时间格式')
        
    @staticmethod
    def INT_RANGE(begin: int=None, end: int=None):
        def wrapper(value):
            if begin is not None and value < begin or end is not None and value > end:
                raise ValueError(f'数值超出范围[{begin if begin is not None else "-∞"},{end if end is not None else "∞"}]')
        return wrapper
    
    @staticmethod
    def PORT(value):
        if not (value >= 0 and value <= 65535):
            raise ValueError(f'端口号应在[0,65535]之间')

    @staticmethod
    def STR_NOT_EMPTY(value):
        if value == '':
            raise ValueError('字符串不能为空')

class Scope:
    def __init__(
        self, 
        config_name: str,
        type: Any=str,
        validator: Callable[[Any], None]=None, 
        ignore_none: bool=True
    ):
        '''
        表示一个设置字段
        参数：
            @ config_name：配置字段名称。会验证该参数值是否和配置中的值是否相同，如果相同，则会忽略更新该字段
            @ type：设置字段类型，所有设置都会被转换成该类型后再验证有效性，如果转换失败则会直接报错。
            @ validator：字段验证器，是一个回调函数，若调用该函数不抛异常则表示验证通过。
                注意：如果同时设置了ignore_none为False，且用户传入None，则不会调用验证器。
            @ ignore_none：如果用户传入None，是否忽略该用户对该字段参数的设置，如果不忽略，则该字段可以被设置为None；否则对该字段的设置会被过滤掉
        '''
        self.config_name = config_name
        self.type = type
        self.validator = validator
        self.ignore_none = ignore_none

class ModuleSetting:

    def __init__(
        self, 
        scopes: dict[str, Scope], 
        setting_callback: Callable[[dict[str, Any]], None]=None
    ) -> None:
        '''
        表示一个模块的设置
        参数：
            @ scopes：所有设置的字段，传入{设置名称:Scope对象}格式的字典
            @ setting_callback：用户对该模块进行设置时，若至少有一个字段需要更新，则会调用该回调函数【该回调函数的调用时机在更新config之后】。
        '''
        self._scopes = scopes
        self._setting_callback = setting_callback

        self.name = None

    def check_and_convert(self, settings: dict) -> dict:
        filtered_setting = {}
        for name, value in settings.items():
            scope = self._scopes.get(name)
            if scope is None:
                continue
            
            # 先验证None值是否需要忽略
            if value is None:
                if scope.ignore_none:
                    continue
            else:
                # 再进行类型转换
                try:
                    value = scope.type(value)
                except:
                    raise ValueError(f'{name}参数转换异常，无法将{value}转换为{scope.type.__name__}类型')
                
            # 看一下是否和config里的配置一模一样，要是一样就可以忽略了
            config_value = getattr(config, scope.config_name)
            if config_value is not None:
                config_value = scope.type(config_value)  # FIX:已存在的配置文件里的路径为相对路径，新设置的路径被转换为绝对路径，两者不匹配
            
            if config_value == value:
                continue

            # 再进行有效验证
            if value is not None and scope.validator is not None:
                try:
                    scope.validator(value)
                except Exception as e:
                    raise ValueError(f'{name}设置失败，{str(e)}')
            
            filtered_setting[name] = value

        return filtered_setting or None
            
    def update(self, settings: dict):
        for name, value in settings.items():
            setattr(config, self._scopes[name].config_name, value)
    
    def call_callback_func(self, settings):
        if self._setting_callback:
            self._setting_callback(settings)
    
    def get(self):
        return {
            name: getattr(config, scope.config_name) for name, scope in self._scopes.items()
        }
    
def setting(module_name: str):
    def wrapper(setting_func: Callable[[None], ModuleSetting]):
        module_setting = setting_func()
        if not isinstance(module_setting, ModuleSetting):
            raise TypeError(f'{setting_func}设置函数必须返回一个ModuleSetting对象')
        module_setting.name = module_name
        # 拆开，将所有嵌套的子模块按照顺序排列
        sub_modules = module_name.split('.')
        module_map = _modules
        for i, module in enumerate(sub_modules):
            next_module_map = module_map.get(module)  # 判断{}下是否有a模块
            if i == len(sub_modules) - 1:  # 最后一层子模块了，需要将module_setting赋值进去
                if next_module_map is not None:
                    raise ValueError(f'{module_name}无法被注册为设置器，因为{module_name}前缀已经被其他模块占用')
                module_map[module] = module_setting
            elif next_module_map is not None:  # 如果下一级子模块字典已经存在了，把他拿出来
                module_map = next_module_map
            else:  # 如果下一级子模块字典不存在，就构建一个新字典
                new_module = {}
                module_map[module] = new_module
                module_map = new_module
        return setting_func
    return wrapper

def get_settings() -> dict:
    def dfs_map(setting: dict) -> dict:
        return dict(map(lambda kv: (kv[0], kv[1].get() if isinstance(kv[1], ModuleSetting) else dfs_map(kv[1])), setting.items()))
    return dfs_map(_modules)

def update_settings(settings: dict):
    module_map = []
    def get_update_modules(setting: dict, module_dict: dict):
        # s_or_m_n: setting or module name
        for s_or_m_n, sub_setting in setting.items():
            s_or_m = module_dict.get(s_or_m_n)
            if s_or_m is not None:  # 这个是子模块，而不是设置项
                if isinstance(s_or_m, ModuleSetting):  # 如果这个子模块对应一个更新器，那就到此为止了
                    try:
                        converted_setting = s_or_m.check_and_convert(sub_setting)
                    except ValueError as e:
                        raise ValueError(f'[{s_or_m.name}]{str(e)}')
                    if converted_setting is not None:
                        module_map.append((s_or_m, converted_setting))
                else:  # 否则就递归调用子模块更新函数
                    get_update_modules(sub_setting, s_or_m)
    get_update_modules(settings, _modules)
    for module, converted_setting in module_map:
        module.update(converted_setting)
    for module, converted_setting in module_map:
        module.call_callback_func(converted_setting)
    config.save_config()

@init  # 初始化时订阅
def _subscribe_update_setting():
    # 只能在这里面导，不然就循环引用了
    from base.mqtt import get_mqtt_service, on_connected
    def update(settings: dict):
        try:
            if 'setting' in settings:
                # 如果这个字段是str，则用json解析成字典，如果本来就是字典，那就不解析
                update_settings(settings['setting'] if isinstance(settings['setting'], dict) else json.loads(settings['setting']))
                feedback = {
                    'ok': True,
                    'message': None
                }
            else:
                feedback = {
                    'ok': False,
                    'message': '请在setting字段中传入json格式的设置信息'
                }
        except Exception as e:
            feedback = {
                'ok': False,
                'message': str(e)
            }
        feedback['setting'] = get_settings()
        # 上报反馈失败直接不管，因为下发指令需要网络连接好，反馈紧接其后大概率不会出问题
        get_mqtt_service().report_update_setting_feedback(feedback)
        
    @on_connected  # 以及重连接时重新订阅
    def sub():
        get_mqtt_service().subscribe_update_setting(update)

    sub()