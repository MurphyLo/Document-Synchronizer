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
    
    async def run(self, content: str, source_lang: str, target_lang: str):
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

class CompareDocumentAction(Action):
    """整体比较两个语言版本的文档"""
    
    DOCUMENT_COMPARISON_PROMPT: ClassVar[str] = """
    请比较以下两种语言版本的文档，找出差异并按照指定格式返回：
    
    ## 源文档 ({source_lang}):
    {source_content}
    
    ## 目标文档 ({target_lang}):
    {target_content}
    
    ## 要求:
    1. 首先详细检查目标文档中是否有缺失的段落或内容
       - 包括单个段落、连续多个段落、整节内容或任何缺失部分
       - 标记所有缺失内容，即使是大段落或从某处开始的所有后续内容
    2. 其次检查目标文档中的代码块与源文档是否完全一致（忽略注释内容）
    3. 最后分析目标文档的内容是否有语义上的偏差
    
    ## 返回格式:
    请直接返回JSON格式的结果，不要包含其他解释。严格遵循以下JSON结构，确保JSON格式正确无误且可以被解析:
    {{
        "missing_content": [
            {{
                "type": "paragraph/section/code/heading",
                "source_content": "源文档中的内容",
                "position_hint": "在目标文档中的位置提示（如：在某段落之后）"
            }}
        ],
        "code_differences": [
            {{
                "source_block": "源代码块",
                "target_block": "目标代码块", 
                "position": "在目标文档中的位置"
            }}
        ],
        "semantic_differences": [
            {{
                "source_paragraph": "源段落",
                "target_paragraph": "目标段落",
                "analysis": "差异分析",
                "position": "在目标文档中的位置"
            }}
        ]
    }}
    
    <注意>
    如果源文档有大量内容缺失，请按照逻辑段落或部分将其拆分成多个缺失项，而不是一次性返回整个文档。尝试标识文档中的主要部分，如引言、各个章节等，并将它们作为独立的缺失项标记。这样更容易进行后续翻译和整合。
    </注意>
    
    如果某个类别没有差异，请返回空列表。请提供完全有效的JSON，不含任何额外文本、导语或解释。
    """
    
    def _remove_tags(self, content: str) -> str:
        """使用正则表达式去除特定标记"""
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """比较两个文档的整体内容差异
        
        Returns:
            Dict: 包含文档级别差异的字典
        """
        source_content = source_path.read_text(encoding='utf-8')
        target_content = target_path.read_text(encoding='utf-8')
        
        # 使用LLM进行整体文档比较
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
            # 首先移除 <think> 和 </think> 标签
            cleaned_response = self._remove_tags(comparison_response)
            
            # 更严格的JSON提取方法
            import json
            import re
            
            # 1. 尝试直接解析整个响应
            try:
                result = json.loads(cleaned_response)
                
            # 2. 如果直接解析失败，尝试提取JSON部分
            except json.JSONDecodeError:
                # 尝试查找最外层的花括号对
                json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', cleaned_response)
                if json_match:
                    try:
                        result = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        # 如果仍然失败，进行更简单的清理并再次尝试
                        json_str = json_match.group(0)
                        # 移除可能的格式问题并处理转义字符
                        json_str = re.sub(r'\\(?!["\\/bfnrtu])', '', json_str)
                        try:
                            result = json.loads(json_str)
                        except json.JSONDecodeError:
                            raise ValueError("无法解析提取的JSON内容")
                else:
                    raise ValueError("响应中找不到有效的JSON格式")
            
            # 确保结果包含所有必需的键
            required_keys = ["missing_content", "code_differences", "semantic_differences"]
            for key in required_keys:
                if key not in result:
                    result[key] = []
                    
            return result
            
        except Exception as e:
            print(f"解析比较结果失败: {e}")
            print(f"原始响应: {comparison_response[:200]}...")
            
            # 返回默认结构
            return {
                "missing_content": [],
                "code_differences": [],
                "semantic_differences": [],
                "error": str(e)
            }

class DocumentSynchronizationAction(Action):
    """基于整体文档比较结果同步文档内容"""
    
    CONTENT_TRANSLATION_PROMPT: ClassVar[str] = """
    请将以下{source_lang}内容翻译为{target_lang}，保持技术准确性和原文风格:
    
    {content}
    """
    
    CODE_BLOCK_TRANSLATION_PROMPT: ClassVar[str] = """
    以下是一个代码块。请不要翻译代码本身，但是将注释从{source_lang}翻译为{target_lang}。
    保持代码结构、变量名和函数名完全不变:
    
    {code_block}
    """
    
    DOCUMENT_UPDATE_PROMPT: ClassVar[str] = """
    请根据以下指示更新目标文档:
    
    ## 原始文档 ({target_lang}):
    {original_document}
    
    ## 需要添加的内容:
    {content_to_add}
    
    ## 需要替换的内容:
    原内容: {content_to_replace}
    新内容: {replacement_content}
    
    ## 位置提示:
    {position_hint}
    
    请返回完整的更新后文档，保持原格式和结构。
    """
    
    async def run(self, differences: Dict, source_path: Path, target_path: Path, 
                  source_lang: str, target_lang: str):
        """根据文档级别的差异同步文档内容
        
        Args:
            differences: CompareDocumentAction返回的差异信息
            source_path: 源文档路径
            target_path: 目标文档路径
            source_lang: 源语言
            target_lang: 目标语言
        """
        # 检查是否需要同步
        if (not differences.get("missing_content") and 
            not differences.get("code_differences") and 
            not differences.get("semantic_differences")):
            return False  # 无需修改
        
        target_content = target_path.read_text(encoding='utf-8')
        source_content = source_path.read_text(encoding='utf-8')
        updated_content = target_content
        changes_made = False
        
        # 处理缺失内容
        if differences.get("missing_content"):
            print(f"  - 处理缺失内容: {len(differences['missing_content'])} 项")
            for item in differences["missing_content"]:
                source_content_piece = item["source_content"]
                position_hint = item.get("position_hint", "文档末尾")
                
                # 翻译缺失内容
                translated_content = await self._aask(
                    self.CONTENT_TRANSLATION_PROMPT.format(
                        source_lang=source_lang,
                        target_lang=target_lang,
                        content=source_content_piece
                    )
                )
                
                # 使用LLM将翻译的内容添加到适当位置
                updated_content = await self._aask(
                    self.DOCUMENT_UPDATE_PROMPT.format(
                        target_lang=target_lang,
                        original_document=updated_content,
                        content_to_add=translated_content,
                        content_to_replace="",  # 无需替换
                        replacement_content="",  # 无需替换
                        position_hint=position_hint
                    )
                )
                changes_made = True
        
        # 处理代码差异
        if differences.get("code_differences"):
            print(f"  - 处理代码差异: {len(differences['code_differences'])} 项")
            for item in differences["code_differences"]:
                source_block = item["source_block"]
                target_block = item["target_block"]
                position = item.get("position", "")
                
                # 对于代码块，我们保留原代码，但翻译注释
                if any(line.strip().startswith(('/', '#', '<!--')) for line in source_block.splitlines()):
                    # 有注释，需要翻译
                    translated_block = await self._aask(
                        self.CODE_BLOCK_TRANSLATION_PROMPT.format(
                            source_lang=source_lang,
                            target_lang=target_lang,
                            code_block=source_block
                        )
                    )
                else:
                    # 无注释，直接使用源代码块
                    translated_block = source_block
                
                # 使用LLM替换目标文档中的代码块
                if target_block:  # 替换现有代码块
                    updated_content = await self._aask(
                        self.DOCUMENT_UPDATE_PROMPT.format(
                            target_lang=target_lang,
                            original_document=updated_content,
                            content_to_add="",  # 无需添加
                            content_to_replace=f"```{target_block}```",
                            replacement_content=f"```{translated_block}```",
                            position_hint=position
                        )
                    )
                changes_made = True
        
        # 处理语义差异
        if differences.get("semantic_differences"):
            print(f"  - 处理语义差异: {len(differences['semantic_differences'])} 项")
            for item in differences["semantic_differences"]:
                source_para = item["source_paragraph"]
                target_para = item["target_paragraph"]
                position = item.get("position", "")
                
                # 重新翻译源段落
                translated_para = await self._aask(
                    self.CONTENT_TRANSLATION_PROMPT.format(
                        source_lang=source_lang,
                        target_lang=target_lang,
                        content=source_para
                    )
                )
                
                # 使用LLM替换目标文档中的段落
                updated_content = await self._aask(
                    self.DOCUMENT_UPDATE_PROMPT.format(
                        target_lang=target_lang,
                        original_document=updated_content,
                        content_to_add="",  # 无需添加
                        content_to_replace=target_para,
                        replacement_content=translated_para,
                        position_hint=position
                    )
                )
                changes_made = True
        
        # 如果有变更，写入文件
        if changes_made:
            # 移除<think>和</think>标记及其中的内容
            updated_content = re.sub(r'<think>[^<]*?</think>', '', updated_content, flags=re.DOTALL)
            target_path.write_text(updated_content, encoding='utf-8')
            print(f"  ✓ 已更新文件: {target_path}")
        
        return changes_made

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
                
                # 使用整体文档比较而不是逐段比较
                differences = await CompareDocumentAction().run(
                    source_path, 
                    target_path, 
                    primary_lang, 
                    target_lang
                )
                
                # 如果有差异，进行同步
                if (differences.get("missing_content") or 
                    differences.get("code_differences") or 
                    differences.get("semantic_differences")):
                    print(f"发现差异，同步文件: {file} ({target_lang})")
                    await DocumentSynchronizationAction().run(
                        differences,
                        source_path,
                        target_path,
                        primary_lang,
                        target_lang
                    )

async def main():
    maintainer = DocMaintainer()
    await maintainer.run("开始文档同步")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
