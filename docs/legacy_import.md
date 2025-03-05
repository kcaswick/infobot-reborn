# Legacy Infobot Data Import

This document outlines our approach to importing data from legacy Infobot installations into Infobot Reborn.

## Legacy Data Format

The original Infobot stored data in several key formats:

1. **Factual Knowledge**: Stored in `.txt` files (and accompanying DBM files):
   - `<botname>-is.txt` - Contains "X is Y" statements
   - `<botname>-are.txt` - Contains "X are Y" statements

2. **Karma/Reputation**: Stored in `<botname>-karma.txt` - Records positive/negative scores for entities

3. **User Seen Data**: Stored in `<botname>-seen.txt` - Records when users were last active

4. **Ignored Items**: Stored in `<botname>-ignore.txt` - Lists items the bot should ignore

5. **Configuration**: Stored in `conf/infobot.config` - Bot settings and behavioral parameters

Each line in the knowledge files typically follows formats like:
- For "is" facts: `topic => information`
- For "are" facts: `topic => information`

## Import Process

Our importer will:

1. Parse the legacy text files (bypassing the DBM files which are binary)
2. Transform the data into our modern storage format
3. Apply validation and cleaning rules
4. Import to our knowledge base

## Data Cleaning

A critical part of the import process is cleaning the legacy data:

1. **Removing Sentence Fragments**: Legacy Infobots often accumulated random sentence fragments and partial conversations
2. **Converting IRC Formatting to Markdown**:
   - Bold: `\x02text\x02` → `**text**`
   - Italic: `\x1Dtext\x1D` → `*text*`
   - Underline: `\x1Ftext\x1F` → `__text__`
   - Color codes: `\x03nn,mm` → Remove entirely
3. **Quality Filtering**: Score entries by likely usefulness using heuristics
4. **Entity Normalization**: Standardize entity references
5. **Contextual Analysis**: Use LLM to identify actual factual information vs. conversational noise
6. **Deduplication**: Merge redundant or highly similar entries

## Implementation Plan

1. Create a `legacy_import.py` module to handle importing from Infobot installations
2. Implement parsers for each data file format
3. Build transformation logic to convert legacy data to new schema
4. Provide CLI command for importing: `python -m infobot_reborn.tools.legacy_import /path/to/infobot/data`

## Example Parser Implementation

For the core "is" and "are" facts:

```python
def parse_factoid_file(file_path: str) -> list[dict]:
    """Parse a legacy Infobot factoid file into structured data."""
    facts = []
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                if '=>' in line:
                    topic, info = line.split('=>', 1)
                    facts.append({
                        'topic': topic.strip(),
                        'information': info.strip(),
                        'source_file': os.path.basename(file_path)
                    })
            except Exception as e:
                logger.warning(f"Error parsing line: {line}. Error: {e}")
    return facts

def convert_irc_to_markdown(text: str) -> str:
    """Convert IRC formatting codes to Markdown."""
    # Bold: \x02text\x02 -> **text**
    text = re.sub(r'\x02(.*?)\x02', r'**\1**', text)
    # Italic: \x1Dtext\x1D -> *text*
    text = re.sub(r'\x1D(.*?)\x1D', r'*\1*', text)
    # Underline: \x1Ftext\x1F -> __text__
    text = re.sub(r'\x1F(.*?)\x1F', r'__\1__', text)
    # Remove color codes: \x03nn,mm
    text = re.sub(r'\x03\d+(?:,\d+)?', '', text)
    # Remove other control characters
    text = re.sub(r'[\x00-\x1F]', '', text)
    return text

def clean_factoid(factoid: dict) -> dict:
    """Clean a factoid entry and determine if it's valid."""
    # Apply markdown conversion
    factoid['information'] = convert_irc_to_markdown(factoid['information'])
    factoid['topic'] = convert_irc_to_markdown(factoid['topic'])
    
    # Apply quality heuristics
    factoid['quality_score'] = calculate_quality_score(factoid)
    factoid['is_valid'] = factoid['quality_score'] > QUALITY_THRESHOLD
    
    return factoid
```

## LLM-Assisted Cleaning

For particularly challenging or ambiguous entries, we'll use an LLM-based approach:

```python
async def enhance_with_llm(factoid: dict) -> dict:
    """Use LLM to improve and validate a factoid."""
    prompt = f"""
    Review this potential factoid from a legacy chatbot:
    Topic: {factoid['topic']}
    Information: {factoid['information']}
    
    1. Is this a genuine factual statement (vs. conversation fragment)?
    2. If factual, rewrite it to be more accurate and clear.
    3. Return JSON with keys: is_factual (bool), cleaned_info (str if factual)
    """
    
    response = await llm_client.generate(prompt)
    result = json.loads(response)
    
    factoid['is_factual'] = result['is_factual']
    if result['is_factual']:
        factoid['enhanced_information'] = result['cleaned_info']
    
    return factoid
```

## Usage Example

```bash
# Import from a legacy Infobot installation
python -m infobot_reborn.tools.legacy_import --source ~/Egor-try1/ --output ./data/imported/ --clean-level=high
```

This will create a new dataset in our modern format while preserving the original knowledge, with extensive cleaning applied to improve quality.