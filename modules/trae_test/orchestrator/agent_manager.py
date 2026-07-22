"""Agent知识挂载管理器 - 实现智能体对特定知识域的按需加载与管理"""

import json
import os
from datetime import datetime
from typing import Any

from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever


class AgentContext:
    """Agent专属知识上下文对象"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.loaded_domains = []
        self.context_summary = ""
        self.recent_access = []
        self.last_access_time = None
        self.domain_stats = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "loaded_domains": self.loaded_domains,
            "context_summary": self.context_summary,
            "recent_access": self.recent_access,
            "last_access_time": self.last_access_time.isoformat() if self.last_access_time else None,
            "domain_stats": self.domain_stats,
        }


class DomainMetadata:
    """知识域元数据"""

    def __init__(
        self,
        domain_id: str,
        description: str = "",
        chunks: list[str] = None,
        priority: str = "medium",
        refresh_strategy: str = "daily",
    ):
        self.domain_id = domain_id
        self.description = description
        self.chunks = chunks or []
        self.priority = priority
        self.refresh_strategy = refresh_strategy
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.access_count = 0
        self.hit_count = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "description": self.description,
            "chunks": self.chunks,
            "priority": self.priority,
            "refresh_strategy": self.refresh_strategy,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
            "hit_count": self.hit_count,
        }


class AgentManager:
    """Agent知识挂载管理器"""

    def __init__(self):
        self.knowledge_base_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "knowledge_base")
        )

        # 配置目录
        self.agents_config_dir = os.path.join(self.knowledge_base_dir, "agents")
        self.domains_dir = os.path.join(self.knowledge_base_dir, "domains")

        # 文件路径
        self.domains_metadata_path = os.path.join(self.domains_dir, "domain_metadata.json")

        # 初始化知识检索器
        self.retriever = KnowledgeRetriever()

        # 内存缓存
        self._agent_contexts: dict[str, AgentContext] = {}
        self._domain_metadata: dict[str, DomainMetadata] = {}
        self._domain_cache: dict[str, Any] = {}

        # 确保目录存在
        os.makedirs(self.agents_config_dir, exist_ok=True)
        os.makedirs(self.domains_dir, exist_ok=True)

        # 加载知识域元数据
        self._load_domain_metadata()

    def _load_domain_metadata(self):
        """加载知识域元数据"""
        if os.path.exists(self.domains_metadata_path):
            try:
                with open(self.domains_metadata_path, encoding="utf-8") as f:
                    data = json.load(f)
                    for domain_id, domain_data in data.get("domains", {}).items():
                        domain = DomainMetadata(
                            domain_id=domain_id,
                            description=domain_data.get("description", ""),
                            chunks=domain_data.get("chunks", []),
                            priority=domain_data.get("priority", "medium"),
                            refresh_strategy=domain_data.get("refresh_strategy", "daily"),
                        )
                        domain.access_count = domain_data.get("access_count", 0)
                        domain.hit_count = domain_data.get("hit_count", 0)
                        self._domain_metadata[domain_id] = domain
            except Exception as e:
                print(f"[AgentManager] 加载知识域元数据失败: {e}")

    def _save_domain_metadata(self):
        """保存知识域元数据"""
        data = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "domains": {domain_id: domain.to_dict() for domain_id, domain in self._domain_metadata.items()},
        }
        with open(self.domains_metadata_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_agent_knowledge_domains(self, agent_id: str) -> list[str]:
        """加载指定Agent的知识域配置

        Args:
            agent_id: Agent ID

        Returns:
            知识域ID列表
        """
        config_path = os.path.join(self.agents_config_dir, f"{agent_id}.json")

        if os.path.exists(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("knowledge_domains", [])
            except Exception as e:
                print(f"[AgentManager] 加载Agent配置失败 {agent_id}: {e}")

        # 如果没有配置文件，尝试从AGENTS.md读取
        return self._load_domains_from_md(agent_id)

    def _load_domains_from_md(self, agent_id: str) -> list[str]:
        """从AGENTS.md加载知识域配置"""
        md_path = os.path.join(self.agents_config_dir, "agents.md")
        domains = []

        if os.path.exists(md_path):
            try:
                with open(md_path, encoding="utf-8") as f:
                    content = f.read()
                    import re

                    # 查找特定agent的配置块
                    agent_pattern = rf"agent_id:\s*{agent_id}\s*[\s\S]*?(?=\n## |\Z)"
                    agent_match = re.search(agent_pattern, content)
                    if agent_match:
                        agent_config = agent_match.group(0)

                        # 提取knowledge_domains部分
                        domains_pattern = r"knowledge_domains:\s*\n([\s\S]*?)(?=\n\S|$)"
                        domains_match = re.search(domains_pattern, agent_config)
                        if domains_match:
                            domains_section = domains_match.group(1)

                            # 解析YAML格式的domain列表
                            domain_lines = domains_section.strip().split("\n")
                            for line in domain_lines:
                                line = line.strip()
                                if line.startswith("-"):
                                    domain_id_match = re.search(r"domain_id:\s*(\S+)", line)
                                    if domain_id_match:
                                        domains.append(domain_id_match.group(1))
            except Exception as e:
                print(f"[AgentManager] 从MD加载配置失败: {e}")

        return domains

    def preload_domain_knowledge(self, domain_id: str) -> bool:
        """预加载特定知识域的业务规则切片至内存缓存

        Args:
            domain_id: 知识域ID

        Returns:
            是否加载成功
        """
        if domain_id in self._domain_cache:
            return True

        # 获取知识域配置
        domain = self._domain_metadata.get(domain_id)
        if not domain:
            print(f"[AgentManager] 知识域不存在: {domain_id}")
            return False

        # 通过KnowledgeRetriever检索相关chunk
        try:
            # 使用倒排索引检索该域相关的知识
            results = self.retriever.search_by_inverted_index(domain_id, top_k=50)

            # 缓存结果
            self._domain_cache[domain_id] = {
                "loaded_at": datetime.now(),
                "chunk_count": len(results),
                "chunks": results,
                "domain_metadata": domain.to_dict(),
            }

            # 更新访问统计
            domain.access_count += 1
            domain.updated_at = datetime.now()
            self._save_domain_metadata()

            print(f"[AgentManager] 知识域 {domain_id} 已预加载，包含 {len(results)} 个chunk")
            return True

        except Exception as e:
            print(f"[AgentManager] 预加载知识域失败 {domain_id}: {e}")
            return False

    def unload_unused_domains(self, agent_id: str, ttl: int = 3600):
        """自动卸载超过指定时间未使用的知识域

        Args:
            agent_id: Agent ID
            ttl: 超时时间（秒），默认1小时
        """
        context = self._agent_contexts.get(agent_id)
        if not context:
            return

        now = datetime.now()
        domains_to_unload = []

        for domain_id in context.loaded_domains:
            cache_entry = self._domain_cache.get(domain_id)
            if cache_entry:
                loaded_at = cache_entry.get("loaded_at")
                if isinstance(loaded_at, str):
                    loaded_at = datetime.fromisoformat(loaded_at)
                if (now - loaded_at).total_seconds() > ttl:
                    domains_to_unload.append(domain_id)

        for domain_id in domains_to_unload:
            del self._domain_cache[domain_id]
            context.loaded_domains.remove(domain_id)
            print(f"[AgentManager] 已卸载知识域 {domain_id} (Agent: {agent_id})")

    def get_agent_context(self, agent_id: str) -> AgentContext:
        """返回Agent专属知识上下文对象

        Args:
            agent_id: Agent ID

        Returns:
            Agent上下文对象
        """
        if agent_id not in self._agent_contexts:
            self._agent_contexts[agent_id] = AgentContext(agent_id)

        context = self._agent_contexts[agent_id]
        context.last_access_time = datetime.now()

        return context

    def add_domain(
        self,
        domain_id: str,
        description: str = "",
        chunks: list[str] = None,
        priority: str = "medium",
        refresh_strategy: str = "daily",
    ) -> bool:
        """添加知识域

        Args:
            domain_id: 知识域ID
            description: 描述
            chunks: 包含的chunk列表
            priority: 优先级
            refresh_strategy: 刷新策略

        Returns:
            是否添加成功
        """
        if domain_id in self._domain_metadata:
            print(f"[AgentManager] 知识域已存在: {domain_id}")
            return False

        self._domain_metadata[domain_id] = DomainMetadata(
            domain_id=domain_id,
            description=description,
            chunks=chunks or [],
            priority=priority,
            refresh_strategy=refresh_strategy,
        )

        self._save_domain_metadata()
        print(f"[AgentManager] 已添加知识域: {domain_id}")
        return True

    def remove_domain(self, domain_id: str) -> bool:
        """移除知识域

        Args:
            domain_id: 知识域ID

        Returns:
            是否移除成功
        """
        if domain_id not in self._domain_metadata:
            print(f"[AgentManager] 知识域不存在: {domain_id}")
            return False

        del self._domain_metadata[domain_id]

        # 从缓存中移除
        if domain_id in self._domain_cache:
            del self._domain_cache[domain_id]

        # 从所有agent的上下文移除
        for context in self._agent_contexts.values():
            if domain_id in context.loaded_domains:
                context.loaded_domains.remove(domain_id)

        self._save_domain_metadata()
        print(f"[AgentManager] 已移除知识域: {domain_id}")
        return True

    def record_domain_access(self, domain_id: str, hit: bool = False):
        """记录知识域访问统计

        Args:
            domain_id: 知识域ID
            hit: 是否命中
        """
        domain = self._domain_metadata.get(domain_id)
        if domain:
            domain.access_count += 1
            if hit:
                domain.hit_count += 1
            domain.updated_at = datetime.now()
            self._save_domain_metadata()

    def get_domain_stats(self, domain_id: str = None) -> dict[str, Any]:
        """获取知识域统计信息

        Args:
            domain_id: 知识域ID，为空则返回所有域的统计

        Returns:
            统计信息
        """
        if domain_id:
            domain = self._domain_metadata.get(domain_id)
            if domain:
                return domain.to_dict()
            return {}

        return {domain_id: domain.to_dict() for domain_id, domain in self._domain_metadata.items()}

    def initialize_agent(self, agent_id: str) -> bool:
        """初始化Agent的知识域加载

        Args:
            agent_id: Agent ID

        Returns:
            是否初始化成功
        """
        context = self.get_agent_context(agent_id)
        domains = self.load_agent_knowledge_domains(agent_id)

        success_count = 0
        for domain_id in domains:
            if self.preload_domain_knowledge(domain_id):
                context.loaded_domains.append(domain_id)
                success_count += 1

        context.context_summary = f"已加载 {success_count}/{len(domains)} 个知识域"
        print(f"[AgentManager] Agent {agent_id} 初始化完成，加载 {success_count} 个知识域")

        return success_count > 0


if __name__ == "__main__":
    print("=" * 60)
    print("AgentManager - 知识挂载管理器测试")
    print("=" * 60)

    manager = AgentManager()

    # 添加测试知识域
    print("\n1. 添加测试知识域...")
    manager.add_domain("sales-order-rules", description="销售订单业务规则", priority="high", refresh_strategy="daily")
    manager.add_domain(
        "purchase-order-rules", description="采购订单业务规则", priority="medium", refresh_strategy="weekly"
    )

    # 初始化Agent
    print("\n2. 初始化case-agent...")
    manager.initialize_agent("case-agent")

    # 获取Agent上下文
    print("\n3. 获取Agent上下文...")
    context = manager.get_agent_context("case-agent")
    print(f"   Agent ID: {context.agent_id}")
    print(f"   已加载域: {context.loaded_domains}")
    print(f"   上下文摘要: {context.context_summary}")

    # 获取知识域统计
    print("\n4. 知识域统计...")
    stats = manager.get_domain_stats()
    for domain_id, data in stats.items():
        print(f"   {domain_id}: 访问次数={data['access_count']}, 命中次数={data['hit_count']}")

    print("\n✅ 测试完成！")
