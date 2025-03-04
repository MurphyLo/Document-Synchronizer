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
    将以下{source_lang}文档准确翻译成{target_lang}，保持专业语气和技术准确性，保留格式，直接输出翻译结果，无需多余说明：
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
            block = block.strip()
            if block and '[CODE_BLOCK]' not in block:
                paragraphs.append(block)
        
        return code_blocks, paragraphs

class CompareContentAction(Action):
    """比较文档内容差异"""
    SEMANTIC_COMPARISON_PROMPT: ClassVar[str] = """
    请比较以下两段文本的语义内容，并判断它们是否表达了相同的意思:
    
    文本1 ({lang1}): 
    {text1}
    
    文本2 ({lang2}): 
    {text2}
    
    仅回复 "相同" 或 "不同" 以及简短说明。如果不同，请指出缺失或额外的信息。
    """
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """比较两个文档的内容差异
        
        Returns:
            Dict: 包含差异信息的字典
                - code_differences: 代码块差异列表
                - text_differences: 文本段落差异列表
        """
        source_content = source_path.read_text(encoding='utf-8')
        target_content = target_path.read_text(encoding='utf-8')
        
        extract_action = ExtractContentBlocksAction()
        
        source_code_blocks, source_paragraphs = await extract_action.run(source_content)
        target_code_blocks, target_paragraphs = await extract_action.run(target_content)
        
        # 比较代码块 (应完全一致)
        code_differences = []
        for i, source_block in enumerate(source_code_blocks):
            if i >= len(target_code_blocks):
                code_differences.append({
                    "type": "missing",
                    "index": i,
                    "source_block": source_block,
                    "target_block": None
                })
            elif source_block.strip() != target_code_blocks[i].strip():
                code_differences.append({
                    "type": "different",
                    "index": i,
                    "source_block": source_block,
                    "target_block": target_code_blocks[i]
                })
        
        # 检查目标文档是否有额外代码块
        if len(target_code_blocks) > len(source_code_blocks):
            for i in range(len(source_code_blocks), len(target_code_blocks)):
                code_differences.append({
                    "type": "extra",
                    "index": i,
                    "source_block": None,
                    "target_block": target_code_blocks[i]
                })
        
        # 比较文本段落 (通过LLM判断语义相似性)
        text_differences = []
        for i, source_para in enumerate(source_paragraphs):
            if i >= len(target_paragraphs):
                text_differences.append({
                    "type": "missing",
                    "index": i,
                    "source_paragraph": source_para,
                    "target_paragraph": None
                })
            else:
                # 使用LLM比较文本语义
                comparison_result = await self._aask(
                    self.SEMANTIC_COMPARISON_PROMPT.format(
                        lang1=source_lang,
                        text1=source_para,
                        lang2=target_lang,
                        text2=target_paragraphs[i]
                    )
                )
                
                if "不同" in comparison_result:
                    text_differences.append({
                        "type": "semantic_different",
                        "index": i,
                        "source_paragraph": source_para,
                        "target_paragraph": target_paragraphs[i],
                        "analysis": comparison_result
                    })
        
        # 检查目标文档是否有额外段落
        if len(target_paragraphs) > len(source_paragraphs):
            for i in range(len(source_paragraphs), len(target_paragraphs)):
                text_differences.append({
                    "type": "extra",
                    "index": i,
                    "source_paragraph": None,
                    "target_paragraph": target_paragraphs[i]
                })
                
        return {
            "code_differences": code_differences,
            "text_differences": text_differences
        }

class SynchronizeDocContentAction(Action):
    """同步文档内容，确保各语言版本内容一致"""
    
    CODE_BLOCK_TRANSLATION_PROMPT: ClassVar[str] = """
    以下是一个代码块。请不要翻译代码本身，但是将注释从{source_lang}翻译为{target_lang}。
    保持代码结构、变量名和函数名完全不变:
    
    {code_block}
    """
    
    TEXT_TRANSLATION_PROMPT: ClassVar[str] = """
    请将以下{source_lang}文本翻译为{target_lang}，保持技术准确性和原文风格:
    
    {text}
    """
    
    async def run(self, differences: Dict, source_path: Path, target_path: Path, 
                  source_lang: str, target_lang: str):
        """同步两个文档的内容
        
        Args:
            differences: CompareContentAction返回的差异信息
            source_path: 源文档路径
            target_path: 目标文档路径
            source_lang: 源语言
            target_lang: 目标语言
        """
        if not differences["code_differences"] and not differences["text_differences"]:
            return False  # 无需修改
        
        target_content = target_path.read_text(encoding='utf-8')
        source_content = source_path.read_text(encoding='utf-8')
        
        # 提取目标文档的当前结构
        extract_action = ExtractContentBlocksAction()
        _, _ = await extract_action.run(target_content)
        
        # 更新列表，用于重建文档
        updated_content = target_content
        
        # 处理缺失或不同的代码块
        for diff in differences["code_differences"]:
            if diff["type"] == "missing":
                # 如果代码块缺失，需要翻译注释并添加
                code_block = diff["source_block"]
                if any(line.strip().startswith(('/', '#', '<!--')) for line in code_block.splitlines()):
                    # 有注释，需要翻译
                    translated_block = await self._aask(
                        self.CODE_BLOCK_TRANSLATION_PROMPT.format(
                            source_lang=source_lang,
                            target_lang=target_lang,
                            code_block=code_block
                        )
                    )
                    # TODO: 将翻译后的代码块插入到适当位置
                else:
                    # 无注释，直接复制
                    translated_block = code_block
                
                # 根据差异类型和位置更新文档内容
                # 这里需要更复杂的文档结构分析和更新策略
            
            elif diff["type"] == "different":
                # 如果代码块不同，需要用源代码块替换，但保留目标语言的注释
                # 这需要更复杂的代码块合并策略
                pass
        
        # 处理文本差异
        for diff in differences["text_differences"]:
            if diff["type"] == "missing" or diff["type"] == "semantic_different":
                # 翻译缺失或语义不同的段落
                source_text = diff["source_paragraph"]
                translated_text = await self._aask(
                    self.TEXT_TRANSLATION_PROMPT.format(
                        source_lang=source_lang,
                        target_lang=target_lang,
                        text=source_text
                    )
                )
                # TODO: 将翻译后的文本插入到适当位置
        
        # 将更新后的内容写回文件
        # 注意：上面的更新逻辑需要进一步完善，以正确处理Markdown文档结构
        # 目前的实现只是一个框架
        
        return True  # 表示文件已更新

class DocMaintainer(Role):
    """文档维护主角色"""
    def __init__(self):
        super().__init__()
        self.set_actions([
            CheckDocStructureAction,
            TranslationAction, 
            GenerateDocAction,
            ExtractContentBlocksAction,
            CompareContentAction,
            SynchronizeDocContentAction
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
        
        # 4. 新增功能：比较文件内容并同步
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
                
                # 比较内容
                differences = await CompareContentAction().run(
                    source_path, 
                    target_path, 
                    primary_lang, 
                    target_lang
                )
                
                # 如果有差异，进行同步
                if differences["code_differences"] or differences["text_differences"]:
                    print(f"发现差异，同步文件: {file} ({target_lang})")
                    await SynchronizeDocContentAction().run(
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
