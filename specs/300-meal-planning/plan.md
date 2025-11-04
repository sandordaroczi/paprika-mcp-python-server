# Implementation Plan: Meal Planning Functionality

## Overview
This plan outlines the implementation of meal planning functionality for the Paprika MCP server, enabling users to add, remove, and list meals in their meal plan through MCP tools.

## Implementation Tasks

### 1. Research and Understand Paprika Meal Plan API
**Priority**: High  
**Estimated Time**: 2-4 hours

**Tasks**:
- Research Paprika API meal planning endpoints from the Go reference implementation: https://github.com/soggycactus/paprika-3-mcp/pull/3/files
- Identify the API endpoints for:
  - Getting meal plan entries
  - Adding meals to meal plan
  - Removing meals from meal plan
- Document API request/response formats
- Verify authentication requirements

**Deliverable**: API documentation notes with endpoint details

---

### 2. Implement Meal Plan Client Methods in `paprika_client.py`
**Priority**: High  
**Estimated Time**: 4-6 hours

**Tasks**:

#### 2.1 Add helper methods
- `_find_recipe_by_name(name: str, recipes: List[Dict]) -> Dict`
  - Implement fuzzy matching using `difflib.SequenceMatcher` or `rapidfuzz`
  - If match score is high (>85%): return recipe dict
  - If match score is medium (60-85%): raise `MealMatchAmbiguousError` with list of potential matches
  - If match score is poor (<60%): raise `MealNotFoundError` offering to list all recipes
- `_parse_flexible_date(date_str: str) -> str`
  - Parse various date formats: "yyyy-mm-dd", "dd mmm", "dd mmmm", "dd-mm-yyyy", etc.
  - Use `dateutil.parser` or custom parsing logic
  - Return normalized date string in "YYYY-MM-DD" format
  - Raise `ValueError` if date cannot be parsed
- `_get_next_free_day(meal_plan: List[Dict], meal_type: str = "dinner") -> str`
  - Find next day from today forward that doesn't have a meal of specified type
  - Start checking from today (inclusive)
  - Return date in "YYYY-MM-DD" format
  - Note: Specs state one meal per type per day, but we don't enforce it

#### 2.2 Implement `get_meal_plan()` method
- **Signature**: `async def get_meal_plan(self, num_days: int = 10, meal_type: Optional[str] = "dinner") -> List[Dict[str, Any]]`
- **Functionality**:
  - Fetch meal plan from Paprika API
  - Filter by `num_days` (default 10) - should include upcoming days from today
  - Optionally filter by `meal_type` (default "dinner")
  - Parse and return list of meal plan entries
  - Each entry should include: meal (name), meal_ID (recipe UUID), date, type
  - Handle API errors and propagate them literally (per non-functional requirements)
  - Note: One meal per type per day per specs, but we don't enforce this

#### 2.3 Implement `add_meal_to_plan()` method
- **Signature**: `async def add_meal_to_plan(self, meal: Optional[str] = None, meal_id: Optional[str] = None, date: Optional[str] = None, meal_type: str = "dinner") -> Dict[str, Any]`
- **Functionality**:
  - If `meal_id` provided, use it directly (it's a recipe UUID, not a number)
  - If `meal` provided:
    - Call `list_recipes()` to get all recipes
    - Use `_find_recipe_by_name()` to find matching recipe (will raise exceptions for medium/poor matches)
  - If `date` provided:
    - Use `_parse_flexible_date()` to parse the date string
    - Normalize to "YYYY-MM-DD" format
  - If `date` not provided:
    - Call `get_meal_plan()` to get current plan
    - Call `_get_next_free_day()` to find next day from today without meal of that type
  - Make API call to add meal to plan
  - Return meal plan entry dict with: meal (name), meal_ID (recipe UUID), date, type
  - Handle API errors and propagate them literally

#### 2.4 Implement `remove_meal_from_plan()` method
- **Signature**: `async def remove_meal_from_plan(self, meal: Optional[str] = None, meal_id: Optional[str] = None, date: Optional[str] = None, meal_type: str = "dinner") -> Dict[str, Any]`
- **Functionality**:
  - Get current meal plan using `get_meal_plan()`
  - If no parameters provided:
    - Find meal on the latest date in the mealplan
    - If multiple meals on latest date, use the one matching default `meal_type` or first one
  - If `meal` or `meal_id` provided:
    - Find matching meal in plan (by name or UUID)
    - If `date` provided, parse with `_parse_flexible_date()` and filter to that date
    - If multiple matches, use most recent (latest date) or raise ambiguity error
  - If only `date` provided:
    - Parse date with `_parse_flexible_date()`
    - Remove meal from that date (with optional `meal_type` filter if provided)
  - Make API call to remove meal
  - Return removed meal details: result ("Meal removed"), meal (name), meal_ID (recipe UUID), date, type
  - Handle API errors and propagate them literally

**Deliverable**: Complete meal plan methods in `paprika_client.py` with proper error handling

---

### 3. Add Fuzzy Matching Dependency
**Priority**: Medium  
**Estimated Time**: 30 minutes

**Tasks**:
- Choose fuzzy matching library:
  - Option A: Use Python standard library `difflib` (no dependency)
  - Option B: Use `rapidfuzz` (faster, more accurate, requires dependency)
- Add dependency to `pyproject.toml` if using `rapidfuzz`
- Implement matching function with configurable thresholds

**Deliverable**: Fuzzy matching implementation in `paprika_client.py`

---

### 4. Implement MCP Tools in `server.py`
**Priority**: High  
**Estimated Time**: 3-4 hours

**Tasks**:

#### 4.1 Add `add_meal_to_plan` tool to `handle_list_tools()`
- Define tool schema with arguments:
  - `meal` (string, optional): Meal name for fuzzy matching
  - `meal_id` (string, optional): Recipe UUID (not a number)
  - `date` (string, optional): Date in flexible format - accepts "YYYY-MM-DD", "dd mmm", "dd mmmm", etc. (preferred: "YYYY-MM-DD")
  - `type` (string, optional): Meal type, defaults to "dinner"
- Add tool description mentioning flexible date parsing but recommending "YYYY-MM-DD" format

#### 4.2 Add `remove_meal_from_plan` tool to `handle_list_tools()`
- Define tool schema with arguments:
  - `meal` (string, optional): Meal name
  - `meal_id` (string, optional): Recipe UUID (not a number)
  - `date` (string, optional): Date in flexible format - accepts "YYYY-MM-DD", "dd mmm", "dd mmmm", etc. (preferred: "YYYY-MM-DD")
  - `type` (string, optional): Meal type, defaults to "dinner"
- Add tool description mentioning flexible date parsing but recommending "YYYY-MM-DD" format
- Note: If no arguments provided, removes meal on latest date in mealplan

#### 4.3 Add `list_meal_plan` tool to `handle_list_tools()`
- Define tool schema with arguments:
  - `num_days` (integer, optional): Number of days to show, defaults to 10
  - `meal_type` (string, optional): Filter by meal type, defaults to "dinner"
- Add tool description

#### 4.4 Implement tool handlers in `handle_call_tool()`
- Handle `add_meal_to_plan`:
  - Call `paprika_client.add_meal_to_plan()`
  - Get meal plan after adding to count meals by type
  - Format response: "Meal '{meal}' added to meal plan on {formatted_date}. Now {lunch_count} lunches and {dinner_count} dinners are planned."
  - Use readable date format (e.g., "3 November 2025")
  - Handle fuzzy matching exceptions (`MealMatchAmbiguousError`, `MealNotFoundError`) and format suggestions appropriately
- Handle `remove_meal_from_plan`:
  - Call `paprika_client.remove_meal_from_plan()`
  - Format response: "Meal '{meal}' removed from meal plan on {formatted_date}"
  - Use readable date format
- Handle `list_meal_plan`:
  - Call `paprika_client.get_meal_plan()`
  - Format response as list of meals with details (meal name, meal_ID as UUID, date, type)
  - Handle empty meal plan case

**Deliverable**: Three new MCP tools fully implemented and registered

---

### 5. Error Handling Implementation
**Priority**: High  
**Estimated Time**: 2 hours

**Tasks**:
- Ensure all Paprika API errors are caught and returned literally in tool responses
- Implement custom exceptions in `paprika_client.py`:
  - `MealNotFoundError`: When meal matching fails (poor match <60%)
    - Message should offer to list all recipes
  - `MealMatchAmbiguousError`: When multiple matches found (medium match 60-85%)
    - Should include list of potential matches in exception data
- Format error messages appropriately for MCP responses
- Handle date parsing errors (`ValueError` from `_parse_flexible_date()`)
- Test error scenarios:
  - Invalid meal names
  - API errors (propagate literally)
  - Network failures
  - Authentication failures
  - Invalid date formats

**Deliverable**: Robust error handling throughout meal planning functionality

---

### 6. Date Handling Utilities
**Priority**: Medium  
**Estimated Time**: 2-3 hours

**Tasks**:
- Implement flexible date parsing in `_parse_flexible_date()`:
  - Support formats: "YYYY-MM-DD", "dd mmm", "dd mmmm", "dd-mm-yyyy", etc.
  - Use `dateutil.parser` library or implement custom parsing
  - Normalize to "YYYY-MM-DD" format
  - Handle relative dates if needed (e.g., "tomorrow", "next week")
- Implement date formatting for user-facing messages (e.g., "3 November 2025")
- Calculate "next free day" logic in `_get_next_free_day()`:
  - Start from today (inclusive)
  - Iterate forward day by day
  - Find first day without meal of specified type
  - Return in "YYYY-MM-DD" format
- Handle edge cases:
  - Empty meal plan (return tomorrow)
  - All days filled up to reasonable limit (e.g., 365 days ahead, then return last checked + 1)
  - Date in past (may be allowed, document behavior)
  - Invalid date formats (raise ValueError)

**Deliverable**: Date utility functions in `paprika_client.py` with flexible parsing

---

### 7. Unit Tests
**Priority**: High  
**Estimated Time**: 4-6 hours

**Tasks**:
- Write tests for `_find_recipe_by_name()`:
  - High match scenario (returns recipe dict)
  - Medium match scenario (raises `MealMatchAmbiguousError` with suggestions)
  - Poor match scenario (raises `MealNotFoundError`)
  - Exact match
  - Case insensitivity
- Write tests for `_parse_flexible_date()`:
  - "YYYY-MM-DD" format
  - "dd mmm" format (e.g., "3 Nov")
  - "dd mmmm" format (e.g., "3 November")
  - Other common formats
  - Invalid date strings
  - Edge cases (leap year, month boundaries)
- Write tests for `_get_next_free_day()`:
  - Empty meal plan
  - Partially filled plan
  - Fully filled plan
  - Different meal types
- Write tests for `get_meal_plan()`:
  - Default parameters
  - Custom num_days
  - Filter by meal_type
  - Empty meal plan
  - API error handling
- Write tests for `add_meal_to_plan()`:
  - Add by meal name (fuzzy match)
  - Add by meal_id
  - Add with explicit date
  - Add without date (auto-find next free day)
  - Error scenarios
- Write tests for `remove_meal_from_plan()`:
  - Remove by meal name
  - Remove by meal_id (UUID)
  - Remove by date (with flexible parsing)
  - Remove last meal (no params - should remove meal on latest date)
  - Ambiguity handling (multiple matches)
  - Remove by date only
- Mock Paprika API responses for all tests

**Deliverable**: Comprehensive test suite in `tests/test_meal_planning.py`

---

### 8. Integration Tests
**Priority**: Medium  
**Estimated Time**: 2-3 hours

**Tasks**:
- Test end-to-end workflows:
  - Add meal → List meal plan → Remove meal
  - Multiple meals on different dates
  - Fuzzy matching in real scenario
- Test MCP tool integration:
  - Tool registration
  - Tool argument parsing
  - Tool response formatting
- Test error propagation through MCP layer

**Deliverable**: Integration tests verifying full workflow

---

### 9. Documentation
**Priority**: Low  
**Estimated Time**: 1 hour

**Tasks**:
- Document new methods in `paprika_client.py` with docstrings
- Document MCP tools with descriptions
- Update README.md if needed
- Add usage examples

**Deliverable**: Complete code documentation

---

## Implementation Order

1. **Phase 1: Foundation** (Tasks 1, 3)
   - Research API
   - Set up fuzzy matching

2. **Phase 2: Core Functionality** (Tasks 2, 6)
   - Implement client methods
   - Implement date utilities

3. **Phase 3: MCP Integration** (Task 4)
   - Register and implement MCP tools

4. **Phase 4: Error Handling** (Task 5)
   - Implement robust error handling

5. **Phase 5: Testing** (Tasks 7, 8)
   - Write and run unit tests
   - Write and run integration tests

6. **Phase 6: Polish** (Task 9)
   - Documentation
   - Code review

---

## Dependencies

### External Libraries (if needed)
- `rapidfuzz` (optional, for better fuzzy matching) - requires `pyproject.toml` update
- `python-dateutil` (for flexible date parsing) - requires `pyproject.toml` update
  - Alternative: Implement custom date parsing (more work, but no dependency)

### Python Standard Library
- `difflib` (if not using rapidfuzz)
- `datetime` (for date handling)

---

## Risk Assessment

### High Risk
- **Paprika API changes**: The reference implementation is in Go, API might differ or be undocumented
  - **Mitigation**: Research thoroughly, test early with real API

### Medium Risk
- **Fuzzy matching accuracy**: Matching quality affects UX
  - **Mitigation**: Tune thresholds, test with various recipe names, consider user feedback

### Low Risk
- **Date handling edge cases**: Timezone issues, date format inconsistencies
  - **Mitigation**: Use standard ISO date format internally, parse flexibly, document assumptions
- **meal_ID format confusion**: Specs show both number and UUID formats
  - **Mitigation**: Always use recipe UUID (recipe.uid), clarify in code and error messages

---

## Success Criteria

1. All three MCP tools (`add_meal_to_plan`, `remove_meal_from_plan`, `list_meal_plan`) are functional
2. Fuzzy matching provides helpful suggestions for medium matches via exceptions
3. Error messages from Paprika API are shown literally to users
4. Date parsing accepts multiple formats (YYYY-MM-DD, dd mmm, dd mmmm) but MCP descriptions specify preferred format
5. Assistant responses include meal counts by type (e.g., "Now 2 lunches and 3 dinners are planned")
6. "Next free day" correctly finds first day from today without meal of that type
7. "Last meal" removal correctly removes meal on latest date in mealplan
8. All unit tests pass
9. Integration tests verify end-to-end workflows
10. Code follows existing patterns in `server.py` and `paprika_client.py`

---

## Future Considerations (Not in Scope)

- "Plan a week of meals" functionality (mentioned in specs as future expansion)
- Seasonal filtering (summer/winter recipes)
- Sorting by `last_prepared` date
- Multi-meal-type support beyond basic filtering

---

## Notes

- Follow existing code patterns in `server.py` for tool registration and handling
- Follow existing error handling patterns in `paprika_client.py`
- Maintain consistency with existing tool response formatting
- Reference the Go implementation for API endpoint details: https://github.com/soggycactus/paprika-3-mcp/pull/3/files
- **meal_ID clarification**: Always use recipe UUID (recipe.uid), not a numeric ID. The specs show inconsistent examples - clarify in implementation.
- **One meal per type per day**: Specs state this is the case, but we don't need to enforce it - just document the behavior.
- **Date flexibility**: Accept multiple formats in parsing, but recommend "YYYY-MM-DD" in MCP tool descriptions.
- **Exception-based fuzzy matching**: Use exceptions for medium/poor matches rather than return type variations - cleaner design.

