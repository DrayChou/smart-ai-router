#!/usr/bin/env python3
"""
豆包定价抓取任务（增强版本）
通过Jina.ai从豆包官网抓取模型信息和定价数据
重点修复：1. 预处理Markdown提取表格 2. 支持深度思考模型和大语言模型双表格解析 3. 正确提取模型规格
"""

import re
import json
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import httpx

logger = logging.getLogger(__name__)

@dataclass
class DoubaoModelInfo:
    """豆包模型信息数据类"""
    model_name: str
    display_name: str
    parameter_count: Optional[str] = None  # 参数量（如：7B、32B）
    context_length: Optional[str] = None    # 上下文长度（如：32K、128K）
    max_input_length: Optional[str] = None  # 最大输入长度
    max_output_length: Optional[str] = None # 最大输出长度
    input_price: float = 0.0  # 输入价格 元/百万token
    output_price: float = 0.0  # 输出价格 元/百万token
    input_length_range: Optional[str] = None  # 输入长度条件（深度思考模型）
    description: str = ""
    model_type: str = "chat"
    pricing_source: str = "unknown"  # 定价来源：deep_thinking 或 large_language
    last_updated: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "model_name": self.model_name,
            "display_name": self.display_name,
            "parameter_count": self.parameter_count,
            "context_length": self.context_length,
            "max_input_length": self.max_input_length,
            "max_output_length": self.max_output_length,
            "input_price": self.input_price,
            "output_price": self.output_price,
            "input_length_range": self.input_length_range,
            "description": self.description,
            "model_type": self.model_type,
            "pricing_source": self.pricing_source,
            "last_updated": self.last_updated or datetime.now().isoformat()
        }


class DoubaoEnhancedPricingTask:
    """豆包定价抓取任务（增强版本）- 表格预处理 + 双定价表解析"""
    
    def __init__(self):
        self.base_dir = Path("cache")
        self.cache_dir = self.base_dir
        self.debug_dir = self.base_dir / "doubao_debug"
        
        # 确保目录存在
        self.cache_dir.mkdir(exist_ok=True)
        self.debug_dir.mkdir(exist_ok=True)
        
        # Jina.ai 配置
        self.jina_base_url = "https://r.jina.ai"
        self.jina_token = "jina_xxx"  # 可以为空，使用免费服务
        
        # 豆包文档URL
        self.doubao_urls = [
            "https://www.volcengine.com/docs/82379/1330310",  # 模型列表（规格信息）
            "https://www.volcengine.com/docs/82379/1544106"   # 模型服务价格
        ]
        
        # 缓存文件路径
        self.markdown_cache_file = self.debug_dir / "enhanced_doubao_docs.md"
        self.tables_cache_file = self.debug_dir / "extracted_tables.json"
        self.parsed_data_file = self.debug_dir / "enhanced_parsed_data.json"
        self.pricing_cache_file = self.cache_dir / "doubao_pricing.json"
        
        # 缓存的模型数据
        self.cached_models: Dict[str, DoubaoModelInfo] = {}
        self.last_update: Optional[datetime] = None
        
        # 加载缓存数据
        self._load_cached_data()
    
    def _load_cached_data(self):
        """加载缓存的数据"""
        try:
            if self.pricing_cache_file.exists():
                with open(self.pricing_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for model_name, model_data in data.get('models', {}).items():
                    self.cached_models[model_name] = DoubaoModelInfo(**model_data)
                
                if data.get('last_update'):
                    self.last_update = datetime.fromisoformat(data['last_update'])
                    
                logger.info(f"已加载豆包模型缓存: {len(self.cached_models)} 个模型")
        except Exception as e:
            logger.debug(f"加载豆包缓存失败: {e}")
    
    def should_update(self) -> bool:
        """检查是否需要更新缓存"""
        if not self.last_update:
            return True
        
        # 24小时更新一次
        from datetime import timedelta
        return datetime.now() - self.last_update > timedelta(hours=24)
    
    async def scrape_docs_via_jina(self) -> Dict[str, DoubaoModelInfo]:
        """通过Jina.ai抓取豆包文档"""
        try:
            logger.info("开始通过Jina.ai抓取豆包文档...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/markdown,text/plain,*/*',
                'X-Retain-Images': 'none',
                'X-Return-Format': 'markdown'
            }
            
            # 如果有Jina token，添加认证头
            if self.jina_token and self.jina_token != "jina_xxx":
                headers['Authorization'] = f'Bearer {self.jina_token}'
            
            all_content = ""
            
            async with httpx.AsyncClient(timeout=60) as client:
                for i, url in enumerate(self.doubao_urls, 1):
                    logger.info(f"正在抓取文档 {i}/{len(self.doubao_urls)}: {url}")
                    
                    jina_url = f"{self.jina_base_url}/{url}"
                    response = await client.get(jina_url, headers=headers)
                    response.raise_for_status()
                    
                    content = response.text
                    logger.info(f"成功获取文档内容，长度: {len(content)} 字符")
                    
                    # 添加文档分隔标记
                    all_content += f"\n\n# === 文档来源: {url} ===\n\n{content}\n\n"
            
            # 保存原始markdown内容
            with open(self.markdown_cache_file, 'w', encoding='utf-8') as f:
                f.write(all_content)
            logger.info(f"Markdown内容已保存到: {self.markdown_cache_file}")
            
            # **关键改进：预处理Markdown提取表格**
            logger.info("开始预处理Markdown内容，提取表格...")
            tables_data = self._preprocess_markdown_extract_tables(all_content)
            
            # 解析提取的表格获取模型信息
            logger.info("开始解析提取的表格获取模型信息...")
            models_dict = self._parse_extracted_tables(tables_data)
            
            return models_dict
            
        except Exception as e:
            logger.error(f"Jina.ai抓取失败: {e}")
            raise
    
    def _preprocess_markdown_extract_tables(self, content: str) -> Dict[str, Any]:
        """预处理Markdown内容，提取所有表格和相关上下文"""
        tables_data = {
            "spec_page_tables": [],  # 规格页面表格
            "pricing_page_tables": [],  # 定价页面表格
            "extracted_at": datetime.now().isoformat()
        }
        
        # 分别处理两个页面
        spec_content = self._extract_document_section(content, "1330310")
        pricing_content = self._extract_document_section(content, "1544106")
        
        # 提取规格页面表格
        if spec_content:
            spec_tables = self._extract_tables_from_content(spec_content, "spec_page")
            tables_data["spec_page_tables"] = spec_tables
            logger.info(f"规格页面提取到 {len(spec_tables)} 个表格")
        
        # 提取定价页面表格
        if pricing_content:
            pricing_tables = self._extract_tables_from_content(pricing_content, "pricing_page")
            tables_data["pricing_page_tables"] = pricing_tables
            logger.info(f"定价页面提取到 {len(pricing_tables)} 个表格")
        
        # 保存提取的表格
        with open(self.tables_cache_file, 'w', encoding='utf-8') as f:
            json.dump(tables_data, f, ensure_ascii=False, indent=2)
        logger.info(f"表格数据已保存到: {self.tables_cache_file}")
        
        return tables_data
    
    def _extract_tables_from_content(self, content: str, page_type: str) -> List[Dict[str, Any]]:
        """从内容中提取所有表格及其上下文"""
        tables = []
        lines = content.split('\n')
        
        current_table = None
        current_context = []  # 表格前的上下文行
        
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            
            # 检测表格开始
            if '|' in stripped_line and len(stripped_line.split('|')) >= 3:
                if current_table is None:
                    # 新表格开始
                    current_table = {
                        "context_before": current_context[-10:],  # 保留前10行上下文
                        "headers": [],
                        "rows": [],
                        "context_after": [],
                        "table_index": len(tables),
                        "page_type": page_type
                    }
                    current_context = []
                
                # 解析表格行
                cells = [cell.strip() for cell in stripped_line.split('|') if cell.strip()]
                if len(cells) >= 2:  # 至少2列
                    # 检测是否为表头或分隔行
                    if all('---' in cell or '-' * 3 in cell for cell in cells):
                        continue  # 跳过分隔行
                    elif not current_table["headers"] and any(
                        keyword in '|'.join(cells).lower() 
                        for keyword in ['模型', 'model', '名称', 'name', '价格', 'price', '计费']
                    ):
                        current_table["headers"] = cells
                    else:
                        current_table["rows"].append(cells)
            else:
                # 非表格行
                if current_table is not None:
                    # 表格可能结束了，先收集后续上下文
                    current_table["context_after"].append(stripped_line)
                    
                    # 如果连续3行都不是表格，认为表格结束
                    if len(current_table["context_after"]) >= 3 and all(
                        '|' not in context_line for context_line in current_table["context_after"][-3:]
                    ):
                        # 保存当前表格
                        if current_table["rows"]:  # 只保存有数据的表格
                            tables.append(current_table)
                        current_table = None
                else:
                    current_context.append(stripped_line)
        
        # 处理最后一个表格
        if current_table is not None and current_table["rows"]:
            tables.append(current_table)
        
        return tables
    
    def _parse_extracted_tables(self, tables_data: Dict[str, Any]) -> Dict[str, DoubaoModelInfo]:
        """解析提取的表格获取模型信息"""
        models_dict = {}
        
        # 解析规格页面表格
        spec_models = self._parse_spec_tables(tables_data.get("spec_page_tables", []))
        models_dict.update(spec_models)
        
        # 解析定价页面表格
        pricing_models = self._parse_pricing_tables(tables_data.get("pricing_page_tables", []))
        
        # 合并定价信息到已有模型，或创建新模型
        for model_name, pricing_info in pricing_models.items():
            if model_name in models_dict:
                # 更新现有模型的价格信息
                models_dict[model_name].input_price = pricing_info.input_price
                models_dict[model_name].output_price = pricing_info.output_price
                models_dict[model_name].input_length_range = pricing_info.input_length_range
                models_dict[model_name].pricing_source = pricing_info.pricing_source
            else:
                # 创建新模型（仅有定价信息）
                models_dict[model_name] = pricing_info
        
        logger.info(f"总共解析出 {len(models_dict)} 个豆包模型")
        
        # 保存调试数据
        debug_data = {
            "timestamp": datetime.now().isoformat(),
            "tables_count": len(tables_data.get("spec_page_tables", [])) + len(tables_data.get("pricing_page_tables", [])),
            "models_found": len(models_dict),
            "scraped_urls": self.doubao_urls,
            "parsed_models": [model.to_dict() for model in models_dict.values()]
        }
        
        with open(self.parsed_data_file, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        
        return models_dict
    
    def _parse_spec_tables(self, spec_tables: List[Dict[str, Any]]) -> Dict[str, DoubaoModelInfo]:
        """解析规格页面表格，提取模型规格信息"""
        models_dict = {}
        
        for table in spec_tables:
            # 根据上下文判断是否为模型规格表格
            context_text = ' '.join(table.get("context_before", []) + table.get("context_after", []))
            
            if any(keyword in context_text for keyword in ["文本生成", "对话", "Chat", "模型规格", "参数量", "上下文"]):
                logger.debug("发现模型规格表格")
                
                headers = table.get("headers", [])
                rows = table.get("rows", [])
                
                # 尝试识别列索引
                model_name_col = self._find_column_index(headers, ["模型", "model", "名称"])
                context_length_col = self._find_column_index(headers, ["上下文", "context", "最大"])
                param_count_col = self._find_column_index(headers, ["参数", "param", "大小"])
                
                for row in rows:
                    if len(row) <= max(model_name_col or 0, context_length_col or 0, param_count_col or 0):
                        continue
                    
                    # 提取模型名称
                    if model_name_col is not None and model_name_col < len(row):
                        raw_model_name = row[model_name_col]
                        model_name = self._clean_model_name(raw_model_name)
                        
                        if model_name and self._is_valid_model_name(model_name):
                            # 提取规格信息
                            context_length = None
                            if context_length_col is not None and context_length_col < len(row):
                                context_length = self._extract_context_length(row[context_length_col])
                            
                            param_count = None
                            if param_count_col is not None and param_count_col < len(row):
                                param_count = self._extract_param_count(row[param_count_col])
                            
                            models_dict[model_name] = DoubaoModelInfo(
                                model_name=model_name,
                                display_name=model_name,
                                context_length=context_length,
                                parameter_count=param_count,
                                description="从豆包模型规格表提取"
                            )
        
        logger.info(f"从规格表格解析出 {len(models_dict)} 个模型")
        return models_dict
    
    def _parse_pricing_tables(self, pricing_tables: List[Dict[str, Any]]) -> Dict[str, DoubaoModelInfo]:
        """解析定价页面表格，提取价格信息"""
        models_dict = {}
        
        for table in pricing_tables:
            context_text = ' '.join(table.get("context_before", []) + table.get("context_after", []))
            headers = table.get("headers", [])
            rows = table.get("rows", [])
            
            # 判断是否为定价表格
            is_pricing_table = any(keyword in context_text or any(keyword in h for h in headers) 
                                 for keyword in ["计费", "定价", "价格", "单价", "元/", "/token"])
            
            if not is_pricing_table:
                continue
            
            # 更精确的表格分类
            is_deep_thinking = ("深度思考模型" in context_text or 
                              any("输入长度" in str(row) and ("[" in str(row) or "]" in str(row)) for row in rows))
            is_large_language = "大语言模型" in context_text
            
            # 如果两个都不是，但是是定价表格，根据内容推断
            if not is_deep_thinking and not is_large_language:
                # 检查是否有条件定价（深度思考模型特征）
                has_conditional_pricing = any(
                    "输入长度" in str(row) or "[" in str(row) or "条件" in str(row) 
                    for row in rows
                )
                if has_conditional_pricing:
                    is_deep_thinking = True
                else:
                    is_large_language = True
            
            pricing_source = "deep_thinking" if is_deep_thinking else "large_language"
            logger.debug(f"发现{'深度思考模型' if is_deep_thinking else '大语言模型'}定价表格，行数: {len(rows)}")
            
            # 识别列索引
            model_name_col = self._find_column_index(headers, ["模型", "model", "名称"])
            input_price_col = self._find_column_index(headers, ["输入", "input", "prompt"])
            output_price_col = self._find_column_index(headers, ["输出", "output", "completion"])
            condition_col = self._find_column_index(headers, ["条件", "长度"])
            
            # 处理特殊的条件定价表格（深度思考模型）
            if is_deep_thinking and any("输入长度" in str(row) for row in rows):
                models_dict.update(self._parse_conditional_pricing_table(rows, headers, pricing_source))
            else:
                # 处理普通定价表格
                for row in rows:
                    if len(row) < 2:
                        continue
                    
                    # 提取模型名称
                    raw_model_name = ""
                    if model_name_col is not None and model_name_col < len(row):
                        raw_model_name = row[model_name_col]
                    elif len(row) > 0:
                        raw_model_name = row[0]
                    
                    model_name = self._clean_model_name(raw_model_name)
                    if not model_name or not self._is_valid_model_name(model_name):
                        continue
                    
                    # 提取价格信息
                    input_price = self._extract_price(
                        row[input_price_col] if input_price_col is not None and input_price_col < len(row) else ""
                    )
                    output_price = self._extract_price(
                        row[output_price_col] if output_price_col is not None and output_price_col < len(row) else (row[-1] if row else "")
                    )
                    
                    # 如果没有找到价格，尝试从其他列提取
                    if input_price == 0 and output_price == 0:
                        for cell in row[1:]:  # 跳过第一列（模型名称）
                            price = self._extract_price(cell)
                            if price > 0:
                                if input_price == 0:
                                    input_price = price
                                elif output_price == 0:
                                    output_price = price
                                    break
                    
                    models_dict[model_name] = DoubaoModelInfo(
                        model_name=model_name,
                        display_name=model_name,
                        input_price=input_price,
                        output_price=output_price,
                        pricing_source=pricing_source,
                        description=f"从豆包{'深度思考模型' if is_deep_thinking else '大语言模型'}定价表提取"
                    )
                    
                    logger.debug(f"定价解析: {model_name} ({pricing_source}) -> 输入:{input_price}, 输出:{output_price}")
        
        logger.info(f"从定价表格解析出 {len(models_dict)} 个模型")
        return models_dict
    
    def _parse_conditional_pricing_table(self, rows: List[List[str]], headers: List[str], pricing_source: str) -> Dict[str, DoubaoModelInfo]:
        """解析条件定价表格（深度思考模型特有）"""
        models_dict = {}
        current_model = None
        
        for row in rows:
            if len(row) < 3:
                continue
            
            # 检查第一列是否为模型名称
            first_cell = row[0].strip()
            if not first_cell.startswith("输入长度") and not first_cell.startswith("条件"):
                # 这是一个新的模型行
                model_name = self._clean_model_name(first_cell)
                if model_name and self._is_valid_model_name(model_name):
                    current_model = model_name
                    # 提取基础价格（如果有）
                    input_price = self._extract_price(row[2] if len(row) > 2 else "")
                    output_price = self._extract_price(row[-1] if row else "")
                    
                    models_dict[model_name] = DoubaoModelInfo(
                        model_name=model_name,
                        display_name=model_name,
                        input_price=input_price,
                        output_price=output_price,
                        pricing_source=pricing_source,
                        description=f"从豆包深度思考模型定价表提取"
                    )
                    logger.debug(f"条件定价解析: {model_name} -> 输入:{input_price}, 输出:{output_price}")
            else:
                # 这是一个条件行，应该属于当前模型
                if current_model and current_model in models_dict:
                    condition = first_cell
                    input_price = self._extract_price(row[1] if len(row) > 1 else "")
                    output_price = self._extract_price(row[-1] if row else "")
                    
                    # 使用第一个条件的价格作为模型的基础价格
                    if models_dict[current_model].input_price == 0:
                        models_dict[current_model].input_price = input_price
                    if models_dict[current_model].output_price == 0:
                        models_dict[current_model].output_price = output_price
                    
                    models_dict[current_model].input_length_range = condition
                    logger.debug(f"条件定价更新: {current_model} 条件:{condition} -> 输入:{input_price}, 输出:{output_price}")
        
        return models_dict
    
    def _find_column_index(self, headers: List[str], keywords: List[str]) -> Optional[int]:
        """查找包含关键词的列索引"""
        for i, header in enumerate(headers):
            header_lower = header.lower()
            if any(keyword.lower() in header_lower for keyword in keywords):
                return i
        return None
    
    def _extract_price(self, price_text: str) -> float:
        """从文本中提取价格数值"""
        if not price_text:
            return 0.0
        
        # 移除常见的非数字字符
        clean_text = price_text.replace(',', '').replace('，', '').replace('元', '').replace('￥', '')
        
        # 提取数字
        price_match = re.search(r'(\d+\.?\d*)', clean_text)
        if price_match:
            return float(price_match.group(1))
        
        return 0.0
    
    def _extract_context_length(self, context_text: str) -> Optional[str]:
        """提取上下文长度"""
        if not context_text:
            return None
        
        # 查找K、M等单位
        length_match = re.search(r'(\d+\.?\d*\s*[KkMm])', context_text)
        if length_match:
            return length_match.group(1).replace(' ', '')
        
        # 查找纯数字
        num_match = re.search(r'(\d+)', context_text)
        if num_match:
            return num_match.group(1)
        
        return None
    
    def _extract_param_count(self, param_text: str) -> Optional[str]:
        """提取参数数量"""
        if not param_text:
            return None
        
        # 查找B、M等单位
        param_match = re.search(r'(\d+\.?\d*\s*[BbMm])', param_text)
        if param_match:
            return param_match.group(1).replace(' ', '')
        
        return None
    
    def _extract_document_section(self, content: str, doc_id: str) -> str:
        """提取指定文档部分的内容"""
        start_marker = f"=== 文档来源: https://www.volcengine.com/docs/82379/{doc_id} ==="
        next_marker = "=== 文档来源:"
        
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.debug(f"未找到文档标记: {doc_id}")
            return ""
        
        # 找到下一个文档标记的位置
        next_pos = content.find(next_marker, start_pos + len(start_marker))
        
        if next_pos == -1:
            # 如果没有找到下一个标记，取到结尾
            result = content[start_pos:]
        else:
            # 提取当前文档部分
            result = content[start_pos:next_pos]
        
        logger.debug(f"提取文档 {doc_id} 内容长度: {len(result)}")
        return result
    
    def _clean_model_name(self, raw_name: str) -> str:
        """清理模型名称，移除版本号和链接"""
        if not raw_name:
            return ""
        
        # 移除markdown链接格式 [name](url)
        link_match = re.match(r'\[([^\]]+)\]', raw_name)
        if link_match:
            raw_name = link_match.group(1)
        
        # 移除时间戳版本号 (如: -250115, -241215等)
        clean_name = re.sub(r'-\d{6}$', '', raw_name)
        
        # 移除其他版本标识和说明
        clean_name = re.sub(r'\s+包括分支版本.*$', '', clean_name)
        clean_name = re.sub(r'>\s*.*$', '', clean_name)  # 移除 > 后面的内容
        clean_name = re.sub(r'\s*\(.*?\)$', '', clean_name)  # 移除括号内容
        
        return clean_name.strip()
    
    def _is_valid_model_name(self, model_name: str) -> bool:
        """验证模型名称是否有效"""
        if not model_name or len(model_name) < 3:
            return False
        
        # 过滤明显的噪音数据
        if any(char in model_name for char in ['=', '?', '#', '%', '<', '>', '"', "'", '&', '\\']):
            return False
        
        # 验证是否包含豆包相关特征
        valid_keywords = [
            'doubao', '豆包', 'ep-', 'Doubao', 'deepseek', 'kimi'
        ]
        
        model_lower = model_name.lower()
        return any(keyword.lower() in model_lower for keyword in valid_keywords)
    
    async def update_pricing_data(self, force: bool = False) -> Dict[str, Any]:
        """更新定价数据"""
        if not force and not self.should_update():
            logger.info("豆包定价数据无需更新")
            return {
                "status": "skipped",
                "reason": "no_update_needed",
                "models_count": len(self.cached_models)
            }
        
        try:
            logger.info("开始更新豆包定价数据...")
            start_time = datetime.now()
            
            # 抓取最新数据
            models_dict = await self.scrape_docs_via_jina()
            
            if not models_dict:
                raise Exception("未抓取到任何模型数据")
            
            # 更新缓存
            self.cached_models = models_dict
            self.last_update = datetime.now()
            
            # 保存到缓存文件
            self._save_cached_data()
            
            # 计算统计信息
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 统计分析
            free_models = sum(1 for model in models_dict.values() if model.input_price == 0.0 and model.output_price == 0.0)
            deep_thinking_models = sum(1 for model in models_dict.values() if model.pricing_source == "deep_thinking")
            large_language_models = sum(1 for model in models_dict.values() if model.pricing_source == "large_language")
            
            result = {
                "status": "success",
                "models_count": len(models_dict),
                "execution_time": execution_time,
                "summary": {
                    "total": len(models_dict),
                    "free": free_models,
                    "paid": len(models_dict) - free_models,
                    "deep_thinking": deep_thinking_models,
                    "large_language": large_language_models,
                    "with_pricing": sum(1 for model in models_dict.values() if model.input_price > 0 or model.output_price > 0),
                    "with_specs": sum(1 for model in models_dict.values() if model.context_length or model.parameter_count)
                }
            }
            
            logger.info(f"豆包定价数据更新完成: {len(models_dict)} 个模型，用时 {execution_time:.2f}秒")
            logger.info(f"  - 深度思考模型: {deep_thinking_models} 个")
            logger.info(f"  - 大语言模型: {large_language_models} 个")
            logger.info(f"  - 含规格信息: {result['summary']['with_specs']} 个")
            return result
            
        except Exception as e:
            logger.error(f"更新豆包定价数据失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "models_count": len(self.cached_models)
            }
    
    def _save_cached_data(self):
        """保存缓存数据"""
        try:
            cache_data = {
                "last_update": self.last_update.isoformat() if self.last_update else None,
                "models": {name: model.to_dict() for name, model in self.cached_models.items()},
                "source": "doubao_enhanced_scraper",
                "total_models": len(self.cached_models),
                "scraped_urls": self.doubao_urls
            }
            
            with open(self.pricing_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"豆包模型缓存已保存: {len(self.cached_models)} 个模型")
            
        except Exception as e:
            logger.error(f"保存豆包缓存失败: {e}")
    
    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模型信息"""
        return {name: model.to_dict() for name, model in self.cached_models.items()}
    
    def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        if model_name in self.cached_models:
            model_info = self.cached_models[model_name]
            return {
                "prompt": str(model_info.input_price),
                "completion": str(model_info.output_price),
                "request": "0",
                "image": "0",
                "audio": "0",
                "web_search": "0",
                "internal_reasoning": "0"
            }
        return None


# 全局实例
_doubao_enhanced_task: Optional[DoubaoEnhancedPricingTask] = None

def get_doubao_enhanced_pricing_task() -> DoubaoEnhancedPricingTask:
    """获取豆包增强定价任务实例"""
    global _doubao_enhanced_task
    if _doubao_enhanced_task is None:
        _doubao_enhanced_task = DoubaoEnhancedPricingTask()
    return _doubao_enhanced_task

async def run_doubao_enhanced_pricing_update(force: bool = False) -> Dict[str, Any]:
    """运行豆包增强定价更新任务"""
    task = get_doubao_enhanced_pricing_task()
    return await task.update_pricing_data(force=force)


if __name__ == "__main__":
    # 测试代码
    async def test():
        print("测试豆包增强定价抓取（表格预处理版本）")
        result = await run_doubao_enhanced_pricing_update(force=True)
        print(f"结果: {result}")
        
        if result.get("status") == "success":
            task = get_doubao_enhanced_pricing_task()
            models = task.get_all_models()
            print(f"总模型数: {len(models)}")
            
            # 按定价来源分类显示
            deep_thinking = [name for name, info in models.items() if info.get('pricing_source') == 'deep_thinking']
            large_language = [name for name, info in models.items() if info.get('pricing_source') == 'large_language']
            
            print(f"深度思考模型: {len(deep_thinking)} 个")
            for name in deep_thinking[:3]:
                info = models[name]
                print(f"  - {name}: 输入{info.get('input_price')}, 输出{info.get('output_price')} (范围:{info.get('input_length_range', 'N/A')})")
            
            print(f"大语言模型: {len(large_language)} 个")
            for name in large_language[:3]:
                info = models[name]
                print(f"  - {name}: 输入{info.get('input_price')}, 输出{info.get('output_price')}")
            
            # 检查doubao-seed-1.6-vision是否修复
            if 'doubao-seed-1.6-vision' in models:
                vision_model = models['doubao-seed-1.6-vision']
                print(f"doubao-seed-1.6-vision检查: 输入{vision_model.get('input_price')}, 来源{vision_model.get('pricing_source')}")
    
    asyncio.run(test())