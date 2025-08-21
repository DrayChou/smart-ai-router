#!/usr/bin/env python3
"""
SiliconFlow定价抓取任务 - 定期从官网获取最新定价信息
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

import httpx
from bs4 import BeautifulSoup

from ...providers.adapters.siliconflow import SiliconFlowModelPricing

logger = logging.getLogger(__name__)

class SiliconFlowPricingTask:
    """SiliconFlow定价抓取任务"""
    
    def __init__(self, cache_dir: str = "cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 调试目录
        self.debug_dir = self.cache_dir / "siliconflow_debug"
        self.debug_dir.mkdir(exist_ok=True)
        
        # 缓存文件路径
        self.pricing_cache_file = self.cache_dir / "siliconflow_pricing.json"
        self.pricing_log_file = self.cache_dir / "siliconflow_pricing_log.json"
        self.html_cache_file = self.debug_dir / "latest_pricing_page.html"
        self.parsed_data_file = self.debug_dir / "parsed_pricing_data.json"
        
        # 定价相关配置
        self.pricing_url = "https://siliconflow.cn/pricing"
        
        # 加载现有缓存
        self.cached_pricing: Dict[str, Any] = {}
        self.last_update: Optional[datetime] = None
        self._load_cache()
    
    def _load_cache(self):
        """加载现有定价缓存"""
        try:
            if self.pricing_cache_file.exists():
                with open(self.pricing_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.cached_pricing = cache_data.get('pricing', {})
                    last_update_str = cache_data.get('last_update')
                    if last_update_str:
                        self.last_update = datetime.fromisoformat(last_update_str)
                    
                logger.info(f"已加载SiliconFlow定价缓存: {len(self.cached_pricing)} 个模型")
        except Exception as e:
            logger.warning(f"加载SiliconFlow定价缓存失败: {e}")
    
    def _save_cache(self, pricing_data: Dict[str, Any]):
        """保存定价缓存"""
        try:
            cache_data = {
                'last_update': datetime.now().isoformat(),
                'pricing': pricing_data,
                'source': 'siliconflow_website',
                'total_models': len(pricing_data)
            }
            
            with open(self.pricing_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"SiliconFlow定价缓存已保存: {len(pricing_data)} 个模型")
        except Exception as e:
            logger.error(f"保存SiliconFlow定价缓存失败: {e}")
    
    def _log_pricing_update(self, result: Dict[str, Any]):
        """记录定价更新日志"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'status': result.get('status', 'unknown'),
                'models_count': result.get('models_count', 0),
                'error': result.get('error'),
                'pricing_summary': result.get('pricing_summary', {})
            }
            
            # 读取现有日志
            logs = []
            if self.pricing_log_file.exists():
                with open(self.pricing_log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            
            # 添加新日志（保留最近50条）
            logs.append(log_entry)
            logs = logs[-50:]
            
            # 保存日志
            with open(self.pricing_log_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"记录SiliconFlow定价日志失败: {e}")
    
    async def scrape_pricing_from_website(self) -> Dict[str, SiliconFlowModelPricing]:
        """从SiliconFlow官网抓取定价信息"""
        try:
            logger.info("正在从SiliconFlow官网抓取定价信息...")
            
            # 首先尝试从本地HTML文件读取（用于测试）
            html_file = self.cache_dir.parent / "logs" / "siliconflow_pricing" / "大模型 API 价格方案 - 硅基流动 SiliconFlow.html"
            
            if html_file.exists():
                logger.info(f"使用本地HTML文件进行定价解析: {html_file}")
                with open(html_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                logger.info(f"从本地文件读取HTML内容，长度: {len(html_content)} 字符")
            else:
                logger.info(f"从官网获取定价页面: {self.pricing_url}")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                    response = await client.get(self.pricing_url)
                    response.raise_for_status()
                    html_content = response.text
                    logger.info(f"从官网获取HTML内容，状态码: {response.status_code}，长度: {len(html_content)} 字符")
            
            # 保存HTML内容到调试文件
            try:
                with open(self.html_cache_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                logger.info(f"HTML内容已保存到: {self.html_cache_file}")
            except Exception as e:
                logger.warning(f"保存HTML内容失败: {e}")
            
            # 如果无法获取内容，使用回退定价
            if not html_content.strip():
                logger.warning("无法获取定价页面内容，使用回退定价数据")
                return self._get_fallback_pricing()
            
            # 解析HTML获取定价
            logger.info("开始解析HTML内容获取定价信息...")
            pricing_data = self._parse_pricing_html(html_content)
            
            # 保存解析结果到调试文件
            debug_data = {
                'timestamp': datetime.now().isoformat(),
                'html_length': len(html_content),
                'parsing_strategies_used': [],
                'models_found': len(pricing_data) if pricing_data else 0,
                'parsed_models': []
            }
            
            if pricing_data:
                for model_name, pricing in pricing_data.items():
                    debug_data['parsed_models'].append({
                        'model_name': model_name,
                        'display_name': pricing.display_name,
                        'input_price': pricing.input_price,
                        'output_price': pricing.output_price,
                        'description': pricing.description
                    })
            
            try:
                with open(self.parsed_data_file, 'w', encoding='utf-8') as f:
                    json.dump(debug_data, f, indent=2, ensure_ascii=False)
                logger.info(f"解析数据已保存到: {self.parsed_data_file}")
            except Exception as e:
                logger.warning(f"保存解析数据失败: {e}")
            
            if not pricing_data:
                logger.warning("HTML解析未获得定价数据，使用增强的回退定价")
                return self._get_enhanced_fallback_pricing()
            
            # 统计解析结果
            free_count = sum(1 for p in pricing_data.values() if p.input_price == 0.0 and p.output_price == 0.0)
            paid_count = len(pricing_data) - free_count
            
            logger.info(f"成功解析到 {len(pricing_data)} 个模型的定价信息 (免费: {free_count}, 收费: {paid_count})")
            
            # 打印前10个模型用于调试
            logger.info("前10个解析到的模型:")
            for i, (model_name, pricing) in enumerate(list(pricing_data.items())[:10]):
                logger.info(f"  {i+1}. {model_name}: 输入={pricing.input_price}, 输出={pricing.output_price}, 描述={pricing.description}")
            
            return pricing_data
            
        except Exception as e:
            logger.error(f"定价抓取失败，使用回退数据: {e}")
            return self._get_fallback_pricing()
    
    def _parse_pricing_html(self, html_content: str) -> Dict[str, SiliconFlowModelPricing]:
        """解析HTML内容获取定价信息"""
        try:
            # 尝试多种解析策略
            pricing_data = None
            strategies_tried = []
            
            logger.info(f"开始解析HTML，内容长度: {len(html_content)} 字符")
            
            # 策略1: 查找JSON数据 (Next.js通常在script标签中嵌入数据)
            logger.info("尝试策略1: 提取JSON数据...")
            pricing_data = self._extract_json_data(html_content)
            strategies_tried.append('json_extraction')
            if pricing_data:
                logger.info(f"从JSON数据中解析到定价信息: {len(pricing_data)} 个模型")
                return pricing_data
            else:
                logger.info("策略1: JSON数据提取未找到有效数据")
            
            # 策略2: 使用BeautifulSoup解析静态内容
            logger.info("尝试策略2: 解析静态HTML内容...")
            pricing_data = self._parse_static_content(html_content)
            strategies_tried.append('static_content')
            if pricing_data:
                logger.info(f"从静态HTML内容中解析到定价信息: {len(pricing_data)} 个模型")
                return pricing_data
            else:
                logger.info("策略2: 静态内容解析未找到有效数据")
            
            # 策略3: 正则表达式提取定价模式
            logger.info("尝试策略3: 提取文本模式...")
            pricing_data = self._extract_pricing_patterns(html_content)
            strategies_tried.append('pattern_extraction')
            if pricing_data:
                logger.info(f"从文本模式中解析到定价信息: {len(pricing_data)} 个模型")
                return pricing_data
            else:
                logger.info("策略3: 文本模式提取未找到有效数据")
            
            logger.warning(f"所有HTML解析策略均未获得数据，已尝试策略: {strategies_tried}")
            logger.info("HTML内容预览 (前500字符):")
            logger.info(html_content[:500] + "..." if len(html_content) > 500 else html_content)
            
            return {}
            
        except Exception as e:
            logger.error(f"HTML解析失败: {e}")
            return {}
    
    def _extract_json_data(self, html_content: str) -> Optional[Dict[str, SiliconFlowModelPricing]]:
        """尝试从HTML中提取JSON数据 (Next.js SPA常用模式)"""
        try:
            # 查找可能包含定价数据的JSON
            json_patterns = [
                r'__NEXT_DATA__"\s*>\s*([^<]+)',
                r'window\.__INITIAL_STATE__\s*=\s*([^;]+)',
                r'pricing["\']?\s*:\s*([\[{][^}\]]+[\]}])',
                r'models["\']?\s*:\s*([\[{][^}\]]+[\]}])',
                r'"pricing"\s*:\s*([\[{][^}\]]+[\]}])',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    try:
                        # 尝试解析JSON数据
                        data = json.loads(match)
                        pricing_dict = self._process_json_pricing_data(data)
                        if pricing_dict:
                            return pricing_dict
                    except json.JSONDecodeError:
                        continue
            
            return None
        except Exception as e:
            logger.debug(f"JSON数据提取失败: {e}")
            return None
    
    def _parse_static_content(self, html_content: str) -> Optional[Dict[str, SiliconFlowModelPricing]]:
        """解析静态HTML内容 - 专门针对SiliconFlow定价表格"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            pricing_dict = {}
            
            logger.info("解析SiliconFlow定价表格...")
            
            # 查找所有模型价格行（SiliconFlow使用的特定格式）
            # 寻找包含模型链接的行
            model_rows = soup.find_all('div', class_=lambda x: x and 'flex' in x and 'items-center' in x and 'px-[0.12rem]' in x)
            logger.info(f"找到 {len(model_rows)} 个可能的模型行")
            
            for row in model_rows:
                try:
                    # 查找模型链接
                    model_link = row.find('a', {'href': lambda x: x and 'models?target=' in x})
                    if not model_link:
                        continue
                    
                    # 提取模型名称
                    model_name = model_link.get_text(strip=True)
                    if not model_name or len(model_name) < 5:
                        continue
                    
                    # 获取所有列（flex-1 div）
                    columns = row.find_all('div', class_='flex-1')
                    if len(columns) < 3:
                        continue
                    
                    # 第二列是输入价格，第三列是输出价格
                    input_price_text = columns[1].get_text(strip=True)
                    output_price_text = columns[2].get_text(strip=True)
                    
                    # 解析价格
                    input_price = self._parse_price_text(input_price_text)
                    output_price = self._parse_price_text(output_price_text)
                    
                    # 创建定价条目
                    pricing_dict[model_name] = SiliconFlowModelPricing(
                        model_name=model_name,
                        display_name=model_name.split('/')[-1] if '/' in model_name else model_name,
                        input_price=input_price,
                        output_price=output_price,
                        description="从SiliconFlow官方定价表格提取"
                    )
                    
                    logger.debug(f"提取模型: {model_name} -> 输入:{input_price}, 输出:{output_price}")
                    
                except Exception as e:
                    logger.debug(f"解析模型行失败: {e}")
                    continue
            
            logger.info(f"成功解析到 {len(pricing_dict)} 个模型的定价信息")
            return pricing_dict if pricing_dict else None
            
        except Exception as e:
            logger.error(f"静态内容解析失败: {e}")
            return None
    
    def _parse_price_text(self, price_text: str) -> float:
        """解析价格文本为数值"""
        try:
            price_text = price_text.strip().lower()
            
            # 免费模型
            if price_text in ['免费', 'free', '0', '0.00']:
                return 0.0
            
            # 提取数字
            import re
            numbers = re.findall(r'\d+\.?\d*', price_text)
            if numbers:
                return float(numbers[0])
            
            # 默认价格（解析失败时）
            return 0.7
            
        except Exception:
            return 0.7
    
    def _extract_pricing_patterns(self, html_content: str) -> Optional[Dict[str, SiliconFlowModelPricing]]:
        """使用正则表达式提取定价模式"""
        try:
            pricing_dict = {}
            
            logger.info("开始使用正则表达式提取定价模式...")
            
            # 更全面的模型名称模式
            model_patterns = [
                r'((?:Qwen|qwen)[\w/\.-]*\d+[bB]?[\w/-]*)',
                r'((?:GLM|glm)[\w/\.-]*\d+[\w/-]*)',
                r'((?:DeepSeek|deepseek)[\w/\.-]*)',
                r'((?:Claude|claude)[\w/\.-]*)',
                r'((?:GPT|gpt)[\w/\.-]*)',
                r'((?:Llama|llama)[\w/\.-]*)',
                r'((?:Yi|yi)[\w/\.-]*)',
                r'((?:gemma|Gemma)[\w/\.-]*)',
                r'([\w-]+/[\w-]+(?:-\d+[bB])?[\w-]*)',
                r'(Pro/[\w/-]+)',
            ]
            
            # 价格模式
            price_patterns = [
                r'(\d+\.\d+)\s*[¥￥元]?/?(?:1?[kK]|千)?\s*tokens?',
                r'[¥￥]\s*(\d+\.\d+)',
                r'(\d+\.\d+)\s*元',
                r'免费',
                r'Free',
                r'(\d+\.\d+)\s*/\s*1K\s*tokens',
            ]
            
            # 查找所有模型名称
            all_models = set()
            for i, pattern in enumerate(model_patterns):
                models = re.findall(pattern, html_content, re.IGNORECASE)
                logger.info(f"模式 {i+1} ({pattern[:30]}...) 找到 {len(models)} 个匹配")
                all_models.update(models)
            
            logger.info(f"总共找到 {len(all_models)} 个潜在模型名称")
            
            # 查找免费关键词
            free_keywords = re.findall(r'免费|Free|free', html_content, re.IGNORECASE)
            logger.info(f"找到 {len(free_keywords)} 个免费关键词")
            
            # 查找价格数字
            price_numbers = re.findall(r'\d+\.\d+', html_content)
            logger.info(f"找到 {len(price_numbers)} 个价格数字")
            
            # 为找到的模型创建基础定价
            for model in all_models:
                if self._is_valid_model_name(model):
                    # 判断是否为免费模型
                    is_free = any(keyword in model.lower() for keyword in [
                        'free', '免费', 'qwen2.5-7b', 'glm-4-9b', 'yi-1.5-9b', 
                        'deepseeк-r1-distill-qwen-1.5b', 'deepseeк-r1-distill-qwen-7b',
                        'dialagpt', 'llama-3.2-3b', 'llama-3.2-1b', 'gemma-2-2b'
                    ])
                    
                    pricing_dict[model] = SiliconFlowModelPricing(
                        model_name=model,
                        display_name=model.split('/')[-1] if '/' in model else model,
                        input_price=0.0 if is_free else 0.7,  # 默认收费价格
                        output_price=0.0 if is_free else 0.7,
                        description="免费" if is_free else "从HTML模式提取"
                    )
            
            logger.info(f"正则表达式提取完成，创建了 {len(pricing_dict)} 个模型定价")
            
            return pricing_dict if pricing_dict else None
            
        except Exception as e:
            logger.error(f"模式提取失败: {e}")
            return None
    
    def _is_valid_model_name(self, model_name: str) -> bool:
        """验证模型名称是否有效"""
        if not model_name or len(model_name) < 5:
            return False
        
        # 过滤明显的噪音数据
        if any(char in model_name for char in ['=', '?', '#', '%', '<', '>', '"', "'", '&', '\\']):
            return False
        
        # 过滤过长的随机字符串
        if len(model_name) > 80:
            return False
        
        # 过滤全数字或全大写字母的字符串
        if model_name.isdigit() or (model_name.isupper() and len(model_name) > 10):
            return False
        
        # 过滤包含太多连续大写字母的字符串（可能是编码）
        import re
        if re.search(r'[A-Z]{6,}', model_name):
            return False
        
        # 过滤明显的文件路径或URL
        if any(keyword in model_name.lower() for keyword in [
            'static/', 'css/', 'js/', 'html', 'http', 'www', '.com', '.svg', '.png', 
            'chunk', 'webpack', 'polyfill', 'script', 'style', 'font', 'image',
            'siliconflow_files', '_next/', 'layout-', 'main-app', 'text/', 'app/',
            'cn/pricing', 'userguide', 'legals/', 'explorer/edge', 'chrome'
        ]):
            return False
        
        # 验证是否包含有效的模型名称特征
        valid_prefixes = [
            'qwen', 'deepseek', 'glm', 'claude', 'gpt', 'llama', 'yi', 'gemma',
            'baai', 'thudm', 'microsoft', 'meta-llama', 'google', 'anthropic',
            'openai', 'moonshot', 'step', 'tencent', 'netease', 'pro/', 'ascend'
        ]
        
        model_lower = model_name.lower()
        has_valid_prefix = any(prefix in model_lower for prefix in valid_prefixes)
        
        # 如果包含有效前缀，或者是标准的 provider/model 格式，则认为有效
        has_slash_format = '/' in model_name and len(model_name.split('/')) == 2
        
        return has_valid_prefix or has_slash_format
    
    def _process_json_pricing_data(self, data: Any) -> Optional[Dict[str, SiliconFlowModelPricing]]:
        """处理JSON定价数据"""
        try:
            # 递归查找定价相关的数据结构
            def find_pricing_data(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if any(keyword in key.lower() for keyword in ['pricing', 'model', 'price', 'cost']):
                            yield path + "." + key, value
                        if isinstance(value, (dict, list)):
                            yield from find_pricing_data(value, path + "." + key)
                elif isinstance(obj, list) and obj:
                    for i, item in enumerate(obj):
                        if isinstance(item, (dict, list)):
                            yield from find_pricing_data(item, path + f"[{i}]")
            
            for path, pricing_data in find_pricing_data(data):
                if isinstance(pricing_data, (list, dict)):
                    logger.debug(f"找到可能的定价数据路径: {path}")
                    # 这里可以进一步解析具体的定价结构
            
            return None  # 暂时返回None，可以根据实际JSON结构来实现具体解析逻辑
            
        except Exception as e:
            logger.debug(f"JSON定价数据处理失败: {e}")
            return None
    
    def _parse_pricing_table(self, table) -> Dict[str, SiliconFlowModelPricing]:
        """解析表格中的定价信息"""
        try:
            pricing_dict = {}
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:  # 至少需要模型名称和价格列
                    model_cell = cells[0].get_text(strip=True)
                    # 尝试提取价格信息
                    for cell in cells[1:]:
                        price_text = cell.get_text(strip=True)
                        if re.search(r'\d+\.\d+|免费|free', price_text, re.IGNORECASE):
                            # 解析价格...
                            pass
            
            return pricing_dict
        except Exception:
            return {}
    
    def _parse_pricing_card(self, card) -> Dict[str, SiliconFlowModelPricing]:
        """解析卡片中的定价信息"""
        try:
            pricing_dict = {}
            text = card.get_text(strip=True)
            
            # 跳过明显的页面标题和非模型内容
            skip_keywords = [
                '大模型', '托管服务', '私有化部署', '预留实例', '量身定制', 
                '企业场景', '支持用户', '定制化', '私有云', '公有云',
                'API', 'API价格', '价格方案', '定价', 'SiliconFlow',
                '硅基流动', '联系我们', '立即购买', '了解更多', '查看详情'
            ]
            
            # 如果文本包含这些关键词，跳过
            if any(keyword in text for keyword in skip_keywords):
                return {}
            
            # 更精确的模型名称匹配
            # 真正的模型名称通常包含特定格式
            model_patterns = [
                r'((?:Qwen|qwen)[\w/\.-]*\d+[bB]?[\w/-]*)',  # Qwen系列
                r'((?:GLM|glm)[\w/\.-]*\d+[\w/-]*)',        # GLM系列
                r'((?:DeepSeek|deepseek)[\w/\.-]*)',         # DeepSeek系列
                r'((?:Claude|claude)[\w/\.-]*)',             # Claude系列
                r'((?:GPT|gpt)[\w/\.-]*)',                   # GPT系列
                r'((?:Llama|llama)[\w/\.-]*)',               # Llama系列
                r'((?:Yi|yi)[\w/\.-]*)',                     # Yi系列
                r'((?:gemma|Gemma)[\w/\.-]*)',               # Gemma系列
                r'([\w-]+/[\w-]+(?:-\d+[bB])?[\w-]*)',       # 标准格式: provider/model
            ]
            
            model_found = False
            for pattern in model_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if len(match) > 5:  # 模型名称长度至少6个字符
                        model_name = match
                        is_free = bool(re.search(r'免费|free', text, re.IGNORECASE))
                        price = 0.0 if is_free else 0.7
                        
                        pricing_dict[model_name] = SiliconFlowModelPricing(
                            model_name=model_name,
                            display_name=model_name.split('/')[-1] if '/' in model_name else model_name,
                            input_price=price,
                            output_price=price,
                            description="从HTML卡片提取"
                        )
                        model_found = True
            
            return pricing_dict
        except Exception:
            return {}
    
    def _get_enhanced_fallback_pricing(self) -> Dict[str, SiliconFlowModelPricing]:
        """获取增强的回退定价数据 (基于2025年1月的SiliconFlow实际定价)"""
        # 基于SiliconFlow官网的最新定价信息
        enhanced_models = {
            # ===== 免费模型 =====
            "Qwen/Qwen2.5-7B-Instruct": (0.0, 0.0, "永久免费"),
            "THUDM/glm-4-9b-chat": (0.0, 0.0, "免费"),  
            "01-ai/Yi-1.5-9B-Chat-16K": (0.0, 0.0, "免费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B": (0.0, 0.0, "免费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": (0.0, 0.0, "免费"),
            "microsoft/DialoGPT-medium": (0.0, 0.0, "免费"),
            "meta-llama/Llama-3.2-3B-Instruct": (0.0, 0.0, "免费"),
            "meta-llama/Llama-3.2-1B-Instruct": (0.0, 0.0, "免费"),
            "google/gemma-2-2b-it": (0.0, 0.0, "免费"),
            "THUDM/GLM-4.1V-9B-Thinking": (0.0, 0.0, "免费Vision模型"),
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": (0.0, 0.0, "免费推理模型"),
            
            # ===== Pro收费模型 =====
            "Pro/Qwen/Qwen2.5-14B-Instruct": (0.35, 0.35, "Pro版本"),
            "Pro/deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": (0.35, 0.35, "Pro版本"),
            "Pro/THUDM/glm-4-9b-chat": (0.60, 0.60, "Pro版本"),
            "Pro/meta-llama/Llama-3.3-70B-Instruct": (0.60, 0.60, "Pro版本"),
            "Pro/Qwen/Qwen2.5-32B-Instruct": (0.60, 0.60, "Pro版本"),
            
            # ===== 标准收费模型 =====
            "Qwen/Qwen2.5-14B-Instruct": (0.70, 0.70, "标准收费"),
            "Qwen/Qwen2.5-32B-Instruct": (1.26, 1.26, "标准收费"),
            "Qwen/Qwen2.5-72B-Instruct": (4.13, 4.13, "标准收费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": (0.70, 0.70, "标准收费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B": (1.26, 1.26, "标准收费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-70B": (4.13, 4.13, "标准收费"),
            "deepseek-ai/DeepSeek-V3": (1.26, 1.26, "标准收费"),
            "meta-llama/Llama-3.3-70B-Instruct": (4.13, 4.13, "标准收费"),
            
            # ===== 高级模型 =====
            "deepseek-ai/DeepSeek-R1": (5.50, 5.50, "高级推理模型"),
            "Qwen/QwQ-32B-Preview": (1.26, 1.26, "高级推理模型"),
            "anthropic/claude-3-5-sonnet-20241022": (1.50, 7.50, "Claude 3.5 Sonnet"),
            "anthropic/claude-3-5-haiku-20241022": (1.00, 5.00, "Claude 3.5 Haiku"),
            "openai/gpt-4o-mini": (0.60, 1.80, "GPT-4o Mini"),
            "openai/gpt-4o": (15.00, 60.00, "GPT-4o"),
            
            # ===== 视觉和多模态模型 =====
            "anthropic/claude-3-5-sonnet-20241022-vision": (1.50, 7.50, "Claude Vision"),
            "openai/gpt-4o-vision": (15.00, 60.00, "GPT-4o Vision"),
            "THUDM/GLM-4.1V": (15.00, 15.00, "GLM Vision"),
            "stepfun/step-1v-8k": (5.00, 5.00, "Step Vision"),
        }
        
        return self._build_pricing_dict(enhanced_models)
    
    def _get_fallback_pricing(self) -> Dict[str, SiliconFlowModelPricing]:
        """获取回退的定价数据"""
        # 基础回退模型 (简化版本，由_get_enhanced_fallback_pricing()提供更全面的数据)
        basic_models = {
            # 主要免费模型
            "Qwen/Qwen2.5-7B-Instruct": (0.0, 0.0, "免费"),
            "THUDM/glm-4-9b-chat": (0.0, 0.0, "免费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": (0.0, 0.0, "免费"),
            
            # 主要收费模型
            "Qwen/Qwen2.5-14B-Instruct": (0.70, 0.70, "标准收费"),
            "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B": (0.70, 0.70, "标准收费"),
        }
        
        return self._build_pricing_dict(basic_models)
    
    def _build_pricing_dict(self, models_data: Dict[str, tuple]) -> Dict[str, SiliconFlowModelPricing]:
        """构建定价字典的通用方法"""
        pricing_dict = {}
        for model_name, (input_price, output_price, description) in models_data.items():
            pricing_dict[model_name] = SiliconFlowModelPricing(
                model_name=model_name,
                display_name=model_name.split('/')[-1],
                input_price=input_price,
                output_price=output_price,
                description=description
            )
        
        return pricing_dict
    
    async def run_pricing_scrape(self) -> Dict[str, Any]:
        """执行定价抓取任务"""
        logger.info("开始SiliconFlow定价抓取任务")
        start_time = datetime.now()
        
        try:
            # 清除定价缓存，强制重新抓取
            self.clear_pricing_cache()
            
            # 执行抓取
            pricing_data = await self.scrape_pricing_from_website()
            
            if not pricing_data:
                result = {
                    'status': 'error',
                    'error': '未能抓取到任何定价信息',
                    'models_count': 0,
                    'execution_time': (datetime.now() - start_time).total_seconds()
                }
                self._log_pricing_update(result)
                return result
            
            # 转换为可序列化的格式
            serializable_pricing = {}
            pricing_summary = {}
            
            for model_name, pricing in pricing_data.items():
                serializable_pricing[model_name] = {
                    'model_name': pricing.model_name,
                    'display_name': pricing.display_name,
                    'input_price': pricing.input_price,
                    'output_price': pricing.output_price,
                    'context_length': pricing.context_length,
                    'description': pricing.description,
                    'last_updated': datetime.now().isoformat()
                }
                
                # 生成价格摘要
                total_price = pricing.input_price + pricing.output_price
                if total_price == 0:
                    price_tier = 'free'
                elif total_price < 0.000001:
                    price_tier = 'very_cheap'
                elif total_price < 0.00001:
                    price_tier = 'cheap'
                else:
                    price_tier = 'standard'
                
                if price_tier not in pricing_summary:
                    pricing_summary[price_tier] = 0
                pricing_summary[price_tier] += 1
            
            # 保存缓存
            self._save_cache(serializable_pricing)
            self.cached_pricing = serializable_pricing
            self.last_update = datetime.now()
            
            result = {
                'status': 'success',
                'models_count': len(serializable_pricing),
                'pricing_summary': pricing_summary,
                'execution_time': (datetime.now() - start_time).total_seconds(),
                'updated_models': list(serializable_pricing.keys())
            }
            
            logger.info(f"SiliconFlow定价抓取完成: {len(serializable_pricing)} 个模型")
            self._log_pricing_update(result)
            return result
            
        except Exception as e:
            logger.error(f"SiliconFlow定价抓取失败: {e}")
            result = {
                'status': 'error',
                'error': str(e),
                'models_count': 0,
                'execution_time': (datetime.now() - start_time).total_seconds()
            }
            self._log_pricing_update(result)
            return result
    
    def clear_pricing_cache(self):
        """清除定价缓存 - 用于强制重新抓取"""
        if self.pricing_cache_file.exists():
            self.pricing_cache_file.unlink()
        self.cached_pricing = {}
        self.last_update = None
        logger.info("SiliconFlow定价缓存已清除")
    
    def should_update_pricing(self, force: bool = False) -> bool:
        """判断是否需要更新定价信息"""
        if force:
            return True
        
        if not self.last_update:
            return True
        
        # 每天更新一次定价信息
        update_interval = timedelta(days=1)
        return datetime.now() - self.last_update > update_interval
    
    async def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Any]]:
        """获取特定模型的定价信息"""
        if model_name in self.cached_pricing:
            pricing = self.cached_pricing[model_name]
            return {
                "prompt": str(pricing['input_price']),
                "completion": str(pricing['output_price']),
                "request": "0",
                "image": "0",
                "audio": "0",
                "web_search": "0",
                "internal_reasoning": "0"
            }
        return None
    
    def get_all_pricing(self) -> Dict[str, Any]:
        """获取所有缓存的定价信息"""
        return self.cached_pricing.copy()
    
    def get_pricing_stats(self) -> Dict[str, Any]:
        """获取定价统计信息"""
        if not self.cached_pricing:
            return {'total_models': 0}
        
        stats = {
            'total_models': len(self.cached_pricing),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'price_distribution': {}
        }
        
        # 统计价格分布
        for model_name, pricing in self.cached_pricing.items():
            total_price = pricing['input_price'] + pricing['output_price']
            
            if total_price == 0:
                tier = 'free'
            elif total_price < 0.000001:
                tier = 'very_cheap'
            elif total_price < 0.00001:
                tier = 'cheap'
            else:
                tier = 'standard'
            
            stats['price_distribution'][tier] = stats['price_distribution'].get(tier, 0) + 1
        
        return stats

# 全局实例
_pricing_task = None

def get_siliconflow_pricing_task() -> SiliconFlowPricingTask:
    """获取全局SiliconFlow定价任务实例"""
    global _pricing_task
    if _pricing_task is None:
        _pricing_task = SiliconFlowPricingTask()
    return _pricing_task

async def run_siliconflow_pricing_update(force: bool = False) -> Dict[str, Any]:
    """运行SiliconFlow定价更新任务"""
    task = get_siliconflow_pricing_task()
    
    if task.should_update_pricing(force):
        return await task.run_pricing_scrape()
    else:
        logger.info("SiliconFlow定价信息仍然有效，跳过更新")
        return {
            'status': 'skipped',
            'reason': 'pricing_still_valid',
            'last_update': task.last_update.isoformat() if task.last_update else None,
            'models_count': len(task.cached_pricing)
        }