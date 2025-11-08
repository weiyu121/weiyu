import subprocess as sp
import threading
import re
import os
from typing import (
    Optional, 
    Callable
)


def inquire_env_info(name: str) -> dict:
    '''返回环境的详细信息'''
    
    # 解析conda命令的字符串
    python_version = sp.run(
        ['conda', 'run', '-n', name, 'python', '-V'],
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
    ).stdout.decode().strip()[7:]
    
    packages = sp.run(
        ['conda', 'run', '-n', name, 'pip', 'list'],
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
    ).stdout.decode().split('\n')[2:]

    return {
        'python': python_version,
        'packages': ','.join(filter(lambda package: package, map(lambda package: re.sub(' +', '==', package), packages)))
    }

def inquire_env_list() -> list[dict]:
    '''返回环境列表'''
    
    # 解析conda命令的字符串
    env_list = sp.run(
        ['conda', 'env', 'list'],
        stdout=sp.PIPE,
        stderr=sp.STDOUT,
    ).stdout.decode().split('\n')[2:-2]

    return list(  # 最终结果映射成list
        map(lambda m: {'name': m[1], 'path': m[2]},  # 将匹配成功的映射成dict
            filter(None,  # 将匹配失败的过滤掉
                map(lambda env: re.match(r'([^ ]+)[\s*]*([^ ]+)', env), env_list)  # 将name和path通过正则匹配出来
            )
        )
    )

# 若没有该环境，返回None
def inquire_env_path(name: str) -> str:
    tp = tuple(map(lambda env: env['path'], filter(lambda env: env['name'] == name, inquire_env_list())))
    return tp[0] if tp else None

def delete_env(name: str):
    try:
        sp.run(
            ['conda', 'env', 'remove', '-n', name],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
        )
    except Exception:
        pass

# 循环直到任务结束，返回进程返回码
def _loop_until_done(
        pipe: sp.Popen,
        log_callback: Optional[Callable[[str], None]]=None,  # 日志会写到这个回调里
        status_callback: Optional[Callable[[int], None]]=None  # 状态会写到这个回调里
) -> int:
    while pipe.poll() is None:
        log = pipe.stdout.readline().decode()
        if log_callback:
            log_callback(log)
    ret = pipe.poll()
    if ret != 0:
        if status_callback:
            status_callback(ret)
    return ret

def _install_packages(
    env_name: str,  # 环境名称
    packages: Optional[list[str]]=None,  # 明文的依赖
    requirements_root: Optional[str]=None,  # 该目录下至少得有个requirements.txt
    requirements_name: Optional[str]=None,  # requirements文件的路径
    index_url: Optional[str]=None,  # 主索引源
    extra_index_urls: Optional[list[str]]=None,  # 额外索引源列表
    log_callback: Optional[Callable[[str], None]]=None,  # 日志会写到这个回调里
    status_callback: Optional[Callable[[int], None]]=None  # 状态会写到这个回调里
):
    def loop_until_done(pipe: sp.Popen) -> int:
        return _loop_until_done(pipe, log_callback, status_callback)
    
    index_par_list = (['-i', index_url if index_url else 'https://pypi.tuna.tsinghua.edu.cn/simple']) \
        + ([par for tup in ([('--extra-index-url', extra_index_url) for extra_index_url in extra_index_urls]) for par in tup] if extra_index_urls else [])
    
    # 获取环境路径，用里面的pip安装，不然用conda run跑的话没实时日志
    env_path = inquire_env_path(env_name)

    if packages:
        if loop_until_done(sp.Popen(
            [os.path.join(env_path, 'bin', 'pip'), 'install'] + packages + index_par_list,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
        )) != 0:
            return False
    
    if requirements_name:
        if loop_until_done(sp.Popen(
            [os.path.join(env_path, 'bin', 'pip'), 'install', '-r', requirements_name] + index_par_list,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            cwd=requirements_root
        )) != 0:
            return False
    return True

def create_env(
    env_name: str,  # 环境名称
    python: str,  # python版本
    packages: Optional[list[str]]=None,  # 明文的依赖
    requirements_root: Optional[str]=None,  # 安装依赖时的工作路径
    requirements_name: Optional[str]=None,  # requirements文件的路径
    index_url: Optional[str]=None,  # 主索引源
    extra_index_urls: Optional[list[str]]=None,  # 额外索引源列表
    log_callback: Optional[Callable[[str], None]]=None,  # 日志会写到这个回调里
    status_callback: Optional[Callable[[int], None]]=None  # 状态会写到这个回调里
):
    '''调用该函数前，应确保检查工作已完成'''
    def wrapper():
        # 循环直到任务结束，返回进程返回码
        def loop_until_done(pipe: sp.Popen) -> int:
            return _loop_until_done(pipe, log_callback, status_callback)
        
        if loop_until_done(sp.Popen(
            ['conda', 'create', '-y', '-n', env_name, f'python={python}'],
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
        )) != 0:
            return
        
        if not _install_packages(env_name, packages, requirements_root, requirements_name, index_url, extra_index_urls, log_callback, status_callback):
            delete_env(env_name)
            return

        if status_callback:
            status_callback(0)
        
    threading.Thread(target=wrapper, daemon=True).start()

def install_packages(
    env_name: str,  # 环境名称
    packages: Optional[list[str]]=None,  # 明文的依赖
    requirements_root: Optional[str]=None,  # 该目录下至少得有个requirements.txt
    requirements_name: Optional[str]=None,  # requirements文件的路径
    index_url: Optional[str]=None,  # 主索引源
    extra_index_urls: Optional[list[str]]=None,  # 额外索引源列表
    log_callback: Optional[Callable[[str], None]]=None,  # 日志会写到这个回调里
    status_callback: Optional[Callable[[int], None]]=None  # 状态会写到这个回调里
):
    '''调用该函数前，应确保检查工作已完成'''
    def wrapper():
        if not _install_packages(env_name, packages, requirements_root, requirements_name, index_url, extra_index_urls, log_callback, status_callback):
            return

        if status_callback:
            status_callback(0)
        
    threading.Thread(target=wrapper, daemon=True).start()
