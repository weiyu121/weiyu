# 下面是这个东西存在的心路历程
# 这个东西存在的意义在于注册全局方法（函数），如果模块A想用模块B的方法，那么模块A就需要导入模块B
# 但如果恰好模块B也需要导入模块A，那么就会循环导入，结果就是完蛋了
# 对于这个情景一般来说是需要做功能抽离以及解耦的，但是再解耦只会增加工作量和代码的复杂性，对于当前的情况我也试过，发现逻辑上解不出去
# 之前对于两个模块需要相互调用方法的解决办法是直接用http走接口，但是后面开发到传感器数据上报mqtt时发现这样不太行，本来传感器数据走http感觉就不太行
# 不过这是Python，于是就想到了可以把需要别的模块调用的方法注册到全局就可以了
# 所以想来想去就想出了这么个东西，从设计上不太美观但是有效并且效率比之前走http接口要高，然后也不弄这么复杂，简简单单的也比较好

# @后面虽然还是给mqtt挪到base里了
from flask import has_request_context

from base.app import app


class MethodsProxy:
    pass

methods = MethodsProxy()  # 寄存所有方法的对象
methods_noerror = MethodsProxy()  # 同时给方法注册一个不抛异常的版本，用起来就不用捕获异常了

# 为了保证函数名称全局不冲突，要以[<模块名>(_<子模块名>...)_方法名]命名
def register_method(name: str):
    def deco(func):
        def wrapper(*args, **kwargs):
            if not has_request_context():  # 当不在req上下文时，将app上下文添加上去
                with app.app_context():
                    return func(*args, **kwargs)
            return func(*args, **kwargs)
        def noerror_wrapper(*args, **kwargs):
            try:
                return wrapper(*args, **kwargs)
            except:
                pass
        setattr(methods, name, wrapper)
        setattr(methods_noerror, name, noerror_wrapper)
        return func
    return deco
