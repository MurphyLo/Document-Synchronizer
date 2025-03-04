from metagpt.actions import Action
from metagpt.roles import Role
from pathlib import Path
from difflib import Differ
from typing import ClassVar

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
        import re
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


class DocMaintainer(Role):
    """文档维护主角色"""
    def __init__(self):
        super().__init__()
        self.set_actions([
            CheckDocStructureAction,
            TranslationAction, 
            GenerateDocAction
        ])
        
    async def _act(self):
        # 核心工作流：
        # 1. 检查文档结构差异
        base_path = Path("src")
        lang_dirs = ["en", "zh"]
        structure = await CheckDocStructureAction().run(base_path, lang_dirs)
        
        # 2. 识别缺失文件
        missing_files = self._find_missing(structure)
        
        # 3. 生成补全文档
        await GenerateDocAction().run(missing_files, base_path, structure)

    def _find_missing(self, structure: dict):
        # 实现差异比对逻辑
        all_files = set().union(*structure.values())
        missing = {}
        for lang in structure:
            missing[lang] = all_files - structure[lang]
        return missing

async def main():
    maintainer = DocMaintainer()
    await maintainer.run("开始文档同步")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
