from metagpt.actions import Action
from metagpt.roles import Role
from pathlib import Path
from difflib import Differ
from typing import ClassVar, Dict, List, Tuple, Set
import re

class CheckDocStructureAction(Action):
    """检查文档目录结构差异""" 
    async def run(self, base_path: Path, lang_dirs: list):
        structure = {}
        for lang in lang_dirs:
            lang_path = base_path / lang
            files = [str(p.relative_to(lang_path)) for p in lang_path.rglob('*.md')]
            structure[lang] = set(files)
        return structure  # 返回各语言文档结构

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
    
    async def run(self, content: str, source_lang: str, target_lang: str, existing_translation: str = None):
        """执行翻译，如有现有翻译则进行改进而非重新翻译"""
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
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)  # [^<]防止贪婪匹配[^7]

    async def run(self, missing_files: dict, base_path: Path, structure: dict):
        # Find a source language for translation
        for target_lang, files in missing_files.items():
            for file in files:
                # Find a source language that has this file
                source_lang = None
                source_content = None
                
                for lang in structure:
                    if file in structure[lang] and lang != target_lang:
                        source_lang = lang
                        source_path = base_path / lang / file
                        source_content = source_path.read_text(encoding='utf-8')
                        break
                
                if source_lang and source_content:
                    # Create target directory
                    target_path = base_path / target_lang / file
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Translate the content
                    translated_content = await TranslationAction().run(
                        source_content, 
                        source_lang, 
                        target_lang
                    )

                    # 写入前添加过滤
                    filtered_content = self._remove_tags(translated_content)
                    target_path.write_text(filtered_content, encoding='utf-8')

class CompareDocumentAction(Action):
    """简化的文档比较，只检查是否有差异，不记录具体位置"""
    
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
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """比较两个文档，检查是否有差异
        
        Returns:
            Dict: 包含差异类型的字典
        """
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
            import json
            import re
            
            # 尝试直接解析或提取JSON
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
            print(f"解析比较结果失败: {e}")
            print(f"原始响应: {comparison_response[:200]}...")
            
            # 返回默认结构
            return {
                "has_missing_content": False,
                "has_translation_issues": False,
                "needs_improvement": False,
                "error": str(e)
            }

class DocumentSynchronizationAction(Action):
    """简化的文档同步，直接使用原文和现有翻译进行完整翻译/改进"""
    
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)
    
    async def run(self, comparison_result: Dict, source_path: Path, target_path: Path, 
                  source_lang: str, target_lang: str):
        """根据比较结果同步文档内容
        
        Args:
            comparison_result: CompareDocumentAction返回的比较结果
            source_path: 源文档路径
            target_path: 目标文档路径
            source_lang: 源语言
            target_lang: 目标语言
        
        Returns:
            bool: 是否进行了更改
        """
        # 如果不需要改进，直接返回
        if not comparison_result.get("needs_improvement", False):
            return False
            
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
        
        print(f"  ✓ 已{'更新' if existing_translation else '创建'}文件: {target_path}")
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
            block = block.strip()  # Fixed: Added 'block.' before strip()
            if block and '[CODE_BLOCK]' not in block:
                paragraphs.append(block)
        
        return code_blocks, paragraphs

class DocMaintainer(Role):
    """文档维护主角色"""
    def __init__(self):
        super().__init__()
        self.set_actions([
            CheckDocStructureAction,
            TranslationAction, 
            GenerateDocAction,
            ExtractContentBlocksAction,
            CompareDocumentAction,
            DocumentSynchronizationAction
        ])
        
    async def _act(self):
        # 核心工作流：
        # 1. 检查文档结构差异
        base_path = Path("test")
        lang_dirs = ["en", "zh"]
        structure = await CheckDocStructureAction().run(base_path, lang_dirs)
        
        # 2. 识别缺失文件
        missing_files = self._find_missing(structure)
        
        # 3. 生成补全文档
        await GenerateDocAction().run(missing_files, base_path, structure)
        
        # 4. 比较文件内容并同步
        await self._synchronize_doc_content(base_path, structure)

    def _find_missing(self, structure: dict):
        # 实现差异比对逻辑
        all_files = set().union(*structure.values())
        missing = {}
        for lang in structure:
            missing[lang] = all_files - structure[lang]
        return missing
    
    async def _synchronize_doc_content(self, base_path: Path, structure: dict):
        """逐文件比较内容并同步"""
        # 获取所有共有的文件
        common_files = {}
        all_files = set().union(*structure.values())
        
        # 对每个文件，查找它存在于哪些语言中
        for file in all_files:
            langs = [lang for lang in structure if file in structure[lang]]
            if len(langs) > 1:  # 至少两种语言都有这个文件
                common_files[file] = langs
        
        # 设置主语言（默认以英文为主）
        primary_lang = "en" if "en" in structure else list(structure.keys())[0]
        
        # 比较每个共有文件在不同语言版本间的内容差异
        for file, langs in common_files.items():
            source_path = base_path / primary_lang / file
            
            # 跳过主语言不存在的文件
            if not source_path.exists() or primary_lang not in langs:
                continue
                
            for target_lang in langs:
                if target_lang == primary_lang:
                    continue
                    
                target_path = base_path / target_lang / file
                print(f"比较文档: {file} ({primary_lang} → {target_lang})")
                
                # 简化的比较逻辑
                comparison_result = await CompareDocumentAction().run(
                    source_path, 
                    target_path, 
                    primary_lang, 
                    target_lang
                )
                
                # 根据比较结果输出信息
                if comparison_result.get("needs_improvement"):
                    issues = []
                    if comparison_result.get("has_missing_content"):
                        issues.append("内容缺失")
                    if comparison_result.get("has_translation_issues"):
                        issues.append("翻译问题")
                    print(f"  发现问题: {', '.join(issues)}")
                    
                    # 执行文档同步
                    await DocumentSynchronizationAction().run(
                        comparison_result,
                        source_path,
                        target_path,
                        primary_lang,
                        target_lang
                    )
                else:
                    print(f"  ✓ 文档已同步")

async def main():
    maintainer = DocMaintainer()
    await maintainer.run("开始文档同步")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
