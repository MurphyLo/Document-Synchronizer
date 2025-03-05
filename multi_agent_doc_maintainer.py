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
import logging
from datetime import datetime
from colorama import Fore, Style, init
import argparse
import sys

# Initialize colorama to support Windows color output
init()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('MultiAgentDocMaintainer')

# Add file handler to write logs to file
file_handler = logging.FileHandler('multi_agent_doc_maintainer.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)


# Document Checker Actions
class CheckDocStructureAction(Action):
    """Check document directory structure differences"""
    
    async def run(self, base_path: Path, lang_dirs: list):
        """Check and compare document structure across language directories"""
        structure = {}
        for lang in lang_dirs:
            lang_path = base_path / lang
            if not lang_path.exists():
                logger.warning(f"{Fore.YELLOW}Language directory doesn't exist: {lang_path}{Style.RESET_ALL}")
                structure[lang] = set()
                continue
                
            files = [str(p.relative_to(lang_path)) for p in lang_path.rglob('*.md')]
            structure[lang] = set(files)
            logger.info(f"{Fore.GREEN}Scanned {lang} directory: found {len(files)} documents{Style.RESET_ALL}")
        return structure

class CompareDocumentAction(Action):
    """Compare documents and identify differences"""
    
    DOCUMENT_COMPARISON_PROMPT: ClassVar[str] = """
    Compare the following documents in two languages and determine if there are any significant differences:
    
    ## Source Document ({source_lang}):
    {source_content}
    
    ## Target Document ({target_lang}):
    {target_content}
    
    ## Requirements:
    1. Check if there are any meaningful differences between the documents
    2. Stop analysis as soon as you find a clear difference
    
    ## Return Format:
    Return only the JSON result without any additional explanation:
    {{
        "has_differences": true/false
    }}
    """
    
    def _remove_tags(self, content: str) -> str:
        """Remove specific tags using regex"""
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)
    
    async def run(self, source_path: Path, target_path: Path, source_lang: str, target_lang: str):
        """Compare two documents and check for differences"""
        logger.debug(f"Comparing documents: {source_path.name} ({source_lang} vs {target_lang})")
        
        source_content = source_path.read_text(encoding='utf-8')
        target_content = target_path.read_text(encoding='utf-8')
        
        # Use LLM for document comparison
        comparison_response = await self._aask(
            self.DOCUMENT_COMPARISON_PROMPT.format(
                source_lang=source_lang,
                source_content=source_content,
                target_lang=target_lang,
                target_content=target_content
            )
        )
        
        # Process LLM response
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
            
            # Ensure the required key is present
            if "has_differences" not in result:
                result["has_differences"] = False
                        
            return result
            
        except Exception as e:
            # Return default structure on error
            logger.error(f"{Fore.RED}Failed to parse comparison result: {e}{Style.RESET_ALL}")
            logger.debug(f"Original response: {comparison_response[:200]}...")
            
            return {
                "has_differences": False,
                "error": str(e)
            }

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
        return re.sub(r'<think>[^<]*?</think>\n\n', '', content, flags=re.DOTALL)
    
    async def run(self, content: str, source_lang: str, target_lang: str, existing_translation: str = None):
        """Execute translation or improve existing translation"""
        logger.info(f"Executing {Fore.BLUE}{'translation improvement' if existing_translation else 'new translation'}{Style.RESET_ALL}: {source_lang} → {target_lang}")
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
        logger.info(f"{Fore.CYAN}🔍 Document Checker: Starting document check...{Style.RESET_ALL}")
        
        # Check structure
        structure, missing_files = await self.check_doc_structure(base_path, lang_dirs)
        
        # Check content of existing files
        content_results = await self.check_doc_content(base_path, structure, primary_lang)
        
        total_missing = sum(len(files) for files in missing_files.values())
        logger.info(f"{Fore.YELLOW}🔍 Document Checker: Found {total_missing} missing files{Style.RESET_ALL}")
        logger.info(f"{Fore.GREEN}🔍 Document Checker: Completed {len(content_results)} content comparisons{Style.RESET_ALL}")
        
        # Return complete results
        return {
            "structure": structure,
            "missing_files": missing_files,
            "content_results": content_results
        }
        
    async def process_and_request_translations(self, check_results, base_path: Path):
        """Process check results and request translations when needed"""
        if not self.translator_role:
            logger.error(f"{Fore.RED}❌ Document Checker: No translator role set!{Style.RESET_ALL}")
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
            if result["comparison"].get("has_differences", False):
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
        
        logger.info(f"{Fore.GREEN}🔍 Document Checker: Requested {missing_count} new translations and {improvement_count} translation improvements{Style.RESET_ALL}")

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
        logger.info(f"{Fore.BLUE}🌐 Document Translator: Received {'improvement' if existing_translation else 'translation'} request for {target_path}{Style.RESET_ALL}")
        
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
            logger.info(f"{Fore.GREEN}🌐 Document Translator: Improved translation saved to {target_path}{Style.RESET_ALL}")
        else:
            self.translations_completed += 1
            logger.info(f"{Fore.GREEN}🌐 Document Translator: New translation saved to {target_path}{Style.RESET_ALL}")
        
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
async def run_document_maintenance(base_path: Path, lang_dirs: list, primary_lang: str = "en", dry_run: bool = False, verbose: bool = False):
    """Run the document maintenance process with multiple agents"""
    if verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}📚 Starting Multi-Agent Document Maintenance{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}Base path: {base_path}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}Languages: {', '.join(lang_dirs)}{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}Primary Language: {primary_lang}{Style.RESET_ALL}")
    
    if dry_run:
        logger.info(f"{Fore.YELLOW}[DRY RUN MODE] No files will be modified{Style.RESET_ALL}")
    
    logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
    
    start_time = datetime.now()
    
    # Create the agents
    translator = DocumentTranslator()
    checker = DocumentChecker()
    checker.set_translator(translator)
    
    try:
        # Run the document check
        check_results = await checker.run_document_check(base_path, lang_dirs, primary_lang)
        
        # Log files needing improvement
        differences_count = sum(1 for result in check_results["content_results"] 
                            if result["comparison"].get("has_differences", False))
        logger.info(f"{Fore.YELLOW}🔍 Document Checker: Found {differences_count} files with differences{Style.RESET_ALL}")
        
        # Process results and request translations
        if not dry_run:
            await checker.process_and_request_translations(check_results, base_path)
        else:
            logger.info(f"{Fore.YELLOW}[DRY RUN] Would have processed translation requests{Style.RESET_ALL}")
        
        # Get final status
        translator_status = await translator.get_status()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
        logger.info(f"{Fore.CYAN}📊 Document Maintenance Summary (Duration: {duration:.1f}s):{Style.RESET_ALL}")
        logger.info(f"   - New Translations: {translator_status['translations_completed']}")
        logger.info(f"   - Improved Translations: {translator_status['improvements_completed']}")
        logger.info(f"   - Total Files Processed: {translator_status['translations_completed'] + translator_status['improvements_completed']}")
        logger.info(f"{Fore.CYAN}========================================{Style.RESET_ALL}")
        
        return check_results, translator_status
    except Exception as e:
        logger.error(f"{Fore.RED}Error during document maintenance: {e}{Style.RESET_ALL}")
        import traceback
        logger.debug(traceback.format_exc())
        return {"error": str(e)}, {"error": str(e)}

def setup_argparse():
    """Set up command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Document Maintenance System - Check and synchronize multi-language documentation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument("-p", "--path", type=str, default="./examples",
                      help="Base path for documentation")
                      
    parser.add_argument("-l", "--langs", type=str, default="en,zh",
                      help="Comma-separated language directories")
                      
    parser.add_argument("-m", "--primary", type=str, default="en",
                      help="Primary language for comparisons")
                      
    parser.add_argument("-v", "--verbose", action="store_true",
                      help="Display verbose output")
                      
    parser.add_argument("-d", "--dry-run", action="store_true",
                      help="Dry run mode, don't modify files")
                      
    return parser

# Example usage
if __name__ == "__main__":
    async def main():
        parser = setup_argparse()
        args = parser.parse_args()
        
        base_path = Path(args.path)
        lang_dirs = args.langs.split(",")
        primary_lang = args.primary
        
        await run_document_maintenance(
            base_path,
            lang_dirs,
            primary_lang,
            args.dry_run,
            args.verbose
        )
    
    asyncio.run(main())
