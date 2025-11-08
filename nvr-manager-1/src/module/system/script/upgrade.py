from pathlib import Path
import sys
import os


def run(cmd, devnull=False):
    if devnull:
        return os.system(f'{cmd} >> /dev/null 2>&1')
    return os.system(cmd)

def lprint(*args, **kwargs):
    print(*args, **kwargs, flush=True)

os.environ['PATH'] = '/usr/local/sbin:/usr/sbin:/sbin:' + os.environ['PATH']  # ISSUE: nvr-manager.service没有配置sbin环境变量，导致无法安装软件包

lprint('# 正在更新软件前端...')
nvr_manager_web_home = '/usr/local/nvr-manager-web'
run(f'rm {nvr_manager_web_home} -rf')
run(f'cp web {nvr_manager_web_home} -r')
run('cp etc/nvr-manager.conf /etc/nginx/conf.d/')
run('systemctl start nginx')
run('systemctl reload nginx')

lprint('# 正在更新软件后端...')
nvr_manager_home = '/usr/local/nvr-manager'
run('ln -s -f /usr/local/conda/bin/conda /bin/conda')
run(f'conda run --no-capture-output -n nvr-manager pip install -r requirements.txt')
run(f'rm {nvr_manager_home}/src -rf && cp src {nvr_manager_home}/ -r')
run(f'cp etc/nvr-manager.service /usr/lib/systemd/system/')
run(f'systemctl daemon-reload')

if Path('/sys/kernel/debug/rknpu').exists():
    if run('type nd5g', True) != 0:
        lprint('# 检测到没有nd5g，即将安装nd5g命令...')
        run('dpkg -i softwares/nd5g/utilneardi-nd5g1.0_arm64.deb')

lprint('# 正在更新数据库...')
os.chdir(nvr_manager_home)

# 修改遗留问题，将live_rtsp_stream字段名改为source，前面这个名称容易让人误解
# sqlalchemy没法在不修改生成脚本的情况下更改列名，所以需要用执行sql代码的方法修改
change_device_column_cmds = """
DELIMITER //

DROP PROCEDURE IF EXISTS rename_lrs;
CREATE PROCEDURE rename_lrs()
BEGIN
    IF EXISTS (SELECT * FROM information_schema.columns WHERE table_schema = 'nvr-manager' AND table_name = 'device' AND column_name = 'live_rtsp_stream') THEN
        IF EXISTS (SELECT * FROM information_schema.columns WHERE table_schema = 'nvr-manager' AND table_name = 'device' AND column_name = 'source') THEN
            ALTER TABLE device DROP COLUMN source;
        END IF;
        ALTER TABLE device CHANGE live_rtsp_stream source TEXT;
    END IF;
END //
DELIMITER ;
CALL rename_lrs();
DROP PROCEDURE IF EXISTS rename_lrs;
"""
run(f'mysql -uroot -D nvr-manager -e "{change_device_column_cmds}"')
run(f'{sys.executable} -m flask --app src/migration.py db migrate')
run(f'{sys.executable} -m flask --app src/migration.py db upgrade')

lprint('# 更新完成！')

run('systemctl restart nvr-manager')  # 执行这个之后，这个脚本所在的进程会被杀死，所以这个命令放在最后
