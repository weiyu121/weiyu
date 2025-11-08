from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Iterable, Optional, Union, Any


thread_pool = ThreadPoolExecutor()

def wait_muti_run(fn: Callable, args_list: Optional[Iterable[Union[dict, list, Any]]]=None, count: Optional[int]=None) -> Iterable:
    '''封装一下submit方法，因为map不太好用，它只能按顺序传参，不能指定参数，用requests的时候尤其不便
    当传args_list参数时，运行的次数为该参数的数量，迭代内容为参数：
        如果子项是dict，则会使用字典解引用的方式传参；
        如果子项是list，则会使用列表解引用的方式传参；
        如果子项是其余情况，则会将参数作为第一个参数传入
    当传countc参数时，函数会额外以无参数的形式运行count次。
    如：
        sync_muti_run(A, ({'a': a} for a in range(10))  # 函数A的参数a分别取0~9运行函数A
        sync_muti_run(A, count=10)  # 函数A以无参的形式运行10次
        sync_muti_run(A, range(10), count=10)  # 函数A分别以参数0~9和无参的方式各运行10次，返回的结果为有参运行结果与无参运行结果的拼接
    '''

    fs = []
    def submit(arg: Any) -> Future:
        if type(arg) == dict:
            return thread_pool.submit(fn, **arg)
        elif type(arg) == list:
            return thread_pool.submit(fn, *arg)
        return thread_pool.submit(fn, arg)

    fs += [submit(arg) for arg in args_list]
    if count:
        fs += [thread_pool.submit(fn) for _ in range(count)]
    
    return [fs.result() for fs in fs]
