import json
import subprocess as sp
import os
import threading
import io
import time
from difflib import SequenceMatcher
from pathlib import Path

from config import config
from base.app import app
from ..ai_project.model.ai_project import AIProject
from ...device.model.device import Device


class AITaskDeamon:

    def __init__(self, device_id: str):
        self._process = None
        self._device_id = device_id
        self._running = True  # 就是守护线程要不要继续跑了
        self._restart = False  # 手动重启时，把这个指定为True，他就不等待直接重启进程了
        threading.Thread(target=self._daemon, daemon=True).start()
    
    def _daemon(self):
        # 将子进程的输出搬到日志文件中，这样就可以提供接口查阅运行日志了
        with open(Path(config.AITASK_LOG_DIR, f'{self._device_id}.output'), mode='w') as f_log:
            while self._running:
                with app.app_context():
                    cmds, cwd = self._get_aitask_args()
                
                if cmds is not None:
                    # 华为开发板需要激活一些环境变量
                    if config.is_atlas200idka2():
                        cmds = [
                            'source /usr/local/Ascend/ascend-toolkit/set_env.sh', '&&',
                            'source /usr/local/Ascend/mxVision/set_env.sh', '&&',
                        ] + cmds
                    self._process = sp.Popen(
                        ['bash', '-c', ' '.join(cmds)], 
                        stdout=sp.PIPE, 
                        stderr=sp.STDOUT,
                        cwd=cwd
                    )
                    text_out = io.TextIOWrapper(self._process.stdout)
                    is_omit = False
                    omit_peaces = 0

                    while self._process.poll() is None:
                        output = text_out.readline()
                        if not output:
                            break
                        if f_log.tell() > config._AITASK_LOG_MAX_BYTES:
                            f_log.truncate(0)
                            f_log.seek(0)
                        
                        if output.startswith('frame='):  # 只有ffmpeg推流省略
                            if not is_omit:  # 当前没有正在省略
                                f_log.write(output)
                                f_log.write('...\n')
                                f_log.flush()
                                is_omit = True
                            else:  # 当前正在省略
                                # 否则啥也不输出
                                omit_peaces += 1
                                if omit_peaces == 50:  # 最多连续省略50条
                                    f_log.write(output)
                                    f_log.flush()
                                    omit_peaces = 0
                        else:
                            f_log.write(output)
                            f_log.flush()
                            is_omit = False
                            omit_peaces = 0
                        
                    if not self._running:
                        f_log.write('# AI任务退出')
                        return

                # 这里判断是不是异常退出
                if self._restart:
                    self._restart = False
                    f_log.write('# 修改配置，AI任务重启......\n')
                else:
                    f_log.write(f'# AI任务异常退出，将在{config._AITASK_RESTART_INTERVAL_SECONDS}秒后重启......\n')
                    time.sleep(config._AITASK_RESTART_INTERVAL_SECONDS)
                    f_log.write(f'# AI任务重启\n')

    def restart(self):
        self._restart = True
        if self._process:
            self._process.terminate()

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()

    # 加这个东西的原因是为参数加上双引号防止转义
    @staticmethod
    def to_arg(value):
        return '"{}"'.format(str(value).replace('"', r'\"'))

    def _get_aitask_args(self) -> tuple[list[str], str]:
        device, ai_pro = Device.query.filter(Device.id == self._device_id).join(AIProject, Device.ai_project_id == AIProject.id).with_entities(Device, AIProject).one()
        
        cwd = os.path.join(config.AIPROJECT_DIR, str(ai_pro.id))
        # 判断程序是个啥程序
        if(ai_pro.entrypoint.endswith('.py')):  # py
            cmds = [os.path.join(ai_pro.env_path, 'bin', 'python'), ai_pro.entrypoint]
        elif(ai_pro.entrypoint.endswith('sh')):  # .bash/.sh
            cmds = ['bash', ai_pro.entrypoint]
        else:  # bin
            cmds = [os.path.join('.', ai_pro.entrypoint)]
        # 拼接启动命令，这些是基本参数
        cmds += [
            '--input', self.to_arg(device.source),
            '--output', self.to_arg(device.ai_rtmp_stream),
            '--alert_collect_url', self.to_arg(f'http://localhost:{config._SERVER_PORT}/alert/collect/{device.id}')
        ]

        ai_task_args = device['ai_task_args'] or {}

        # 如果有启动参数则追加启动参数
        # 追加检测区域参数
        ai_task_args['region'] = device['ai_region']

        # 追加报警配置参数
        ai_task_args['alert'] = device['ai_alert_config']
        
        # 处理所有的追加参数
        if ai_task_args:
            for k, v in ai_task_args.items():
                if v is None:
                    continue
                elif isinstance(v, list):
                    if v:
                        if isinstance(v[0], list):  # 适配二重列表数据（如多区域入侵）
                            for lst in v:
                                cmds.append(f'--{k}')
                                cmds.extend(map(self.to_arg, lst))
                        elif isinstance(v[0], dict):  # 适配二重字典数据（如报警，给他弄成json）
                            cmds.append(f'--{k}')
                            cmds.extend(map(self.to_arg, (json.dumps(dct, ensure_ascii=False) for dct in v)))
                        else:
                            cmds.append(f'--{k}')
                            cmds.extend(map(self.to_arg, v))
                elif type(v) == bool:
                    if v:
                        cmds.append(f'--{k}')
                else:
                    cmds.append(f'--{k}')
                    cmds.append(self.to_arg(v))
        return cmds, cwd