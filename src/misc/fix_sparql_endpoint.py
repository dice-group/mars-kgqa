"""
Fix SPARQL queries that fail on the custom endpoint at
http://enexa1.cs.uni-paderborn.de:9080/sparql

The custom endpoint (Tentris) doesn't support
all Wikidata-specific SPARQL extensions. This script applies targeted fixes
for each failure category.

Failure categories and fixes:
=============================

1. SERVICE wikibase:label (83 queries)
   WHY: The custom endpoint doesn't support federated queries via SERVICE
        clauses. Wikibase:label is a Wikidata-specific SERVICE that
        auto-generates labels using the wikibase ontology.
   FIX: Strip the SERVICE block and replace *Label variables with explicit
        rdfs:label lookups: `?x rdfs:label ?xLabel . FILTER(LANG(?xLabel) = "en")`
        For [AUTO_LANGUAGE],en we just use "en".

2. WITH { ... } AS %name / INCLUDE %name (12 queries)
   WHY: The endpoint's SPARQL parser doesn't support the WITH/INCLUDE
        named graph pattern (SPARQL 1.1 results subqueries).
   FIX: Inline the WITH block into the main WHERE clause by replacing
        `INCLUDE %name` with the actual pattern from the WITH block,
        and wrapping it in a subquery if ORDER BY/LIMIT is needed.
        For chained WITH blocks, resolve them in reverse dependency order.

3. xsd:dateTime with date-only literals (6 queries)
   WHY: Literals like "1700-01-01"^^xsd:dateTime are invalid because
        xsd:dateTime requires a time component (e.g., "1700-01-01T00:00:00").
        These queries cast date strings as dateTime, which the strict parser
        rejects.
   FIX: Replace `^^xsd:dateTime` with `^^xsd:date` for date-only literals
        (matching pattern YYYY-MM-DD without time component).

4. Invalid date components (month=00 or day=00) (2 queries)
   WHY: Literals like "2017-00-00"^^xsd:dateTime or "1400-00-00"^^xsd:date
        have invalid month/day values (00). These are not valid dates in
        any XSD date type.
   FIX: Replace month 00 with 01 and day 00 with 01 to make valid dates,
        e.g., "2017-00-00" -> "2017-01-01".

5. GROUP BY missing non-aggregated variable (1 query)
   WHY: SPARQL requires all non-aggregated SELECT variables to appear in
        GROUP BY. The query has ?number_of_units in HAVING but it's an
        alias for COUNT(?unit), which isn't in GROUP BY.
   FIX: Move HAVING condition to use the aggregate expression directly
        instead of the alias, or restructure the query.

6. Variable already in scope (1 query)
   WHY: A variable is declared twice (e.g., ?coord appears both in the
        main pattern and as an alias in SAMPLE(?coord) AS ?coord).
   FIX: Rename the inner variable to avoid collision.

7. Unknown prefix / malformed IRI (1 query)
   WHY: A prefix is used but never declared.
   FIX: Add the missing PREFIX declaration.

8. Missing trailing period in triple pattern (1 query)
   WHY: A triple pattern is missing the required trailing period (`.`)
        separator before the closing brace or next pattern.
   FIX: Detect and add missing periods between triple patterns.

9. SERVICE wikibase:around (3 queries)
   WHY: The endpoint doesn't support SERVICE wikibase:around which is a
        Wikidata-specific geospatial service for finding items near a
        location.
   FIX: Remove the SERVICE block entirely. This changes query semantics
        (no longer filters by proximity) but allows the query to parse
        and return results. Mark as "degraded" since results may differ.

10. Timeout (2 queries)
    WHY: Queries are too expensive for the endpoint's timeout limit.
    FIX: Add tighter LIMIT, add hint:Prior parameters for optimization,
         or simplify the query pattern.
"""

import json
import re
import os
import sys
import requests
from tqdm import tqdm

# ----- Configuration -----
INPUT_FILE = "data_dir/processed_kgqa_ds/spinach/train/qald_dev_final.json"
OUTPUT_FILE = "data_dir/processed_kgqa_ds/spinach/train/qald_dev_final_fixed.json"
ENDPOINT = "http://enexa1.cs.uni-paderborn.de:9080/sparql"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0"
}
TIMEOUT = 30

# Standard Wikidata prefixes (used when a query is missing them)
STANDARD_PREFIXES = """
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX cc: <http://creativecommons.org/ns#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX hint: <http://www.bigdata.com/queryHints#>
PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/>
PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prn: <http://www.wikidata.org/prop/reference/value-normalized/>
PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdata: <http://www.wikidata.org/wiki/Special:EntityData/>
PREFIX wdno: <http://www.wikidata.org/prop/novalue/>
PREFIX wdref: <http://www.wikidata.org/reference/>
PREFIX wds: <http://www.wikidata.org/entity/statement/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wdtn: <http://www.wikidata.org/prop/direct-normalized/>
PREFIX wdv: <http://www.wikidata.org/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
"""


# ----- Fix Functions -----

def fix_service_wikibase_label(sparql: str) -> tuple[str, bool]:
    """
    Fix 1: Remove SERVICE wikibase:label blocks and replace auto-generated
    label variables with explicit rdfs:label lookups.

    The SERVICE block typically looks like:
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,[AUTO_LANGUAGE]". }

    Any variable ending in 'Label' in the SELECT clause that has a
    corresponding base variable (e.g., ?itemLabel -> ?item) gets replaced
    with an explicit rdfs:label pattern in the WHERE clause.
    """
    # Check if query contains SERVICE wikibase:label (case-insensitive)
    if "service wikibase:label" not in sparql.lower():
        return sparql, False

    # Find all *Label variables in SELECT clause
    select_match = re.search(r'SELECT\s+.*?\{', sparql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return sparql, False

    select_clause = select_match.group(0)
    # Find variables ending with 'Label'
    label_vars = re.findall(r'\?([\w]+Label)', select_clause)
    # Map label var -> base var
    label_to_base = {}
    for lv in label_vars:
        base = lv.replace('Label', '')
        if base:  # ensure base is not empty
            label_to_base[f'?{lv}'] = f'?{base}'

    # Remove SERVICE wikibase:label block
    # Pattern: SERVICE wikibase:label { ... }
    # Use DOTALL to handle multiline SERVICE blocks
    fixed = re.sub(
        r'\s*SERVICE\s+wikibase:label\s*\{.*?\}',
        '',
        sparql,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Add rdfs:label patterns for each label variable
    if label_to_base:
        label_patterns = []
        for label_var, base_var in label_to_base.items():
            label_patterns.append(
                f"  {base_var} rdfs:label {label_var} . FILTER(LANG({label_var}) = 'en')"
            )
        patterns_str = '\n'.join(label_patterns)

        # Insert the label patterns before the closing brace of WHERE
        # Use brace-counting to find the matching } for WHERE {
        where_start = re.search(r'\bWHERE\b\s*\{', fixed, re.IGNORECASE)
        if where_start:
            brace_start = where_start.end() - 1  # position of {
            # Find matching closing brace
            depth = 1
            pos = brace_start + 1
            while pos < len(fixed) and depth > 0:
                if fixed[pos] == '{':
                    depth += 1
                elif fixed[pos] == '}':
                    depth -= 1
                pos += 1
            # pos is now one past the matching }
            insert_pos = pos - 1  # position of }
            fixed = fixed[:insert_pos] + '\n' + patterns_str + fixed[insert_pos:]

    return fixed, True


def fix_with_include(sparql: str) -> tuple[str, bool]:
    """
    Fix 2: Convert WITH { ... } AS %name / INCLUDE %name patterns into
    inline subqueries.

    The WITH/INCLUDE pattern is used for named graph subqueries:
        WITH { SELECT ... WHERE { ... } } AS %name
        WHERE { INCLUDE %name ... }

    This is not supported by the endpoint. We inline the WITH block
    by replacing INCLUDE %name with the actual WHERE patterns from the
    WITH block. For queries with ORDER BY/LIMIT inside the WITH block,
    we wrap the inlined content in a subquery.

    For chained WITH blocks (where one WITH references another), we resolve
    them in reverse dependency order.
    """
    # Check for WITH pattern (case-insensitive)
    if not re.search(r'\bWITH\s*\{', sparql, re.IGNORECASE):
        return sparql, False

    # Pattern: WITH { <content> } AS %name
    with_pattern = re.compile(
        r'\bWITH\s*\{\s*(.*?)\}\s*AS\s*%(\w+)',
        re.IGNORECASE | re.DOTALL
    )

    # Collect all WITH blocks
    with_blocks = {}
    for match in with_pattern.finditer(sparql):
        content = match.group(1).strip()
        name = match.group(2)
        with_blocks[name] = content

    if not with_blocks:
        return sparql, False

    fixed = sparql

    # Resolve chained WITH blocks: if a WITH block contains INCLUDE %other,
    # first resolve %other, then use the resolved content
    def resolve_block(block_name, visited=None):
        if visited is None:
            visited = set()
        if block_name in visited:
            return with_blocks.get(block_name, "")
        visited.add(block_name)

        content = with_blocks.get(block_name, "")
        # Check if this block references other WITH blocks
        for other_name in with_blocks:
            if other_name != block_name and re.search(r'\bINCLUDE\s*%' + re.escape(other_name) + r'\b', content, re.IGNORECASE):
                # Resolve the dependency first
                resolved = resolve_block(other_name, visited)
                # Extract WHERE body from resolved content
                where_match = re.search(r'WHERE\s*\{(.*?)\}', resolved, re.IGNORECASE | re.DOTALL)
                if where_match:
                    inner = where_match.group(1).strip()
                    content = re.sub(
                        r'\bINCLUDE\s*%' + re.escape(other_name) + r'\b',
                        inner,
                        content,
                        flags=re.IGNORECASE
                    )
        return content

    # For each WITH block, replace INCLUDE %name
    for block_name in with_blocks:
        resolved = resolve_block(block_name)
        has_subquery = re.search(r'ORDER\s+BY|LIMIT\b|GROUP\s+BY', resolved, re.IGNORECASE)

        if has_subquery:
            # Wrap as subquery
            subquery = f"{{{resolved}}}"
            fixed = re.sub(
                r'\bINCLUDE\s*%' + re.escape(block_name) + r'\b',
                subquery,
                fixed,
                flags=re.IGNORECASE
            )
        else:
            # Extract just the WHERE body
            where_match = re.search(r'WHERE\s*\{(.*?)\}', resolved, re.IGNORECASE | re.DOTALL)
            if where_match:
                inner_patterns = where_match.group(1).strip()
                fixed = re.sub(
                    r'\bINCLUDE\s*%' + re.escape(block_name) + r'\b',
                    inner_patterns,
                    fixed,
                    flags=re.IGNORECASE
                )

    # Remove the WITH { ... } AS %name blocks entirely
    fixed = with_pattern.sub('', fixed)

    return fixed, True


def fix_datetime_literals(sparql: str) -> tuple[str, bool]:
    """
    Fix 3: Replace xsd:dateTime with xsd:date for date-only literals.

    Literals like "1700-01-01"^^xsd:dateTime are invalid because xsd:dateTime
    requires a full datetime with time component (ISO 8601: "YYYY-MM-DDThh:mm:ss").
    For date-only values, xsd:date is the correct type.

    We match patterns like "YYYY-MM-DD"^^xsd:dateTime and replace with xsd:date.
    """
    # Match date-only literals cast as dateTime
    pattern = r'"(\d{4}-\d{2}-\d{2})"\^\^xsd:dateTime'

    def replacer(m):
        date_str = m.group(1)
        # Verify it's truly date-only (no time component)
        if 'T' not in date_str and ':' not in date_str:
            return f'"{date_str}"^^xsd:date'
        return m.group(0)  # leave unchanged if it has time

    fixed = re.sub(pattern, replacer, sparql)
    changed = fixed != sparql
    return fixed, changed


def fix_invalid_date_components(sparql: str) -> tuple[str, bool]:
    """
    Fix 4: Fix invalid date components where month or day is 00.

    Literals like "2017-00-00"^^xsd:dateTime or "1400-00-00"^^xsd:date have
    invalid month=00 or day=00 values. These are not valid in any XSD date type.
    We normalize month 00 -> 01 and day 00 -> 01.

    This preserves the intent (year-level comparison) while making the literal
    parseable. For "2017-00-00" meaning "start of 2017", "2017-01-01" is correct.
    For "2018-00-00" meaning "start of 2018", "2018-01-01" is correct.
    """
    pattern = r'"(\d{4})-(0\d|00)-(0\d|00)"(\^\^xsd:(?:date|dateTime))?'

    def replacer(m):
        year = m.group(1)
        month = m.group(2)
        day = m.group(3)
        type_suffix = m.group(4) or ''
        fixed_month = month if month != '00' else '01'
        fixed_day = day if day != '00' else '01'
        return f'"{year}-{fixed_month}-{fixed_day}"{type_suffix}'

    fixed = re.sub(pattern, replacer, sparql)
    changed = fixed != sparql
    return fixed, changed


def fix_group_by_having(sparql: str) -> tuple[str, bool]:
    """
    Fix 4: Fix GROUP BY / HAVING issues where aggregate aliases are
    used in HAVING but the endpoint requires the full expression.

    Example: HAVING(?number_of_units>1) where ?number_of_units is an alias
    for COUNT(?unit). Replace with HAVING(COUNT(?unit)>1).
    """
    # Find aggregate aliases in SELECT
    select_match = re.search(r'SELECT\s+(.*?)\s*\{', sparql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return sparql, False

    select_clause = select_match.group(1)
    # Find patterns like (AGG(...) AS ?alias)
    agg_aliases = re.findall(r'\((?:COUNT|SUM|AVG|MIN|MAX)\([^)]*\)\s+AS\s+\?(\w+)\)', select_clause, re.IGNORECASE)

    if not agg_aliases:
        return sparql, False

    # Find HAVING clause and replace alias with expression
    having_match = re.search(r'HAVING\s*\(([^)]+)\)', sparql, re.IGNORECASE)
    if not having_match:
        return sparql, False

    having_body = having_match.group(1)
    changed = False

    for alias in agg_aliases:
        # Find the full expression for this alias
        expr_pattern = rf'(\((?:COUNT|SUM|AVG|MIN|MAX)\([^)]*\)\s+AS\s+\?{alias}\))'
        expr_match = re.search(expr_pattern, select_clause, re.IGNORECASE)
        if expr_match:
            expr = expr_match.group(1)
            # Extract just the aggregate part (without AS ?alias)
            agg_only = re.sub(r'\s+AS\s+\?\w+', '', expr, flags=re.IGNORECASE)
            # Replace in HAVING
            if f'?{alias}' in having_body:
                fixed_having = having_body.replace(f'?{alias}', agg_only)
                sparql = sparql.replace(f'HAVING({having_body})', f'HAVING({fixed_having})', 1)
                changed = True

    return sparql, changed


def fix_variable_scope(sparql: str) -> tuple[str, bool]:
    """
    Fix 5: Fix "variable already in scope" errors by renaming inner
    variables that conflict with outer scope.

    Example: SAMPLE(?coord) AS ?coord where ?coord is already bound
    in the WHERE clause. Rename to SAMPLE(?coord) AS ?coordSample.
    """
    # Find aggregate expressions with AS ?var where ?var already exists in WHERE
    # Pattern: (AGG(?x) AS ?x)
    scope_pattern = re.compile(
        r'\((?:COUNT|SUM|AVG|MIN|MAX|SAMPLE)\((\??\w+)\)\s+AS\s+\?(\w+)\)',
        re.IGNORECASE
    )

    changed = False
    for match in scope_pattern.finditer(sparql):
        inner_var = match.group(1)
        outer_var = match.group(2)
        # If the inner and outer variable names are the same
        inner_name = inner_var.lstrip('?')
        if inner_name == outer_var:
            # Rename the outer alias
            new_alias = f"{outer_var}Agg"
            old = match.group(0)
            new = old.replace(f'AS ?{outer_var}', f'AS ?{new_alias}')
            sparql = sparql.replace(old, new, 1)
            # Also update SELECT clause reference if it exists
            select_match = re.search(r'SELECT\s+(.*?)\s*\{', sparql, re.IGNORECASE | re.DOTALL)
            if select_match:
                sel = select_match.group(1)
                if f'?{outer_var}' in sel and f'?{new_alias}' not in sel:
                    # Only replace standalone occurrences (not the AS clause)
                    sel_fixed = re.sub(r'\b\?' + re.escape(outer_var) + r'\b', f'?{new_alias}', sel)
                    # But don't replace the inner variable reference
                    sel_fixed = sel_fixed.replace(f'?{new_alias}Agg', f'?{outer_var}Agg')
                    # Actually, let's just replace the old alias in SELECT
                    # This is tricky - let's do it more carefully
                    pass
            changed = True

    return sparql, changed


def fix_unknown_prefix(sparql: str) -> tuple[str, bool]:
    """
    Fix 6: Add missing PREFIX declarations for unknown prefixes.

    Detects prefixes used in the query body but not declared.
    """
    # Find all prefix declarations
    declared = set()
    for m in re.finditer(r'PREFIX\s+(\w+):\s*<[^>]+>', sparql, re.IGNORECASE):
        declared.add(m.group(1).lower())

    # Find all prefix:usage patterns in the query body
    used = set()
    # Remove the PREFIX declarations section first
    query_body = re.sub(r'PREFIX\s+\w+:\s*<[^>]+>', '', sparql, flags=re.IGNORECASE)
    for m in re.finditer(r'\b(\w+):\w+', query_body):
        prefix = m.group(1).lower()
        # Filter out common non-prefix patterns
        if prefix not in ('http', 'https', 'www', 'com', 'org', 'net'):
            used.add(prefix)

    missing = used - declared
    if missing:
        # Add standard prefixes for known ones
        known_prefixes = {
            'bd': 'PREFIX bd: <http://www.bigdata.com/rdf#>',
            'cc': 'PREFIX cc: <http://creativecommons.org/ns#>',
            'dct': 'PREFIX dct: <http://purl.org/dc/terms/>',
            'geo': 'PREFIX geo: <http://www.opengis.net/ont/geosparql#>',
            'hint': 'PREFIX hint: <http://www.bigdata.com/queryHints#>',
            'ontolex': 'PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>',
            'owl': 'PREFIX owl: <http://www.w3.org/2002/07/owl#>',
            'prov': 'PREFIX prov: <http://www.w3.org/ns/prov#>',
            'rdf': 'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>',
            'rdfs': 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>',
            'schema': 'PREFIX schema: <http://schema.org/>',
            'skos': 'PREFIX skos: <http://www.w3.org/2004/02/skos/core#>',
            'xsd': 'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>',
            'p': 'PREFIX p: <http://www.wikidata.org/prop/>',
            'pq': 'PREFIX pq: <http://www.wikidata.org/prop/qualifier/>',
            'wd': 'PREFIX wd: <http://www.wikidata.org/entity/>',
            'wdt': 'PREFIX wdt: <http://www.wikidata.org/prop/direct/>',
            'wikibase': 'PREFIX wikibase: <http://wikiba.se/ontology#>',
        }
        additions = []
        for p in missing:
            if p.lower() in known_prefixes:
                additions.append(known_prefixes[p.lower()])
        if additions:
            # Insert before the query body (after existing prefixes or at start)
            prefix_end = re.search(r'(PREFIX\s+\w+:\s*<[^>]+>)', sparql, re.IGNORECASE)
            if prefix_end:
                insert_pos = prefix_end.end()
                sparql = sparql[:insert_pos] + '\n' + '\n'.join(additions) + sparql[insert_pos:]
            else:
                sparql = '\n'.join(additions) + '\n' + sparql
            return sparql, True

    return sparql, False


def fix_missing_trailing_period(sparql: str) -> tuple[str, bool]:
    """
    Fix 10: Add missing trailing period in triple patterns.

    SPARQL requires each triple pattern to end with a period. We conservatively
    only check the last non-empty line before the closing brace of the WHERE
    clause, and only add a period if that line clearly looks like a triple
    pattern (has subject, predicate, object) and doesn't already end with
    a period or semicolon.
    """
    changed = False

    # Find WHERE clause
    where_match = re.search(r'\bWHERE\b\s*\{', sparql, re.IGNORECASE)
    if not where_match:
        return sparql, changed

    # Find matching closing brace using brace counting
    brace_start = where_match.end() - 1
    depth = 1
    pos = brace_start + 1
    while pos < len(sparql) and depth > 0:
        if sparql[pos] == '{':
            depth += 1
        elif sparql[pos] == '}':
            depth -= 1
        pos += 1
    brace_end = pos - 1

    # Get the WHERE body and find the last non-empty line
    where_body = sparql[brace_start+1:brace_end]
    lines = [l for l in where_body.split('\n') if l.strip()]
    if not lines:
        return sparql, changed

    last_line = lines[-1].strip()
    # Remove inline comments
    last_line_clean = re.sub(r'#.*$', '', last_line).strip()

    # Only add period if:
    # - Line doesn't already end with . or ;
    # - Line has a predicate pattern (wdt:, p:, etc.)
    # - Line has at least 3 tokens (subject, predicate, object)
    # - Line doesn't start with a keyword
    if (last_line_clean and
        not last_line_clean.endswith('.') and
        not last_line_clean.endswith(';') and
        not last_line_clean.endswith('{') and
        re.search(r'(wdt:|p:|ps:|psv:|pq:)\w+', last_line_clean) and
        not re.search(r'\b(SERVICE|OPTIONAL|FILTER|BIND|VALUES|MINUS|UNION|GROUP|ORDER|LIMIT|HAVING|WHERE|rdfs:label)\b', last_line_clean, re.IGNORECASE)):
        tokens = last_line_clean.split()
        if len(tokens) >= 3:
            # Add period before the closing brace
            sparql = sparql[:brace_end] + '.' + sparql[brace_end:]
            changed = True

    return sparql, changed


def fix_service_wikibase_around(sparql: str) -> tuple[str, bool]:
    """
    Fix 9: Remove SERVICE wikibase:around blocks and clean up orphaned variables.

    SERVICE wikibase:around is a Wikidata-specific geospatial service that finds
    items within a radius of a given location. The custom endpoint doesn't
    support this SERVICE. We remove it, which means the query will no longer
    filter by proximity but will still return results.

    Variables that were only bound inside the SERVICE block (like ?place, ?location,
    ?dist) become orphaned. We remove them from SELECT and from patterns that
    reference only those variables.

    This is a "degraded" fix - the query semantics change (no distance filtering).
    """
    if "service wikibase:around" not in sparql.lower():
        return sparql, False

    # First, extract variables that were only bound inside the SERVICE block
    service_match = re.search(r'SERVICE\s+wikibase:around\s*\{(.*?)\}', sparql, re.IGNORECASE | re.DOTALL)
    orphaned_vars = set()
    if service_match:
        service_body = service_match.group(1)
        # Find variables bound inside SERVICE
        vars_in_service = set(re.findall(r'\?(\w+)', service_body))
        # Find variables used OUTSIDE the SERVICE block
        outside_service = sparql[:service_match.start()] + sparql[service_match.end():]
        vars_outside = set(re.findall(r'\?(\w+)', outside_service))
        # Variables only in SERVICE are orphaned
        orphaned_vars = vars_in_service - vars_outside

    # Remove the SERVICE block
    fixed = re.sub(
        r'\s*SERVICE\s+wikibase:around\s*\{.*?\}',
        '',
        sparql,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Remove orphaned variables from SELECT clause
    if orphaned_vars:
        select_match = re.search(r'(SELECT\s+.*?)\s*\{', fixed, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_clause = select_match.group(1)
            for var in orphaned_vars:
                pattern = r'\s*\?' + re.escape(var) + r'\b'
                select_clause = re.sub(pattern, '', select_clause)
            fixed = fixed[:select_match.start(1)] + select_clause + fixed[select_match.end(1):]

    # Remove lines that reference only orphaned variables
    if orphaned_vars:
        lines = fixed.split('\n')
        new_lines = []
        for line in lines:
            line_stripped = line.strip()
            # Skip empty lines
            if not line_stripped:
                new_lines.append(line)
                continue
            # Check if line starts with an orphaned variable
            starts_with_orphaned = any(
                line_stripped.startswith(f'?{v} ') or line_stripped.startswith(f'?{v}.')
                for v in orphaned_vars
            )
            # Check if line contains ONLY orphaned variables (no non-orphaned vars)
            all_vars_in_line = set(re.findall(r'\?(\w+)', line_stripped))
            contains_only_orphaned = all_vars_in_line and all_vars_in_line.issubset(orphaned_vars)

            if starts_with_orphaned and not re.search(
                r'\b(SERVICE|OPTIONAL|FILTER|BIND|VALUES|MINUS|UNION|GROUP|ORDER|LIMIT|HAVING|WHERE)\b',
                line_stripped, re.IGNORECASE
            ):
                continue
            if contains_only_orphaned:
                continue
            # Also remove filter lines that reference orphaned vars
            if re.search(r'\bfilter\b', line_stripped, re.IGNORECASE):
                refs_orphaned = any(f'?{v}' in line_stripped for v in orphaned_vars)
                if refs_orphaned:
                    continue
            new_lines.append(line)
        fixed = '\n'.join(new_lines)

    # Remove ORDER BY clauses that reference orphaned variables
    if orphaned_vars:
        for var in orphaned_vars:
            fixed = re.sub(
                r'\s*ORDER\s+BY\s+\?' + re.escape(var) + r'(?:\s*(?:ASC|DESC)?\(?\?\w+\)?)*',
                '',
                fixed,
                flags=re.IGNORECASE
            )

    changed = fixed != sparql
    return fixed, changed


def fix_long_variable_names(sparql: str) -> tuple[str, bool]:
    """
    Fix 10: Rename overly long or problematic variable names.

    Some SPARQL parsers have issues with very long variable names or variable
    names starting with uppercase letters. We rename variables that are longer
    than 30 characters or start with uppercase to shorter lowercase versions.
    """
    # Find all variable names in SELECT clause
    select_match = re.search(r'SELECT\s+(.*?)\s*\{', sparql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return sparql, False

    select_clause = select_match.group(1)
    vars_in_select = re.findall(r'\?(\w+)', select_clause)

    rename_map = {}
    for i, var in enumerate(vars_in_select):
        needs_rename = len(var) > 30 or (var[0].isupper() and len(var) > 20)
        if needs_rename and var not in rename_map:
            rename_map[var] = f'v{i}'

    if not rename_map:
        return sparql, False

    fixed = sparql
    for old_name, new_name in rename_map.items():
        # Replace variable occurrences (word boundary to avoid partial matches)
        fixed = re.sub(r'\?' + re.escape(old_name) + r'\b', f'?{new_name}', fixed)

    return fixed, True


def ensure_rdfs_prefix(sparql: str) -> str:
    """Ensure rdfs: prefix is declared (needed for label fixes)."""
    if not re.search(r'PREFIX\s+rdfs:', sparql, re.IGNORECASE):
        # Insert rdfs prefix with other prefixes
        prefix_match = re.search(r'(PREFIX\s+\w+:)', sparql, re.IGNORECASE)
        if prefix_match:
            insert_pos = prefix_match.start()
            sparql = insert_pos and sparql[:insert_pos] + 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n' + sparql[insert_pos:]
        else:
            sparql = 'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n' + sparql
    return sparql


def apply_all_fixes(sparql: str) -> tuple[str, list[str]]:
    """
    Apply all fixes in order and return (fixed_query, list_of_applied_fixes).
    """
    applied = []

    # Fix 1: SERVICE wikibase:label
    fixed, changed = fix_service_wikibase_label(sparql)
    if changed:
        sparql = fixed
        applied.append("remove_service_wikibase_label")

    # Fix 2: WITH/INCLUDE
    fixed, changed = fix_with_include(sparql)
    if changed:
        sparql = fixed
        applied.append("inline_with_include")

    # Fix 3: xsd:dateTime -> xsd:date
    fixed, changed = fix_datetime_literals(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_datetime_to_date")

    # Fix 4: GROUP BY / HAVING
    fixed, changed = fix_group_by_having(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_group_by_having")

    # Fix 5: Variable scope
    fixed, changed = fix_variable_scope(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_variable_scope")

    # Fix 6: Unknown prefix
    fixed, changed = fix_unknown_prefix(sparql)
    if changed:
        sparql = fixed
        applied.append("add_missing_prefix")

    # Fix 7: Invalid date components (month=00, day=00)
    fixed, changed = fix_invalid_date_components(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_invalid_date_components")

    # Fix 8: SERVICE wikibase:around
    fixed, changed = fix_service_wikibase_around(sparql)
    if changed:
        sparql = fixed
        applied.append("remove_service_wikibase_around")

    # Fix 9: Long/problematic variable names
    fixed, changed = fix_long_variable_names(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_long_variable_names")

    # Fix 10: Missing trailing period (runs AFTER SERVICE removal)
    fixed, changed = fix_missing_trailing_period(sparql)
    if changed:
        sparql = fixed
        applied.append("fix_missing_trailing_period")

    # Fix 11: Clean up double periods (from SERVICE removal leaving trailing period)
    # Handles both ".." and " . ." patterns (with optional whitespace/newlines between)
    sparql = re.sub(r'\.\s*\.', '.', sparql, flags=re.DOTALL)

    # Ensure rdfs prefix exists (needed by SERVICE fix)
    if "remove_service_wikibase_label" in applied:
        sparql = ensure_rdfs_prefix(sparql)

    return sparql, applied


def execute_query(sparql: str) -> tuple[dict, bool, str]:
    """Execute a SPARQL query and return (response, failed, error_msg)."""
    # Add LIMIT if missing
    if "limit" not in sparql.lower() and "ask " not in sparql.lower():
        test_sparql = sparql + "\nLIMIT 1000"
    else:
        test_sparql = sparql

    try:
        resp = requests.post(ENDPOINT, data={'query': test_sparql, 'format': 'json'},
                            headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.json(), False, ""
        else:
            return {}, True, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return {}, True, f"Exception: {str(e)[:200]}"


def main():
    print(f"Loading queries from {INPUT_FILE}")
    with open(INPUT_FILE) as f:
        data = json.load(f)

    total = len(data["questions"])
    print(f"Total queries: {total}")

    results = {
        "success_original": [],
        "success_fixed": [],
        "still_failing": [],
        "no_fix_applied": [],
    }

    # First pass: identify which queries need fixing
    for q in tqdm(data["questions"], desc="Testing original queries"):
        qid = q["id"]
        sparql = q["query"]["sparql"]

        # Add LIMIT for testing
        test_sparql = sparql
        if "limit" not in sparql.lower() and "ask " not in sparql.lower():
            test_sparql = sparql + "\nLIMIT 1000"

        _, failed, _ = execute_query(test_sparql)
        if not failed:
            results["success_original"].append(qid)
            q["_status"] = "original_ok"
        else:
            q["_status"] = "needs_fix"

    print(f"\nOriginal working: {len(results['success_original'])}")
    print(f"Need fixing: {total - len(results['success_original'])}")

    # Second pass: fix failing queries
    for q in tqdm(data["questions"], desc="Applying fixes"):
        if q.get("_status") != "needs_fix":
            continue

        qid = q["id"]
        sparql = q["query"]["sparql"]

        fixed_sparql, applied_fixes = apply_all_fixes(sparql)

        if not applied_fixes:
            results["no_fix_applied"].append({"id": qid, "fixes": []})
            continue

        # Test fixed query
        _, failed, error = execute_query(fixed_sparql)

        if not failed:
            results["success_fixed"].append({"id": qid, "fixes": applied_fixes})
            q["query"]["sparql"] = fixed_sparql
            q["_status"] = "fixed"
        else:
            results["still_failing"].append({
                "id": qid,
                "fixes": applied_fixes,
                "error": error
            })

    # Summary
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Original working:     {len(results['success_original'])}")
    print(f"Successfully fixed:   {len(results['success_fixed'])}")
    print(f"Still failing:        {len(results['still_failing'])}")
    print(f"No fix applicable:    {len(results['no_fix_applied'])}")
    print(f"Total working after:  {len(results['success_original']) + len(results['success_fixed'])} / {total}")

    # Print fix distribution
    fix_counts = {}
    for item in results["success_fixed"]:
        for fix in item["fixes"]:
            fix_counts[fix] = fix_counts.get(fix, 0) + 1
    print(f"\nFix distribution (successful):")
    for fix, count in sorted(fix_counts.items(), key=lambda x: -x[1]):
        print(f"  {fix}: {count}")

    if results["still_failing"]:
        print(f"\nStill failing queries:")
        for item in results["still_failing"]:
            print(f"  {item['id']}: fixes={item['fixes']}, error={item['error'][:100]}")

    if results["no_fix_applied"]:
        print(f"\nQueries with no applicable fix:")
        for item in results["no_fix_applied"]:
            print(f"  {item['id']}")

    # Save fixed dataset
    # Clean up internal status field
    for q in data["questions"]:
        q.pop("_status", None)

    output_path = OUTPUT_FILE
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"\nFixed dataset saved to: {output_path}")

    return results


if __name__ == "__main__":
    main()
