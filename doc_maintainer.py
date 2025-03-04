"""
文档维护工具 - 用于检查和同步多语言文档

用法示例:
python doc_maintainer.py --path ./docs --langs en,zh,es --primary en
"""

from metagpt.actions import Action
from metagpt.roles import Role
from pathlib import Path
from difflib import Differ
from typing import ClassVar, Dict, List, Tuple, Set, Optional
import re
import json
import sys
import argparse
import asyncio
import logging
from datetime import datetime
from colorama import Fore, Style, init

# 初始化colorama以支持Windows颜色输出
init()

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('DocMaintainer')

# 添加文件处理器以将日志写入到文件
file_handler = logging.FileHandler('doc_maintainer.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Action类定义
class CheckDocStructureAction(Action):
    """检查文档目录结构差异""" 
    async def run(self, base_path: Path, lang_dirs: list):
        structure = {}
        for lang in lang_dirs:
            lang_path = base_path / lang
            if not lang_path.exists():
                logger.warning(f"{Fore.YELLOW}语言目录不存在: {lang_path}{Style.RESET_ALL}")
                structure[lang] = set()
                continue
                
            files = [str(p.relative_to(lang_path)) for p in lang_path.rglob('*.md')]
            structure[lang] = set(files)
            logger.info(f"{Fore.GREEN}已扫描 {lang} 目录: 发现 {len(files)} 个文档{Style.RESET_ALL}")
        return structure

class TranslationAction(Action):
    """执行文档翻译的Action"""
    PROMPT_TEMPLATE: ClassVar[str] = """
    将以下{source_lang}文档准确翻译成{target_lang}，保持专业语气和技术准确性，保留原文的所有格式、标记和结构。
    对于较长内容，请确保完整翻译每一段落，不要遗漏或简化任何部分。
    直接输出翻译结果，无需额外说明：
    
    {content}
    """
    
    IMPROVEMENT_PROMPT_TEMPLATE: ClassVar[str] = """
    请改进以下{target_lang}翻译文档，使其更准确地反映{source_lang}原文内容。
    
    原文({source_lang}):
    {source_content}
    
    现有翻译({target_lang}):
    {target_content}
    
    要求:
    1. 保留现有翻译中正确且合适的部分
    2. 修正不准确或不恰当的翻译部分
    3. 补充原文中有但翻译中缺失的内容
    4. 保持原文的所有格式、标记和结构
    
    请输出完整的改进后文档，而不只是更改的部分：
    """
    
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)
    
    async def run(self, content: str, source_lang: str, target_lang: str, existing_translation: str = None):
        """执行翻译，如有现有翻译则进行改进而非重新翻译"""
        logger.info(f"执行{'翻译改进' if existing_translation else '新翻译'}: {source_lang} → {target_lang}")
        
        if existing_translation:
            # 如果有现有翻译，使用改进模式
            return await self._aask(
                self.IMPROVEMENT_PROMPT_TEMPLATE.format(
                    source_content=content,
                    source_lang=source_lang,
                    target_content=existing_translation,
                    target_lang=target_lang
                )
            )
        else:
            # 没有现有翻译，进行全新翻译
            return await self._aask(
                self.PROMPT_TEMPLATE.format(
                    content=content,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
            )

class GenerateDocAction(Action):
    """生成缺失文档的Action"""
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)

    async def run(self, missing_files: dict, base_path: Path, structure: dict, primary_lang: str, dry_run: bool = False):
        """基于现有语言版本生成缺失的文档
        
        Args:
            missing_files: 缺失文件的字典 {语言: [文件路径]}
            base_path: 文档根目录
            structure: 文档结构信息
            primary_lang: 主要语言
            dry_run: 如果为True，仅打印操作但不执行
            
        Returns:
            dict: 操作统计信息
        """
        stats = {"planned": 0, "created": 0, "skipped": 0}
        
        for target_lang, files in missing_files.items():
            for file in files:
                # 优先使用主要语言作为源语言
                source_lang = None
                source_content = None
                
                # 首先尝试使用主要语言
                if primary_lang in structure and file in structure[primary_lang]:
                    source_lang = primary_lang
                    source_path = base_path / primary_lang / file
                    if source_path.exists():
                        source_content = source_path.read_text(encoding='utf-8')
                
                # 如果主要语言没有该文件，尝试其他语言
                if not source_content:
                    for lang in structure:
                        if file in structure[lang] and lang != target_lang:
                            source_lang = lang
                            source_path = base_path / lang / file
                            if source_path.exists():
                                source_content = source_path.read_text(encoding='utf-8')
                                break
                
                if source_lang and source_content:
                    target_path = base_path / target_lang / file
                    stats["planned"] += 1
                    
                    # 打印操作信息
                    logger.info(f"{Fore.BLUE}需要翻译: {source_lang} → {target_lang} : {file}{Style.RESET_ALL}")
                    
                    if dry_run:
                        logger.info(f"{Fore.YELLOW}[模拟] 将创建翻译: {target_path}{Style.RESET_ALL}")
                        continue
                    
                    # 翻译内容
                    translated_content = await TranslationAction().run(
                        source_content, 
                        source_lang, 
                        target_lang
                    )

                    # 写入前添加过滤
                    filtered_content = self._remove_tags(translated_content)
                    
                    # 确保目标目录存在
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_text(filtered_content, encoding='utf-8')
                    
                    logger.info(f"{Fore.GREEN}✓ 创建翻译文件: {target_path}{Style.RESET_ALL}")
                    stats["created"] += 1
                else:
                    logger.warning(f"{Fore.YELLOW}无法翻译 {file} 到 {target_lang}: 未找到源文件{Style.RESET_ALL}")
                    stats["skipped"] += 1
        
        return stats

class CompareDocumentAction(Action):
    """比较文档并识别差异"""
    
    DOCUMENT_COMPARISON_PROMPT: ClassVar[str] = """
    请比较以下两种语言版本的文档，找出差异类型：
    
    ## 源文档 ({source_lang}):
    {source_content}
    
    ## 目标文档 ({target_lang}):
    {target_content}
    
    ## 要求:
    1. 检查目标文档是否有缺失内容（整段落、部分段落或任何内容缺失）
    2. 检查目标文档的翻译是否存在不准确或不恰当的部分
    
    ## 返回格式:
    请直接返回JSON格式的结果，不要包含其他解释：
    {{
        "has_missing_content": true/false,
        "has_translation_issues": true/false,
        "needs_improvement": true/false  // 如果上面任一为true，则此项为true
    }}
    """
    
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """比较两个文档，检查是否有差异
        
        Returns:
            Dict: 包含差异类型的字典
        """
        logger.debug(f"比较文档: {source_path.name} ({source_lang} vs {target_lang})")
        source_content = source_path.read_text(encoding='utf-8')
        target_content = target_path.read_text(encoding='utf-8')
        
        # 使用LLM进行文档比较
        comparison_response = await self._aask(
            self.DOCUMENT_COMPARISON_PROMPT.format(
                source_lang=source_lang,
                source_content=source_content,
                target_lang=target_lang,
                target_content=target_content
            )
        )
        
        # 处理LLM返回的结果
        try:
            # 移除特定标签
            cleaned_response = self._remove_tags(comparison_response)
            
            # 尝试解析JSON
            try:
                result = json.loads(cleaned_response)
            except json.JSONDecodeError:
                # 尝试提取JSON部分
                json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', cleaned_response)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        raise ValueError("无法解析提取的JSON内容")
                else:
                    raise ValueError("响应中找不到有效的JSON格式")
            
            # 确保结果包含所有必需的键
            required_keys = ["has_missing_content", "has_translation_issues", "needs_improvement"]
            for key in required_keys:
                if key not in result:
                    if key == "needs_improvement":
                        result[key] = result.get("has_missing_content", False) or result.get("has_translation_issues", False)
                    else:
                        result[key] = False
                    
            return result
            
        except Exception as e:
            logger.error(f"{Fore.RED}解析比较结果失败: {e}{Style.RESET_ALL}")
            logger.debug(f"原始响应: {comparison_response[:200]}...")
            
            # 返回默认结构
            return {
                "has_missing_content": False,
                "has_translation_issues": False,
                "needs_improvement": False,
                "error": str(e)
            }

class DocumentSynchronizationAction(Action):
    """文档同步，根据比较结果改进翻译"""
    
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)
    
    async def run(self, comparison_result: Dict, source_path: Path, target_path: Path, 
                  source_lang: str, target_lang: str, dry_run: bool = False):
        """根据比较结果同步文档内容
        
        Args:
            comparison_result: CompareDocumentAction返回的比较结果
            source_path: 源文档路径
            target_path: 目标文档路径
            source_lang: 源语言
            target_lang: 目标语言
            dry_run: 如果为True，仅打印操作但不执行
        
        Returns:
            bool: 是否进行了更改
        """
        # 如果不需要改进，直接返回
        if not comparison_result.get("needs_improvement", False):
            return False
            
        issues = []
        if comparison_result.get("has_missing_content"):
            issues.append("内容缺失")
        if comparison_result.get("has_translation_issues"):
            issues.append("翻译不准确")
            
        logger.info(f"{Fore.YELLOW}文档需要改进: {target_path.name} - 问题: {', '.join(issues)}{Style.RESET_ALL}")
        
        if dry_run:
            logger.info(f"{Fore.YELLOW}[模拟] 将改进文档: {target_path}{Style.RESET_ALL}")
            return True
            
        source_content = source_path.read_text(encoding='utf-8')
        
        # 如果目标文件存在，则读取现有翻译，否则为None
        existing_translation = None
        if target_path.exists():
            existing_translation = target_path.read_text(encoding='utf-8')
            
        # 翻译或改进文档
        translation = await TranslationAction().run(
            source_content,
            source_lang,
            target_lang,
            existing_translation
        )
        
        # 移除特定标签
        cleaned_translation = self._remove_tags(translation)
        
        # 写入更新后的翻译
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(cleaned_translation, encoding='utf-8')
        
        logger.info(f"{Fore.GREEN}✓ {'更新' if existing_translation else '创建'}文件: {target_path}{Style.RESET_ALL}")
        return True

class ExtractContentBlocksAction(Action):
    """从文档中提取代码块和文本段落"""
    
    async def run(self, content: str):
        """提取文档中的代码块和文本段落
        
        Returns:
            Tuple[List[str], List[str]]: 代码块列表和文本段落列表
        """
        # 提取代码块 (```开始和结束的区块)
        code_block_pattern = r'```[^\n]*\n(.*?)```'
        code_blocks = re.findall(code_block_pattern, content, re.DOTALL)
        
        # 替换掉代码块后提取文本段落 (连续的非空行)
        content_without_code = re.sub(code_block_pattern, '[CODE_BLOCK]', content, flags=re.DOTALL)
        
        # 按照空行分割文本，获取段落
        paragraphs = []
        for block in re.split(r'\n\s*\n', content_without_code):
            block = block.strip()
            if block and '[CODE_BLOCK]' not in block:
                paragraphs.append(block)
        
        return code_blocks, paragraphs

class DocMaintainer(Role):
    """文档维护主角色"""
    def __init__(self, base_path: str = "docs", lang_dirs: List[str] = ["en", "zh"], 
                 primary_lang: str = "en", verbose: bool = False, dry_run: bool = False):
        """初始化文档维护角色
        
        Args:
            base_path: 文档根目录
            lang_dirs: 语言目录列表
            primary_lang: 主要语言（作为翻译源）
            verbose: 是否显示详细信息
            dry_run: 如果为True，不实际修改文件
        """
        super().__init__()
        self.base_path = Path(base_path)
        self.lang_dirs = lang_dirs
        self.primary_lang = primary_lang
        self.verbose = verbose
        self.dry_run = dry_run
        
        # 设置日志级别
        if verbose:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
            
        self.set_actions([
            CheckDocStructureAction,
            TranslationAction, 
            GenerateDocAction,
            ExtractContentBlocksAction,
            CompareDocumentAction,
            DocumentSynchronizationAction
        ])
        
        self.stats = {
            "missing_files": 0,
            "files_to_improve": 0,
            "files_created": 0,
            "files_improved": 0
        }
        
    def _find_missing(self, structure: dict):
        """实现查找缺失文件的逻辑"""
        all_files = set().union(*structure.values()) if structure.values() else set()
        missing = {}
        for lang in structure:
            missing_files = all_files - structure[lang]
            missing[lang] = missing_files
            if missing_files:
                self.stats["missing_files"] += len(missing_files)
                
        return missing
    
    async def check_and_generate_docs(self):
        """检查并生成缺失的文档"""
        logger.info(f"{Fore.CYAN}开始检查文档结构: {self.base_path}{Style.RESET_ALL}")
        
        # 1. 检查文档结构
        structure = await CheckDocStructureAction().run(self.base_path, self.lang_dirs)
        
        # 2. 识别缺失文件
        missing_files = self._find_missing(structure)
        
        # 3. 统计缺失文件
        total_missing = sum(len(files) for files in missing_files.values())
        if total_missing > 0:
            logger.info(f"{Fore.YELLOW}发现 {total_missing} 个缺失文件{Style.RESET_ALL}")
            for lang, files in missing_files.items():
                if files:
                    logger.info(f"  {lang}: 缺少 {len(files)} 个文件")
                    if self.verbose:
                        for f in files:
                            logger.debug(f"    - {f}")
        else:
            logger.info(f"{Fore.GREEN}未发现缺失文件{Style.RESET_ALL}")
        
        # 4. 生成缺失文档
        if total_missing > 0:
            if self.dry_run:
                logger.info(f"{Fore.YELLOW}[模拟模式] 将生成 {total_missing} 个缺失文件{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.BLUE}开始生成缺失文件...{Style.RESET_ALL}")
                
            stats = await GenerateDocAction().run(
                missing_files, 
                self.base_path, 
                structure, 
                self.primary_lang,
                self.dry_run
            )
            self.stats["files_created"] = stats["created"]
        
        return structure
    
    async def synchronize_doc_content(self, structure: dict):
        """同步文档内容，更新不一致的翻译"""
        logger.info(f"{Fore.CYAN}开始检查文档内容一致性{Style.RESET_ALL}")
        
        # 获取所有共有的文件
        common_files = {}
        all_files = set().union(*structure.values()) if structure.values() else set()
        
        # 对每个文件，查找它存在于哪些语言中
        for file in all_files:
            langs = [lang for lang in structure if file in structure[lang]]
            if len(langs) > 1:  # 至少两种语言都有这个文件
                common_files[file] = langs
        
        logger.info(f"共有 {len(common_files)} 个文件需要检查内容一致性")
        
        # 比较每个共有文件在不同语言版本间的内容差异
        files_to_improve = 0
        files_improved = 0
        
        for file, langs in common_files.items():
            source_path = self.base_path / self.primary_lang / file
            
            # 跳过主语言不存在的文件
            if not source_path.exists() or self.primary_lang not in langs:
                continue
                
            for target_lang in langs:
                if target_lang == self.primary_lang:
                    continue
                    
                target_path = self.base_path / target_lang / file
                
                if self.verbose:
                    logger.debug(f"比较文档: {file} ({self.primary_lang} → {target_lang})")
                
                # 比较文档内容
                comparison_result = await CompareDocumentAction().run(
                    source_path, 
                    target_path, 
                    self.primary_lang, 
                    target_lang
                )
                
                # 处理比较结果
                if comparison_result.get("needs_improvement"):
                    files_to_improve += 1
                    self.stats["files_to_improve"] += 1
                    
                    # 同步文档内容
                    was_improved = await DocumentSynchronizationAction().run(
                        comparison_result,
                        source_path,
                        target_path,
                        self.primary_lang,
                        target_lang,
                        self.dry_run
                    )
                    
                    if was_improved and not self.dry_run:
                        files_improved += 1
                        self.stats["files_improved"] += 1
                elif self.verbose:
                    logger.debug(f"  ✓ 文档已同步")
        
        # 汇总结果
        if files_to_improve > 0:
            if self.dry_run:
                logger.info(f"{Fore.YELLOW}[模拟模式] 需要改进 {files_to_improve} 个文件{Style.RESET_ALL}")
            else:
                logger.info(f"{Fore.GREEN}已改进 {files_improved} 个文件{Style.RESET_ALL}")
        else:
            logger.info(f"{Fore.GREEN}所有文档内容一致，无需改进{Style.RESET_ALL}")
    
    async def run_maintenance(self):
        """运行完整的文档维护流程"""
        start_time = datetime.now()
        logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}开始文档维护流程{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}文档目录: {self.base_path}{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}语言: {', '.join(self.lang_dirs)}{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}主要语言: {self.primary_lang}{Style.RESET_ALL}")
        if self.dry_run:
            logger.info(f"{Fore.YELLOW}[模拟模式] 不会实际修改任何文件{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
        
        try:
            # 1. 检查并生成缺失文档
            structure = await self.check_and_generate_docs()
            
            # 2. 同步文档内容
            await self.synchronize_doc_content(structure)
            
            # 3. 汇总结果
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
            logger.info(f"{Fore.CYAN}文档维护完成 (耗时: {duration:.1f}秒){Style.RESET_ALL}")
            logger.info(f"{Fore.CYAN}统计信息:{Style.RESET_ALL}")
            logger.info(f"  - 发现缺失文件: {self.stats['missing_files']} 个")
            logger.info(f"  - 发现需改进文件: {self.stats['files_to_improve']} 个")
            
            if not self.dry_run:
                logger.info(f"  - 创建新文件: {self.stats['files_created']} 个")
                logger.info(f"  - 改进文件: {self.stats['files_improved']} 个")
            logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
            
            return self.stats
        except Exception as e:
            logger.error(f"{Fore.RED}文档维护过程中出错: {e}{Style.RESET_ALL}")
            import traceback
            logger.debug(traceback.format_exc())
            return {"error": str(e)}

def setup_argparse():
    """设置命令行参数解析"""
    parser = argparse.ArgumentParser(
        description="多语言文档维护工具 - 用于检查和同步多语言文档",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument("-p", "--path", type=str, default="./test",
                      help="文档根目录路径")
                      
    parser.add_argument("-l", "--langs", type=str, default="en,zh",
                      help="语言目录列表，用逗号分隔")
                      
    parser.add_argument("-m", "--primary", type=str, default="en",
                      help="主要语言，用作翻译源")
                      
    parser.add_argument("-v", "--verbose", action="store_true",
                      help="显示详细输出信息")
                      
    parser.add_argument("-d", "--dry-run", action="store_true",
                      help="模拟模式，不实际修改文件")
                      
    return parser

async def main():
    """主函数，解析命令行参数并运行文档维护"""
    parser = setup_argparse()
    args = parser.parse_args()
    
    # 解析语言列表
    lang_dirs = args.langs.split(',')
    
    # 创建维护器并运行
    maintainer = DocMaintainer(
        base_path=args.path,
        lang_dirs=lang_dirs,
        primary_lang=args.primary,
        verbose=args.verbose,
        dry_run=args.dry_run
    )
    
    await maintainer.run_maintenance()

if __name__ == "__main__":
    asyncio.run(main())
