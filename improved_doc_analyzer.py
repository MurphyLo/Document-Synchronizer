"""
改进的文档分析器 - 为文档维护提供额外的分析功能
"""

from pathlib import Path
import re
import difflib
from typing import Dict, List, Tuple

class DocAnalyzer:
    """文档分析工具类，提供额外的文档分析功能"""
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """计算两段文本的相似度，返回0-1之间的值，1表示完全相同"""
        s = difflib.SequenceMatcher(None, text1, text2)
        return s.ratio()
    
    @staticmethod
    def is_missing_significant_content(source: str, target: str, threshold: float = 0.7) -> bool:
        """检查目标文档是否缺失了大量内容
        
        通过比较文档长度和关键部分是否存在来判断
        
        Args:
            source: 源文档内容
            target: 目标文档内容
            threshold: 长度比例阈值，低于此值认为缺失较多内容
            
        Returns:
            bool: 是否缺失重要内容
        """
        # 基于长度的简单比较
        if len(target) / len(source) < threshold:
            return True
            
        # 检查标题和结构
        source_headers = re.findall(r'^#+\s+.+$', source, re.MULTILINE)
        target_headers = re.findall(r'^#+\s+.+$', target, re.MULTILINE)
        
        # 如果源文档有标题但目标文档标题数量明显偏少
        if source_headers and len(target_headers) / len(source_headers) < threshold:
            return True
            
        return False

    @staticmethod
    def extract_document_sections(content: str) -> List[Dict]:
        """提取文档的主要部分，包括标题和内容
        
        返回格式: [{"type": "heading", "content": "标题"}, {"type": "paragraph", "content": "内容"}]
        """
        sections = []
        lines = content.split('\n')
        current_section = None
        current_content = []
        
        for line in lines:
            # 检测标题行
            if re.match(r'^#+\s+', line):
                # 如果有当前部分，则保存
                if current_section:
                    sections.append({
                        "type": current_section,
                        "content": '\n'.join(current_content)
                    })
                
                # 开始新的标题部分
                current_section = "heading"
                current_content = [line]
            else:
                # 如果还没有部分，开始一个段落部分
                if not current_section:
                    current_section = "paragraph"
                    current_content = [line]
                # 如果当前是标题部分，且这行不为空，开始一个新的段落部分
                elif current_section == "heading" and line.strip():
                    sections.append({
                        "type": current_section,
                        "content": '\n'.join(current_content)
                    })
                    current_section = "paragraph"
                    current_content = [line]
                # 否则追加到当前内容
                else:
                    current_content.append(line)
        
        # 添加最后一个部分
        if current_section and current_content:
            sections.append({
                "type": current_section,
                "content": '\n'.join(current_content)
            })
            
        return sections
    
    @staticmethod
    def check_common_translation_issues(source_text: str, translated_text: str) -> bool:
        """检查常见翻译问题，如术语不一致、格式丢失等
        
        Returns:
            bool: 是否存在翻译问题
        """
        # 检查代码块数量是否匹配
        source_code_blocks = len(re.findall(r'```[\s\S]*?```', source_text))
        translated_code_blocks = len(re.findall(r'```[\s\S]*?```', translated_text))
        
        if source_code_blocks != translated_code_blocks:
            return True
            
        # 检查链接数量是否匹配
        source_links = len(re.findall(r'\[.*?\]\(.*?\)', source_text))
        translated_links = len(re.findall(r'\[.*?\]\(.*?\)', translated_text))
        
        if source_links != translated_links:
            return True
            
        # 检查标题结构是否保持
        source_headers = re.findall(r'^(#+)\s+.+$', source_text, re.MULTILINE)
        translated_headers = re.findall(r'^(#+)\s+.+$', translated_text, re.MULTILINE)
        
        if len(source_headers) != len(translated_headers):
            return True
            
        # 检查标记结构是否保持
        patterns = [
            (r'\*\*.*?\*\*', '粗体'),  # 粗体
            (r'\*.*?\*', '斜体'),      # 斜体
            (r'`.*?`', '内联代码')      # 内联代码
        ]
        
        for pattern, name in patterns:
            source_count = len(re.findall(pattern, source_text))
            translated_count = len(re.findall(pattern, translated_text))
            if abs(source_count - translated_count) > source_count * 0.2:  # 允许20%的差异
                return True
                
        return False

# 示例用法
if __name__ == "__main__":
    analyzer = DocAnalyzer()
    
    # 示例文档
    source = """# 示例文档
    
这是一个示例段落。
    
## 第二节
    
这是另一个段落，包含 `代码` 和**加粗文字**。
    
```python
def example():
    return "This is a code block"
```
    
### 子节
    
最后一段内容 [链接](https://example.com)
"""
    
    target = """# 示例文档
    
这是示例段落。
    
## 第二部分
    
这是另一段，有`代码`和**加粗**。
"""
    
    # 分析结果
    print("缺失内容:", analyzer.is_missing_significant_content(source, target))
    print("翻译问题:", analyzer.check_common_translation_issues(source, target))
    print("相似度:", analyzer.calculate_similarity(source, target))
    
    # 提取部分
    sections = analyzer.extract_document_sections(source)
    print("\n文档部分:")
    for i, section in enumerate(sections):
        print(f"{i+1}. {section['type']}: {section['content'][:30]}...")
