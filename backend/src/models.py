"""集中加载全部 ORM 模型，填充 SQLAlchemy mapper 注册表。

单一事实源：凡是需要"完整模型注册表"的地方都 import 本模块——
- alembic（autogenerate 需要 Base.metadata 含全部表，否则会误判缺失的表该 drop）；
- 任何一次性脚本 / REPL（ORM 查询编译时要解析 relationship 的字符串引用，
  必须先注册全部关联模型，否则报 "no mapped classes registered under ..."）。

新增模型只需在此登记一处。注意：这是"导入即注册"的副作用模块，import 顺序无关。
"""

from src.database import Base

# 显式导入全部 model 模块以触发 mapper 注册（与项目"显式 import"风格一致）。
import src.audit.models  # noqa: F401
import src.auth.models  # noqa: F401
import src.jobs.models  # noqa: F401
import src.knowledge_base.models  # noqa: F401
import src.news_media.analysis.models  # noqa: F401
import src.news_media.monitors.models  # noqa: F401
import src.news_media.tasks.models  # noqa: F401
import src.rbac.models  # noqa: F401
import src.research_agent.models  # noqa: F401
import src.social_media.analysis.models  # noqa: F401
import src.social_media.monitors.models  # noqa: F401
import src.social_media.tasks.models  # noqa: F401
import src.strategies.models  # noqa: F401

__all__ = ["Base"]
