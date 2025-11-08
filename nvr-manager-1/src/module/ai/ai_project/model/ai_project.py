from base.ext import db, BaseModel


@BaseModel.Scope(
    optional_args=BaseModel.ScopeType.JSON,
    alert_config=BaseModel.ScopeType.JSON,
)
class AIProject(BaseModel):

    # 主键
    id = db.Column(db.Integer, primary_key=True, nullable=False)
    # 项目名称（描述性信息）
    name = db.Column(db.String(20), nullable=False)
    # 项目Python环境路径（暂定所有项目共用一个Python3.9的环境，但如果冲突了也可以创建独立的环境）
    env_path = db.Column(db.String(50), nullable=True)
    # 项目入口程序路径
    entrypoint = db.Column(db.String(50), nullable=False)
    # 项目描述（描述性信息）
    description = db.Column(db.String(50), nullable=False)
    # 项目版本（描述性信息）
    version = db.Column(db.String(20), nullable=False)
    # 可替换的模型路径
    # model_path = db.Column(db.String(50), nullable=True)
    # 模型版本号（描述性信息）
    # model_version = db.Column(db.String(20), nullable=True)
    # Git项目仓库地址，用于判断是否是同一个项目
    git_url = db.Column(db.Text, nullable=False)
    # 可选参数信息，用于描述该项目可以指定的参数（一段有着特定格式的JSON文本）
    optional_args = db.Column(db.Text, nullable=True)
    # 报警配置信息，用于描述该项目可以进行的报警配置（一段有着特定格式的JSON文本）
    alert_config = db.Column(db.Text, nullable=True)
    # 该项目的依赖是否正常被安装了（项目环境是否正常）
    env_ok = db.Column(db.Boolean, nullable=False)
    # 是否是默认AI算法（每个新设备都会被加上该默认的AI算法，应该保证只有一个default）
    default = db.Column(db.Boolean, nullable=False)

    # 模型库中该项目的ID（如果是在线创建的话）
    model_hub_id = db.Column(db.Integer, nullable=True)
