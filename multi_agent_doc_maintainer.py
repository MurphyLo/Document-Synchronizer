"""
Multi-Agent Document Maintenance System

Contains two roles:
1. DocumentChecker - Checks and compares document consistency
2. DocumentTranslator - Handles translation and translation improvement
"""

from metagpt.actions import Action
from metagpt.roles import Role
from metagpt.schema import Message
from pathlib import Path
from typing import ClassVar, Dict, List, Tuple, Set, Optional
import re
import json
import asyncio
from improved_doc_analyzer import DocAnalyzer

# Shared Actions that might be used by both agents
class ExtractContentBlocksAction(Action):
    """Extract code blocks and text paragraphs from a document"""
    
    async def run(self, content: str):
        """Extract code blocks and text paragraphs from the document"""
        # Extract code blocks (sections between ``` markers)
        code_block_pattern = r'```[^\n]*\n(.*?)```'
        code_blocks = re.findall(code_block_pattern, content, re.DOTALL)
        
        # Replace code blocks then extract text paragraphs (consecutive non-empty lines)
        content_without_code = re.sub(code_block_pattern, '[CODE_BLOCK]', content, flags=re.DOTALL)
        
        # Split by empty lines to get paragraphs
        paragraphs = []
        for block in re.split(r'\n\s*\n', content_without_code):
            block = block.strip()
            if block and '[CODE_BLOCK]' not in block:
                paragraphs.append(block)
        
        return code_blocks, paragraphs

# Document Checker Actions
class CheckDocStructureAction(Action):
    """Check document directory structure differences"""
    
    async def run(self, base_path: Path, lang_dirs: list):
        """Check and compare document structure across language directories"""
        structure = {}
        for lang in lang_dirs:
            lang_path = base_path / lang
            if lang_path.exists():
                files = [str(p.relative_to(lang_path)) for p in lang_path.rglob('*.md')]
                structure[lang] = set(files)
            else:
                structure[lang] = set()
        return structure

class CompareDocumentAction(Action):
    """Compare documents and identify differences"""
    
    DOCUMENT_COMPARISON_PROMPT: ClassVar[str] = """
    Compare the following documents in two languages and identify difference types:
    
    ## Source Document ({source_lang}):
    {source_content}
    
    ## Target Document ({target_lang}):
    {target_content}
    
    ## Requirements:
    1. Check if the target document is missing any content (whole paragraphs, parts of paragraphs, or any content)
    2. Check if the target document's translation has any inaccurate or inappropriate parts
    
    ## Return Format:
    Return only the JSON result without any additional explanation:
    {{
        "has_missing_content": true/false,
        "has_translation_issues": true/false,
        "needs_improvement": true/false  // true if either of the above is true
    }}
    """
    
    def _remove_tags(self, content: str) -> str:
        """Remove specific tags using regex"""
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """Compare two documents and check for differences"""
        # Use DocAnalyzer for additional checks
        analyzer = DocAnalyzer()
        
        source_content = source_path.read_text(encoding='utf-8')
        target_content = target_path.read_text(encoding='utf-8')
        
        # Basic analysis with DocAnalyzer
        missing_content = analyzer.is_missing_significant_content(source_content, target_content)
        translation_issues = analyzer.check_common_translation_issues(source_content, target_content)
        similarity = analyzer.calculate_similarity(source_content, target_content)
        
        # For more detailed analysis, use LLM
        if similarity < 0.95:  # Only use LLM for documents with significant differences
            comparison_response = await self._aask(
                self.DOCUMENT_COMPARISON_PROMPT.format(
                    source_lang=source_lang,
                    source_content=source_content,
                    target_lang=target_lang,
                    target_content=target_content
                )
            )
            
            try:
                # Clean and parse response
                cleaned_response = self._remove_tags(comparison_response)
                
                try:
                    result = json.loads(cleaned_response)
                except json.JSONDecodeError:
                    # Try to extract JSON portion
                    json_match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', cleaned_response)
                    if json_match:
                        try:
                            result = json.loads(json_match.group(0))
                        except json.JSONDecodeError:
                            raise ValueError("Cannot parse extracted JSON content")
                    else:
                        raise ValueError("Cannot find valid JSON format in response")
                
                # Ensure all required keys are present
                required_keys = ["has_missing_content", "has_translation_issues", "needs_improvement"]
                for key in required_keys:
                    if key not in result:
                        if key == "needs_improvement":
                            result[key] = result.get("has_missing_content", False) or result.get("has_translation_issues", False)
                        else:
                            result[key] = False
            except Exception as e:
                # Fallback to analyzer results
                result = {
                    "has_missing_content": missing_content,
                    "has_translation_issues": translation_issues,
                    "needs_improvement": missing_content or translation_issues or similarity < 0.8,
                    "error": str(e)
                }
        else:
            # Use analyzer results directly for high similarity documents
            result = {
                "has_missing_content": missing_content,
                "has_translation_issues": translation_issues,
                "needs_improvement": missing_content or translation_issues
            }
            
        # Add similarity score for reference
        result["similarity"] = similarity
        return result

# Document Translator Actions
class TranslationAction(Action):
    """Execute document translation"""
    PROMPT_TEMPLATE: ClassVar[str] = """
    Translate the following {source_lang} document accurately into {target_lang}, maintaining professional tone and technical accuracy.
    Preserve all original formatting, markups, and structure.
    For longer content, ensure complete translation of each paragraph without omission or simplification.
    Provide only the translation output without additional comments:
    
    {content}
    """
    
    IMPROVEMENT_PROMPT_TEMPLATE: ClassVar[str] = """
    Improve the following {target_lang} translation document to more accurately reflect the {source_lang} original content.
    
    Original ({source_lang}):
    {source_content}
    
    Existing Translation ({target_lang}):
    {target_content}
    
    Requirements:
    1. Preserve correct and appropriate parts of the existing translation
    2. Correct inaccurate or inappropriate translation parts
    3. Add content present in the original but missing in the translation
    4. Maintain all original formatting, markups, and structure
    
    Output the complete improved document, not just the changed parts:
    """
    
    def _remove_tags(self, content: str) -> str:
        """Remove specific tags using regex"""
        return re.sub(r'<think>[^<]*?</think>', '', content, flags=re.DOTALL)
    
    async def run(self, content: str, source_lang: str, target_lang: str, existing_translation: str = None):
        """Execute translation or improve existing translation"""
        if existing_translation:
            # Improvement mode with existing translation
            result = await self._aask(
                self.IMPROVEMENT_PROMPT_TEMPLATE.format(
                    source_content=content,
                    source_lang=source_lang,
                    target_content=existing_translation,
                    target_lang=target_lang
                )
            )
        else:
            # New translation
            result = await self._aask(
                self.PROMPT_TEMPLATE.format(
                    content=content,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
            )
        
        # Remove special tags before returning
        return self._remove_tags(result)

# Main Roles
class DocumentChecker(Role):
    """Document Checker Role - responsible for checking document consistency and identifying issues"""
    
    def __init__(self, translator_role=None):
        super().__init__()
        self.translator_role = translator_role
        self.set_actions([
            CheckDocStructureAction,
            CompareDocumentAction
        ])
    
    def set_translator(self, translator_role):
        """Set the translator role for communication"""
        self.translator_role = translator_role
    
    def _find_missing_files(self, structure: dict) -> Dict[str, Set[str]]:
        """Find missing files across language directories"""
        all_files = set().union(*structure.values()) if structure.values() else set()
        missing = {}
        for lang in structure:
            missing[lang] = all_files - structure[lang]
        return missing
    
    async def check_doc_structure(self, base_path: Path, lang_dirs: list):
        """Check document structure and identify missing files"""
        structure = await CheckDocStructureAction().run(base_path, lang_dirs)
        missing_files = self._find_missing_files(structure)
        return structure, missing_files
    
    async def check_doc_content(self, base_path: Path, structure: dict, primary_lang: str):
        """Check document content consistency across languages"""
        results = []
        
        # Get all common files
        common_files = {}
        all_files = set().union(*structure.values()) if structure.values() else set()
        
        # For each file, find which languages it exists in
        for file in all_files:
            langs = [lang for lang in structure if file in structure[lang]]
            if len(langs) > 1:  # At least two languages have this file
                common_files[file] = langs
        
        # Compare each common file across language versions
        for file, langs in common_files.items():
            source_path = base_path / primary_lang / file
            
            # Skip files that don't exist in the primary language
            if not source_path.exists() or primary_lang not in langs:
                continue
                
            for target_lang in langs:
                if target_lang == primary_lang:
                    continue
                    
                target_path = base_path / target_lang / file
                
                # Compare documents
                comparison_result = await CompareDocumentAction().run(
                    source_path, 
                    target_path, 
                    primary_lang, 
                    target_lang
                )
                
                # Store result with file paths
                results.append({
                    "file": file,
                    "source_lang": primary_lang,
                    "target_lang": target_lang,
                    "source_path": source_path,
                    "target_path": target_path,
                    "comparison": comparison_result
                })
        
        return results
    
    async def run_document_check(self, base_path: Path, lang_dirs: list, primary_lang: str = "en"):
        """Run full document structure and content check"""
        print("🔍 Document Checker: Starting document check...")
        
        # Check structure
        structure, missing_files = await self.check_doc_structure(base_path, lang_dirs)
        
        # Check content of existing files
        content_results = await self.check_doc_content(base_path, structure, primary_lang)
        
        print(f"🔍 Document Checker: Found {sum(len(files) for files in missing_files.values())} missing files")
        print(f"🔍 Document Checker: Completed {len(content_results)} content comparisons")
        
        # Return complete results
        return {
            "structure": structure,
            "missing_files": missing_files,
            "content_results": content_results
        }
        
    async def process_and_request_translations(self, check_results, base_path: Path):
        """Process check results and request translations when needed"""
        if not self.translator_role:
            print("❌ Document Checker: No translator role set!")
            return
            
        # Process missing files first
        missing_count = 0
        for target_lang, files in check_results["missing_files"].items():
            for file in files:
                # Find a source language that has this file
                source_lang = None
                source_path = None
                
                for lang in check_results["structure"]:
                    if file in check_results["structure"][lang] and lang != target_lang:
                        source_lang = lang
                        source_path = base_path / lang / file
                        break
                
                if source_lang and source_path and source_path.exists():
                    target_path = base_path / target_lang / file
                    
                    # Request translation for missing file
                    source_content = source_path.read_text(encoding='utf-8')
                    await self.translator_role.handle_translation_request(
                        source_content=source_content,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        target_path=target_path,
                        existing_translation=None  # No existing translation
                    )
                    missing_count += 1
        
        # Then process content improvements
        improvement_count = 0
        for result in check_results["content_results"]:
            if result["comparison"].get("needs_improvement", False):
                source_path = result["source_path"]
                target_path = result["target_path"]
                
                # Request translation improvement
                source_content = source_path.read_text(encoding='utf-8')
                target_content = target_path.read_text(encoding='utf-8')
                
                await self.translator_role.handle_translation_request(
                    source_content=source_content,
                    source_lang=result["source_lang"],
                    target_lang=result["target_lang"],
                    target_path=target_path,
                    existing_translation=target_content
                )
                improvement_count += 1
        
        print(f"🔍 Document Checker: Requested {missing_count} new translations and {improvement_count} translation improvements")

class DocumentTranslator(Role):
    """Document Translator Role - handles translation and translation improvement"""
    
    def __init__(self):
        super().__init__()
        self.set_actions([
            TranslationAction
        ])
        self.translations_completed = 0
        self.improvements_completed = 0
    
    async def handle_translation_request(self, source_content: str, source_lang: str, 
                                        target_lang: str, target_path: Path, 
                                        existing_translation: Optional[str] = None):
        """Handle translation request from the checker"""
        print(f"🌐 Document Translator: Received {'improvement' if existing_translation else 'translation'} request for {target_path}")
        
        # Perform translation or improvement
        result = await TranslationAction().run(
            source_content, 
            source_lang, 
            target_lang, 
            existing_translation
        )
        
        # Save the result
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(result, encoding='utf-8')
        
        # Update counters
        if existing_translation:
            self.improvements_completed += 1
            print(f"🌐 Document Translator: Improved translation saved to {target_path}")
        else:
            self.translations_completed += 1
            print(f"🌐 Document Translator: New translation saved to {target_path}")
        
        return {
            "target_path": target_path,
            "is_improvement": existing_translation is not None,
            "success": True
        }
    
    async def get_status(self):
        """Get the current status of translations"""
        return {
            "translations_completed": self.translations_completed,
            "improvements_completed": self.improvements_completed
        }

# Main coordinator function
async def run_document_maintenance(base_path: Path, lang_dirs: list, primary_lang: str = "en"):
    """Run the document maintenance process with multiple agents"""
    print(f"📚 Starting Multi-Agent Document Maintenance for {base_path}")
    print(f"   Languages: {', '.join(lang_dirs)}")
    print(f"   Primary Language: {primary_lang}")
    
    # Create the agents
    translator = DocumentTranslator()
    checker = DocumentChecker()
    checker.set_translator(translator)
    
    # Run the document check
    check_results = await checker.run_document_check(base_path, lang_dirs, primary_lang)
    
    # Process results and request translations
    await checker.process_and_request_translations(check_results, base_path)
    
    # Get final status
    translator_status = await translator.get_status()
    
    print("\n📊 Document Maintenance Summary:")
    print(f"   New Translations: {translator_status['translations_completed']}")
    print(f"   Improved Translations: {translator_status['improvements_completed']}")
    print(f"   Total Files Processed: {translator_status['translations_completed'] + translator_status['improvements_completed']}")
    
    return check_results, translator_status

# Example usage
if __name__ == "__main__":
    async def main():
        # Example usage with command-line arguments
        import argparse
        
        parser = argparse.ArgumentParser(description="Multi-Agent Document Maintenance System")
        parser.add_argument("--path", type=str, default="./test", help="Base path for documentation")
        parser.add_argument("--langs", type=str, default="en,zh", help="Comma-separated language directories")
        parser.add_argument("--primary", type=str, default="en", help="Primary language for comparisons")
        
        args = parser.parse_args()
        
        base_path = Path(args.path)
        lang_dirs = args.langs.split(",")
        primary_lang = args.primary
        
        await run_document_maintenance(base_path, lang_dirs, primary_lang)
    
    asyncio.run(main())
