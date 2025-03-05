# Document Synchronizer

A powerful tool for maintaining multi-language documentation consistency. This project provides utilities to ensure your documentation in different languages stays synchronized and up-to-date.

This tool is an agent-based multilingual document synchronization system built on the MetaGPT framework. It leverages LLM-powered agents to intelligently analyze, compare, and translate documentation across multiple languages, ensuring consistency while maintaining the technical accuracy and nuance of specialized content.

## Features

- **Document Structure Checking**: Identifies missing files across language directories
- **Content Comparison**: Detects differences between document versions in different languages
- **Automatic Translation**: Generates translations for missing documents
- **Translation Improvement**: Updates existing translations to match the source content
- **Multi-Agent System**: Advanced option with separate roles for checking and translating
- **Dry-Run Mode**: Preview changes without modifying files
- **Comprehensive Logging**: Console and file-based logging

## Installation

### Prerequisites

- Python 3.9+ (required by MetaGPT)
- MetaGPT library
- Internet connection for API access

> **Note**: This code was developed and tested using Python 3.11.

### Setup
1. Clone this repository:
    ```bash
    git clone https://github.com/gly11/Document-Synchronizer.git
    cd Document-Synchronizer
    ```

2. Install MetaGPT following the [official installation guide](https://github.com/geekan/MetaGPT)

3. Configure API access according to [MetaGPT documentation](https://github.com/geekan/MetaGPT?tab=readme-ov-file#configuration)

4. Install additional dependencies:
    ```bash
    pip install colorama
    ```
    
    > **Note**: colorama is used for better log display and terminal output formatting

## Usage

### Basic Document Maintainer

The `doc_maintainer.py` script provides a straightforward approach to document maintenance:

```bash
python doc_maintainer.py --path ./docs --langs en,zh,es --primary en
```

### Multi-Agent Document Maintainer

The `multi_agent_doc_maintainer.py` script offers an advanced multi-agent approach:

```bash
python multi_agent_doc_maintainer.py --path ./docs --langs en,zh,es --primary en
```

### Command Line Options

Both scripts support the following options:

| Option | Description | Default |
|--------|-------------|---------|
| `-p, --path` | Base path for documentation | `./examples` |
| `-l, --langs` | Comma-separated language directories | `en,zh` |
| `-m, --primary` | Primary language for comparisons | `en` |
| `-v, --verbose` | Display verbose output | `False` |
| `-d, --dry-run` | Dry run mode, don't modify files | `False` |

## How It Works

1. **Scanning**: The tool scans all language directories for markdown files
2. **Structure Analysis**: Identifies which files are missing in each language
3. **Content Comparison**: For files that exist in multiple languages, compares content for differences
4. **Translation**: Generates translations for missing files or outdated content
5. **Reporting**: Provides detailed statistics about the documentation state

## Example Workflow

```bash
# Check documentation structure and preview changes
python doc_maintainer.py --path ./project-docs --langs en,zh,ja,fr --primary en --dry-run

# Apply changes to synchronize all documentation
python doc_maintainer.py --path ./project-docs --langs en,zh,ja,fr --primary en
```

## Choosing Between Scripts

- `doc_maintainer.py` - Simpler implementation, good for most use cases
- `multi_agent_doc_maintainer.py` - More advanced with separate agent roles, better for complex documentation

## Logs

Both tools generate logs in their respective log files:
- `doc_maintainer.log`
- `multi_agent_doc_maintainer.log`

These provide detailed information about the operations performed during execution.

## License

[MIT License](LICENSE)
