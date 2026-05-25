Implemented the rich grammar schema without modifying existing files.

Added [rich_grammar_schema.py](/Users/thorbthorb/Downloads/IL_ideation/packages/pipeline/rich_grammar_schema.py:1) with:
- Frozen dataclasses for `NodeAttributes`, `ProductionSymbol`, `ProductionRule`, and `RichGrammar`
- Multiple productions per LHS nonterminal
- RHS node attributes: `angle`, `mass`, `orientation`, `scale`
- Optional `weight`, `tags`, and `label` provenance metadata
- `convert_legacy_rules(old: dict[str, list[str]]) -> RichGrammar`
- `compile_rich_structural_rules(...) -> CompileResult`, preserving the existing `compile_safe` / `invalid_nodes` contract and validating against `GrammarNodes.short_form_name`

Added [test_rich_grammar_schema.py](/Users/thorbthorb/Downloads/IL_ideation/tests/test_rich_grammar_schema.py:1) covering legacy conversion, multiple productions, attributes, immutability, validation errors, Supabase vocabulary integration via monkeypatch, invalid-node reporting, empty vocabulary behavior, and legacy loading through the new compiler.

Verification:
- `python3 -m pytest tests/test_rich_grammar_schema.py -q` -> `10 passed`
- `python3 -m pytest tests/test_grammar_graph.py -q` -> `33 passed`
- `python3 -m pytest tests/test_rich_grammar_schema.py tests/test_grammar_graph.py -q` -> `43 passed`
