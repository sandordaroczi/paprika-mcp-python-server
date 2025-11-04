import base64
import gzip
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import aiohttp
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class PaprikaAPIError(Exception):
    """Custom exception for Paprika API errors."""

    pass


class MealNotFoundError(Exception):
    """Exception raised when a meal/recipe cannot be found."""

    pass


class MealMatchAmbiguousError(Exception):
    """Exception raised when multiple potential meal matches are found."""

    def __init__(self, message: str, matches: List[Dict[str, Any]]):
        """
        Initialize the exception.

        Args:
            message: Error message
            matches: List of potential matching recipes
        """
        super().__init__(message)
        self.matches = matches


class PaprikaClient:
    """Client for interacting with the Paprika Recipe Manager API."""

    BASE_URL = "https://paprikaapp.com/api"

    def __init__(self, username: str, password: str):
        """
        Initialize the Paprika client.

        Args:
            username: Paprika account email
            password: Paprika account password
        """
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session

    async def authenticate(self) -> Optional[str]:
        """
        Authenticate with Paprika API and get access token.

        Returns:
            Authentication token

        Raises:
            PaprikaAPIError: If authentication fails
        """
        session = await self._get_session()

        login_data = {"email": self.username, "password": self.password}

        try:
            # Use v1 API for authentication (v2 returns "Unrecognized client")
            async with session.post(
                f"{self.BASE_URL}/v1/account/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as response:
                if response.status != 200:
                    raise PaprikaAPIError(f"Login failed with status {response.status}")

                result = await response.json()

                if "result" not in result or "token" not in result["result"]:
                    raise PaprikaAPIError("Invalid login response format")

                self.token = result["result"]["token"]
                logger.info("Successfully authenticated with Paprika API")
                return self.token

        except aiohttp.ClientError as e:
            raise PaprikaAPIError(f"Network error during authentication: {str(e)}")
        except json.JSONDecodeError:
            raise PaprikaAPIError("Invalid JSON response from login endpoint")

    async def _make_authenticated_request(
        self, method: str, endpoint: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for aiohttp request

        Returns:
            JSON response data

        Raises:
            PaprikaAPIError: If request fails
        """
        if not self.token:
            await self.authenticate()

        session = await self._get_session()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with session.request(
                method, f"{self.BASE_URL}/v2{endpoint}", headers=headers, **kwargs
            ) as response:
                if response.status == 401:
                    # Token might be expired, re-authenticate
                    await self.authenticate()
                    headers["Authorization"] = f"Bearer {self.token}"

                    async with session.request(
                        method,
                        f"{self.BASE_URL}/v2{endpoint}",
                        headers=headers,
                        **kwargs,
                    ) as retry_response:
                        if retry_response.status != 200:
                            raise PaprikaAPIError(
                                f"Request failed with status {retry_response.status}"
                            )

                        return await retry_response.json()

                elif response.status != 200:
                    error_text = await response.text()
                    raise PaprikaAPIError(
                        f"Request failed with status {response.status}: {error_text}"
                    )

                return await response.json()

        except aiohttp.ClientError as e:
            raise PaprikaAPIError(f"Network error: {str(e)}")

    async def _make_v1_basic_auth_request(
        self, method: str, endpoint: str, **kwargs
    ) -> Dict[str, Any]:
        """
        Make a v1 API request with HTTP Basic Authentication.
        Used for meal plan endpoints which require v1 Basic Auth.

        Args:
            method: HTTP method (GET, POST, DELETE, etc.)
            endpoint: API endpoint path (e.g., "/sync/meals/")
            **kwargs: Additional arguments for aiohttp request

        Returns:
            JSON response data

        Raises:
            PaprikaAPIError: If request fails
        """
        session = await self._get_session()
        headers = kwargs.pop("headers", {})

        # Create Basic Auth header
        credentials = f"{self.username}:{self.password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers["Authorization"] = f"Basic {encoded_credentials}"

        try:
            async with session.request(
                method, f"{self.BASE_URL}/v1{endpoint}", headers=headers, **kwargs
            ) as response:
                # Accept 200 OK, 201 Created (for POST), and 204 No Content (for DELETE)
                if response.status not in (200, 201, 204):
                    error_text = await response.text()
                    raise PaprikaAPIError(
                        f"Request failed with status {response.status}: {error_text}"
                    )

                # For 204 No Content, return empty dict
                if response.status == 204:
                    return {}

                # Try to parse JSON, but handle empty responses
                try:
                    return await response.json()
                except aiohttp.ContentTypeError:
                    # Some endpoints might return empty body with 200/201
                    return {}

        except aiohttp.ClientError as e:
            raise PaprikaAPIError(f"Network error: {str(e)}")

    def _generate_uuid(self) -> str:
        """Generate a new uppercase UUID."""
        return str(uuid.uuid4()).upper()

    def _calculate_hash(self, recipe_dict: Dict[str, Any]) -> str:
        """
        Calculate SHA256 hash for a recipe object.

        Args:
            recipe_dict: Recipe data dictionary

        Returns:
            Hex-encoded SHA256 hash
        """
        # Remove hash field and sort keys for consistent hashing
        data = {k: v for k, v in recipe_dict.items() if k != "hash"}
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _gzip_json(self, data: Dict[str, Any]) -> bytes:
        """
        Compress JSON data with gzip.

        Args:
            data: Data to compress

        Returns:
            Gzipped JSON bytes
        """
        json_str = json.dumps(data)
        return gzip.compress(json_str.encode("utf-8"))

    def _create_recipe_object(
        self,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
        uid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a recipe object with all required fields.

        Args:
            name: Recipe name
            ingredients: Recipe ingredients
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level
            uid: Recipe UID (generated if not provided)

        Returns:
            Complete recipe object
        """
        recipe = {
            "uid": uid or self._generate_uuid(),
            "name": name,
            "ingredients": ingredients,
            "directions": directions,
            "description": description,
            "notes": notes,
            "servings": servings,
            "prep_time": prep_time,
            "cook_time": cook_time,
            "total_time": "",
            "difficulty": difficulty,
            "source": "",
            "source_url": "",
            "categories": [],
            "rating": 0,
            "nutritional_info": "",
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "in_trash": False,
            "is_pinned": False,
            "on_favorites": False,
            "on_grocery_list": False,
            "image_url": "",
            "photo": "",
            "photo_hash": "",
            "photo_large": None,
            "photo_url": None,
            "scale": None,
        }

        # Calculate and set hash
        recipe["hash"] = self._calculate_hash(recipe)
        return recipe

    async def create_recipe(
        self,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
    ) -> Dict[str, Any]:
        """
        Create a new recipe in Paprika.

        Args:
            name: Recipe name
            ingredients: Recipe ingredients (one per line)
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level

        Returns:
            Created recipe data

        Raises:
            PaprikaAPIError: If creation fails
        """
        recipe = self._create_recipe_object(
            name=name,
            ingredients=ingredients,
            directions=directions,
            description=description,
            notes=notes,
            servings=servings,
            prep_time=prep_time,
            cook_time=cook_time,
            difficulty=difficulty,
        )

        # Gzip the recipe data
        gzipped_data = self._gzip_json(recipe)

        # Create multipart form data
        data = aiohttp.FormData()
        data.add_field("data", gzipped_data, content_type="application/octet-stream")

        try:
            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{recipe['uid']}/", data=data
            )

            logger.info(f"Successfully created recipe: {name}")
            return recipe

        except Exception as e:
            logger.error(f"Failed to create recipe {name}: {str(e)}")
            raise PaprikaAPIError(f"Failed to create recipe: {str(e)}")

    async def update_recipe(
        self,
        uid: str,
        name: str,
        ingredients: str,
        directions: str,
        description: str = "",
        notes: str = "",
        servings: str = "",
        prep_time: str = "",
        cook_time: str = "",
        difficulty: str = "",
    ) -> Dict[str, Any]:
        """
        Update an existing recipe in Paprika.

        Args:
            uid: Recipe UID to update
            name: Recipe name
            ingredients: Recipe ingredients
            directions: Cooking directions
            description: Recipe description
            notes: Additional notes
            servings: Number of servings
            prep_time: Preparation time
            cook_time: Cooking time
            difficulty: Difficulty level

        Returns:
            Updated recipe data

        Raises:
            PaprikaAPIError: If update fails
        """
        recipe = self._create_recipe_object(
            name=name,
            ingredients=ingredients,
            directions=directions,
            description=description,
            notes=notes,
            servings=servings,
            prep_time=prep_time,
            cook_time=cook_time,
            difficulty=difficulty,
            uid=uid,
        )

        # Gzip the recipe data
        gzipped_data = self._gzip_json(recipe)

        # Create multipart form data
        data = aiohttp.FormData()
        data.add_field("data", gzipped_data, content_type="application/octet-stream")

        try:
            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(f"Successfully updated recipe: {name}")
            return recipe

        except Exception as e:
            logger.error(f"Failed to update recipe {name}: {str(e)}")
            raise PaprikaAPIError(f"Failed to update recipe: {str(e)}")

    async def update_recipe_partial(self, uid: str, **kwargs) -> Dict[str, Any]:
        """
        Partially update an existing recipe in Paprika.
        Only updates the fields that are provided.

        Args:
            uid: Recipe UID to update
            **kwargs: Fields to update (name, ingredients, directions, etc.)

        Returns:
            Updated recipe data

        Raises:
            PaprikaAPIError: If update fails
        """
        try:
            # First, get the existing recipe
            response = await self._make_authenticated_request(
                "GET", f"/sync/recipe/{uid}/"
            )
            existing_recipe = response.get("result", {})

            if not existing_recipe:
                raise PaprikaAPIError(f"Recipe with UID {uid} not found")

            # Update only the provided fields
            for field, value in kwargs.items():
                if value is not None and value != "":
                    existing_recipe[field] = value

            # Recalculate hash and update timestamp
            existing_recipe["created"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            existing_recipe["hash"] = self._calculate_hash(existing_recipe)

            # Gzip the recipe data
            gzipped_data = self._gzip_json(existing_recipe)

            # Create multipart form data
            data = aiohttp.FormData()
            data.add_field(
                "data", gzipped_data, content_type="application/octet-stream"
            )

            await self._make_authenticated_request(
                "POST", f"/sync/recipe/{uid}/", data=data
            )

            logger.info(
                f"Successfully partially updated recipe: {existing_recipe['name']}"
            )
            return existing_recipe

        except Exception as e:
            logger.error(f"Failed to partially update recipe {uid}: {str(e)}")
            raise PaprikaAPIError(f"Failed to partially update recipe: {str(e)}")

    async def list_recipes(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List recipes from Paprika.
        Enhanced with last_planned date from meal plan.

        Args:
            limit: Maximum number of recipes to return

        Returns:
            List of recipe data, each with optional last_planned date (YYYY-MM-DD format)

        Raises:
            PaprikaAPIError: If listing fails
        """
        try:
            # Fetch all planned meals to calculate last_planned dates
            # Get all historical meal plan entries (past dates, not future)
            # For last_planned, we need all past entries, so use a large historical range
            meal_plan = []
            try:
                today = datetime.now().date()
                # Get meal plan from 1 year ago until today for last_planned calculation
                # This ensures we capture all historical entries
                start_date = (today - timedelta(days=366)).strftime("%Y-%m-%d")
                end_date = today.strftime("%Y-%m-%d")
                meal_plan = await self.get_meal_plan(
                    start_date=start_date,
                    end_date=end_date,
                    meal_type=None
                )
            except Exception as e:
                logger.warning(f"Failed to fetch meal plan for last_planned calculation: {str(e)}")
                # Continue without last_planned dates if meal plan fetch fails

            # Build a map of recipe UID to most recent planned date
            recipe_last_planned = {}
            for meal_entry in meal_plan:
                meal_id = meal_entry.get("meal_ID", "")
                meal_date = meal_entry.get("date", "")
                if meal_id and meal_date:
                    # Parse date (format: "YYYY-MM-DD")
                    try:
                        # If meal_date has time component, strip it
                        date_str = meal_date.split()[0] if " " in meal_date else meal_date
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                        
                        # Keep the most recent date for each recipe
                        if meal_id not in recipe_last_planned:
                            recipe_last_planned[meal_id] = date_obj
                        else:
                            if date_obj > recipe_last_planned[meal_id]:
                                recipe_last_planned[meal_id] = date_obj
                    except (ValueError, AttributeError):
                        logger.warning(f"Failed to parse date '{meal_date}' for meal_ID '{meal_id}'")
                        continue

            # First get the list of recipe UIDs
            response = await self._make_authenticated_request("GET", "/sync/recipes")
            recipe_list = response.get("result", [])

            if not recipe_list:
                return []

            # Limit the number of recipes to fetch
            recipe_list = recipe_list[:limit]

            # Fetch full recipe data for each UID
            recipes = []
            for recipe_info in recipe_list:
                uid = recipe_info["uid"]

                try:
                    recipe_response = await self._make_authenticated_request(
                        "GET", f"/sync/recipe/{uid}/"
                    )

                    recipe_data = recipe_response.get("result", {})

                    # Skip recipes in trash
                    if recipe_data.get("in_trash", False):
                        continue

                    # Add last_planned date if available
                    if uid in recipe_last_planned:
                        recipe_data["last_planned"] = recipe_last_planned[uid].strftime("%Y-%m-%d")

                    recipes.append(recipe_data)

                except Exception as e:
                    logger.warning(f"Failed to fetch recipe {uid}: {str(e)}")
                    continue

            logger.info(f"Successfully fetched {len(recipes)} recipes")
            return recipes

        except Exception as e:
            logger.error(f"Failed to list recipes: {str(e)}")
            raise PaprikaAPIError(f"Failed to list recipes: {str(e)}")

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # Meal planning helper methods

    def _find_recipe_by_name(
        self, name: str, recipes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Find a recipe by name using fuzzy matching.

        Args:
            name: Recipe name to search for
            recipes: List of recipe dictionaries to search

        Returns:
            Matching recipe dictionary

        Raises:
            MealMatchAmbiguousError: If multiple matches found (medium confidence)
            MealNotFoundError: If no good match found (poor confidence)
        """
        if not recipes:
            raise MealNotFoundError(
                f"Recipe '{name}' not found. No recipes available. Would you like to list all recipes?"
            )

        name_lower = name.lower().strip()
        matches_with_scores = []

        for recipe in recipes:
            recipe_name = recipe.get("name", "").lower().strip()
            if not recipe_name:
                continue

            # Calculate similarity using SequenceMatcher
            similarity = SequenceMatcher(None, name_lower, recipe_name).ratio()

            if similarity > 0.85:
                # High match - return immediately
                logger.info(
                    f"Found high match for '{name}': {recipe['name']} (score: {similarity:.2f})"
                )
                return recipe

            if similarity >= 0.60:
                # Medium match - collect for suggestions
                matches_with_scores.append((similarity, recipe))

        # Sort by similarity (highest first)
        matches_with_scores.sort(key=lambda x: x[0], reverse=True)

        if matches_with_scores:
            # Medium matches found - raise with suggestions
            matches = [recipe for _, recipe in matches_with_scores[:5]]  # Top 5 matches
            match_names = [r["name"] for r in matches]
            raise MealMatchAmbiguousError(
                f"Did you mean these? {' '.join(match_names)}", matches
            )

        # No good match found
        raise MealNotFoundError(
            f"Recipe '{name}' not found. Would you like to list all recipes?"
        )

    def _parse_flexible_date(self, date_str: str) -> str:
        """
        Parse a flexible date string into YYYY-MM-DD format.

        Supports formats like:
        - "YYYY-MM-DD" (e.g., "2025-11-03")
        - "dd mmm" (e.g., "3 Nov")
        - "dd mmmm" (e.g., "3 November")
        - "dd-mm-yyyy" (e.g., "03-11-2025")
        - And other common formats via dateutil

        Args:
            date_str: Date string in various formats

        Returns:
            Date string in "YYYY-MM-DD" format

        Raises:
            ValueError: If date cannot be parsed
        """
        try:
            # First check if it's already in ISO format (YYYY-MM-DD)
            if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                try:
                    # Validate it's a valid ISO date
                    datetime.strptime(date_str, "%Y-%m-%d")
                    return date_str
                except ValueError:
                    pass  # Not a valid ISO date, continue with parsing

            # Try using dateutil parser for flexible parsing
            parsed_date = date_parser.parse(date_str, dayfirst=True)
            return parsed_date.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError) as e:
            raise ValueError(f"Unable to parse date '{date_str}': {str(e)}")

    def _format_date_readable(self, date_str: str) -> str:
        """
        Format a date string (YYYY-MM-DD) into a readable format.

        Args:
            date_str: Date string in "YYYY-MM-DD" format

        Returns:
            Readable date string (e.g., "3 November 2025")
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            # Use %d and strip leading zero for cross-platform compatibility
            day = date_obj.day
            month = date_obj.strftime("%B")
            year = date_obj.year
            return f"{day} {month} {year}"
        except ValueError:
            return date_str  # Return original if parsing fails

    def _get_next_free_day(
        self, meal_plan: List[Dict[str, Any]], meal_type: str = "dinner"
    ) -> str:
        """
        Find the next day from today that doesn't have a meal of the specified type.

        Args:
            meal_plan: List of meal plan entries
            meal_type: Type of meal to check for (default: "dinner")

        Returns:
            Date string in "YYYY-MM-DD" format
        """
        today = datetime.now().date()
        max_days_ahead = 365  # Reasonable limit

        # Create a set of dates that already have meals of this type
        occupied_dates = set()
        for entry in meal_plan:
            entry_type = entry.get("type", "").lower()
            entry_date_str = entry.get("date", "")
            if entry_type == meal_type.lower() and entry_date_str:
                try:
                    entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
                    occupied_dates.add(entry_date)
                except ValueError:
                    continue

        # Iterate from today forward
        for day_offset in range(max_days_ahead + 1):
            check_date = today + timedelta(days=day_offset)
            if check_date not in occupied_dates:
                return check_date.strftime("%Y-%m-%d")

        # If all days are filled, return the day after the max limit
        return (today + timedelta(days=max_days_ahead + 1)).strftime("%Y-%m-%d")

    # Meal planning API methods

    async def get_meal_plan(
        self,
        num_days: Optional[int] = None,
        meal_type: Optional[str] = "dinner",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get meal plan entries from Paprika.

        Args:
            num_days: Number of days to include from today forward (default: 10, ignored if start_date/end_date provided)
            meal_type: Filter by meal type (default: "dinner", None for all types)
            start_date: Start date in YYYY-MM-DD format (optional, if provided overrides num_days)
            end_date: End date in YYYY-MM-DD format (optional, if provided overrides num_days)

        Returns:
            List of meal plan entries, each with: meal (name), meal_ID (recipe UUID), date, type

        Raises:
            PaprikaAPIError: If API request fails
            ValueError: If date parsing fails
        """
        try:
            # Fetch meal plan from API
            # Based on Go reference implementation, endpoint is /sync/meals (requires v1 Basic Auth)
            # Try /sync/meals first, fallback to /sync/meals/ if needed
            try:
                response = await self._make_v1_basic_auth_request("GET", "/sync/meals")
            except PaprikaAPIError as e:
                if "404" in str(e):
                    # Try with trailing slash
                    response = await self._make_v1_basic_auth_request("GET", "/sync/meals/")
                else:
                    raise

            # Parse response - API might return result.mealplan or result.meals
            meal_plan_data = response.get("result", {})
            if isinstance(meal_plan_data, list):
                all_entries = meal_plan_data
            else:
                # Could be nested like result.mealplan or result.meals
                all_entries = meal_plan_data.get("mealplan", meal_plan_data.get("meals", []))

            if not all_entries:
                return []

            # Determine date range for filtering
            today = datetime.now().date()
            
            if start_date and end_date:
                # Use explicit start and end dates
                try:
                    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError as e:
                    raise ValueError(f"Invalid date format. Expected YYYY-MM-DD: {str(e)}")
            elif start_date:
                # Only start_date provided, use today as end_date or parse end_date
                try:
                    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                    end_date_obj = today + timedelta(days=num_days if num_days is not None else 10)
                except ValueError as e:
                    raise ValueError(f"Invalid start_date format. Expected YYYY-MM-DD: {str(e)}")
            elif end_date:
                # Only end_date provided, use today as start_date
                try:
                    start_date_obj = today
                    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                except ValueError as e:
                    raise ValueError(f"Invalid end_date format. Expected YYYY-MM-DD: {str(e)}")
            else:
                # Use num_days (default behavior, backwards compatible)
                num_days_val = num_days if num_days is not None else 10
                start_date_obj = today
                end_date_obj = today + timedelta(days=num_days_val)

            # Map meal type integers to strings for filtering
            meal_type_map = {
                1: "breakfast",
                2: "dinner",
                3: "lunch",
            }
            reverse_meal_type_map = {"breakfast": 1, "dinner": 2, "lunch": 3}

            filtered_entries = []
            for entry in all_entries:
                entry_date_str = entry.get("date", "")
                if not entry_date_str:
                    continue

                try:
                    # Parse date - API returns "YYYY-MM-DD 00:00:00" format
                    if " " in entry_date_str:
                        entry_date = datetime.strptime(entry_date_str.split()[0], "%Y-%m-%d").date()
                        date_str_for_result = entry_date_str.split()[0]  # Just the date part
                    else:
                        entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
                        date_str_for_result = entry_date_str

                    if start_date_obj <= entry_date <= end_date_obj:
                        # Get meal type - can be integer or string
                        entry_type = entry.get("type")
                        entry_type_str = None
                        if isinstance(entry_type, int):
                            entry_type_str = meal_type_map.get(entry_type, "dinner")
                        elif isinstance(entry_type, str):
                            entry_type_str = entry_type.lower()

                        # Filter by meal_type if specified
                        if meal_type is None:
                            # Include all types
                            include_entry = True
                        else:
                            # Check if types match
                            meal_type_int = reverse_meal_type_map.get(meal_type.lower())
                            include_entry = (
                                entry_type_str == meal_type.lower()
                                or entry_type == meal_type_int
                            )

                        if include_entry:
                            # Normalize entry format
                            recipe_uid = entry.get("recipe_uid") or entry.get("recipe_id") or entry.get("meal_id")
                            recipe_name = entry.get("name") or entry.get("recipe_name") or entry.get("meal")

                            filtered_entries.append({
                                "meal": recipe_name or "Unknown",
                                "meal_ID": recipe_uid or "",
                                "date": date_str_for_result,
                                "type": entry_type_str or "dinner",
                            })
                except ValueError:
                    continue

            # Sort by date
            filtered_entries.sort(key=lambda x: x.get("date", ""))

            logger.info(f"Successfully fetched {len(filtered_entries)} meal plan entries")
            return filtered_entries

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to get meal plan: {error_msg}")
            # Per non-functional requirements: show API errors literally
            raise PaprikaAPIError(f"Failed to get meal plan: {error_msg}")

    async def add_meal_to_plan(
        self,
        meal: Optional[str] = None,
        meal_id: Optional[str] = None,
        date: Optional[str] = None,
        meal_type: str = "dinner",
    ) -> Dict[str, Any]:
        """
        Add a meal to the meal plan.

        Args:
            meal: Meal name for fuzzy matching (optional if meal_id provided)
            meal_id: Recipe UUID (optional if meal provided)
            date: Date in flexible format (optional, defaults to next free day)
            meal_type: Meal type (default: "dinner")

        Returns:
            Meal plan entry dict with: meal (name), meal_ID (recipe UUID), date, type

        Raises:
            MealNotFoundError: If meal not found
            MealMatchAmbiguousError: If multiple matches found
            PaprikaAPIError: If API request fails
        """
        recipe_uid = meal_id
        recipe_name = None

        # Resolve recipe from meal name if needed
        if meal and not meal_id:
            recipes = await self.list_recipes(limit=1000)  # Get all recipes for matching
            matched_recipe = self._find_recipe_by_name(meal, recipes)
            recipe_uid = matched_recipe["uid"]
            recipe_name = matched_recipe["name"]
        elif meal_id:
            # Get recipe name from UUID
            try:
                recipe_response = await self._make_authenticated_request(
                    "GET", f"/sync/recipe/{meal_id}/"
                )
                recipe_data = recipe_response.get("result", {})
                recipe_name = recipe_data.get("name", "")
            except Exception:
                recipe_name = "Unknown Recipe"

        if not recipe_uid:
            raise MealNotFoundError("Either meal name or meal_id must be provided")

        # Parse date or find next free day
        if date:
            parsed_date = self._parse_flexible_date(date)
        else:
            # Get current meal plan to find next free day
            current_plan = await self.get_meal_plan(num_days=365, meal_type=None)
            parsed_date = self._get_next_free_day(current_plan, meal_type)

        # Generate UUID for meal plan entry
        meal_entry_id = self._generate_uuid()

        # Map meal_type string to integer (based on API: 1=breakfast, 2=dinner, 3=lunch)
        meal_type_map = {
            "breakfast": 1,
            "dinner": 2,
            "lunch": 3,
        }
        meal_type_int = meal_type_map.get(meal_type.lower(), 2)  # Default to dinner

        # Format date with time component (API expects "YYYY-MM-DD 00:00:00")
        date_with_time = f"{parsed_date} 00:00:00"

        # Create meal plan entry object matching actual API structure
        # Based on Go reference implementation: https://github.com/soggycactus/paprika-3-mcp/blob/5a81214b157d0184aeb9bfdc0762f6bacfe58032/internal/paprika/client.go
        # Key differences:
        # 1. Meal must be wrapped in an array (mealsArray := []MealPlan{meal})
        # 2. Must include "deleted": false field
        # 3. Always POST to /api/v1/sync/meals/ (no UID in URL)
        meal_entry = {
            "uid": meal_entry_id,
            "recipe_uid": recipe_uid,
            "name": recipe_name or "Unknown",
            "date": date_with_time,
            "type": meal_type_int,
            "order_flag": 0,
            "deleted": False,  # Required field per Go reference
        }

        try:
            # Wrap meal in array as required by V1 API (per Go reference)
            meals_array = [meal_entry]
            gzipped_data = self._gzip_json(meals_array)
            
            # Create multipart form with filename "data" (per Go reference: CreateFormFile("data", "data"))
            data = aiohttp.FormData()
            data.add_field("data", gzipped_data, content_type="application/octet-stream", filename="data")

            # Always POST to /sync/meals/ (without UID in URL, per Go reference)
            await self._make_v1_basic_auth_request(
                "POST", "/sync/meals/", data=data
            )

            logger.info(
                f"Successfully added meal '{recipe_name}' to meal plan on {parsed_date}"
            )

            return {
                "meal": recipe_name or "Unknown",
                "meal_ID": recipe_uid,
                "date": parsed_date,
                "type": meal_type,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to add meal to plan: {error_msg}")
            # Per non-functional requirements: show API errors literally
            raise PaprikaAPIError(f"Failed to add meal to plan: {error_msg}")

    async def remove_meal_from_plan(
        self,
        meal: Optional[str] = None,
        meal_id: Optional[str] = None,
        date: Optional[str] = None,
        meal_type: str = "dinner",
    ) -> Dict[str, Any]:
        """
        Remove a meal from the meal plan.

        Args:
            meal: Meal name (optional)
            meal_id: Recipe UUID (optional)
            date: Date in flexible format (optional)
            meal_type: Meal type for filtering (default: "dinner")

        Returns:
            Removed meal details: result, meal (name), meal_ID (recipe UUID), date, type

        Raises:
            MealNotFoundError: If meal not found in plan
            PaprikaAPIError: If API request fails
        """
        # Get current meal plan
        current_plan = await self.get_meal_plan(num_days=365, meal_type=None)

        if not current_plan:
            raise MealNotFoundError("No meals found in meal plan")

        # Find meal to remove
        meal_to_remove = None

        if not meal and not meal_id and not date:
            # Remove meal on latest date
            if current_plan:
                # Sort by date (descending), then by meal_type match
                sorted_plan = sorted(
                    current_plan,
                    key=lambda x: (x.get("date", ""), x.get("type", "").lower() != meal_type.lower()),
                    reverse=True,
                )
                meal_to_remove = sorted_plan[0]
        elif date:
            # Remove meal from specific date
            parsed_date = self._parse_flexible_date(date)
            matching_meals = [
                m for m in current_plan
                if m.get("date") == parsed_date
                and (meal_type is None or m.get("type", "").lower() == meal_type.lower())
            ]

            if meal or meal_id:
                # Filter by meal name or ID
                search_value = (meal or "").lower() if meal else meal_id
                matching_meals = [
                    m for m in matching_meals
                    if (m.get("meal", "").lower() == search_value)
                    or (m.get("meal_ID", "") == search_value)
                ]

            if not matching_meals:
                raise MealNotFoundError(
                    f"No meal found on {parsed_date} matching the criteria"
                )
            meal_to_remove = matching_meals[0]
        elif meal or meal_id:
            # Find by meal name or ID
            search_value = (meal or "").lower() if meal else meal_id
            matching_meals = [
                m for m in current_plan
                if (m.get("meal", "").lower() == search_value)
                or (m.get("meal_ID", "") == search_value)
            ]

            if date:
                parsed_date = self._parse_flexible_date(date)
                matching_meals = [m for m in matching_meals if m.get("date") == parsed_date]

            if not matching_meals:
                raise MealNotFoundError(f"No meal found matching '{search_value}'")

            if len(matching_meals) > 1:
                # Multiple matches - use most recent (latest date)
                matching_meals.sort(key=lambda x: x.get("date", ""), reverse=True)
                meal_to_remove = matching_meals[0]
            else:
                meal_to_remove = matching_meals[0]

        if not meal_to_remove:
            raise MealNotFoundError("No meal found matching the criteria")

        # Extract meal plan entry ID - we need to find it from the API
        # The meal plan entries might have an ID field
        entry_date = meal_to_remove.get("date", "")
        entry_type = meal_to_remove.get("type", "")
        entry_recipe_uid = meal_to_remove.get("meal_ID", "")

        try:
            # Fetch full meal plan to find entry ID
            response = await self._make_v1_basic_auth_request("GET", "/sync/meals/")
            meal_plan_data = response.get("result", {})
            if isinstance(meal_plan_data, list):
                all_entries = meal_plan_data
            else:
                all_entries = meal_plan_data.get("mealplan", meal_plan_data.get("meals", []))

            entry_to_delete = None
            # Map meal type integers to strings for matching
            meal_type_map = {
                1: "breakfast",
                2: "dinner",
                3: "lunch",
            }
            
            # Filter out already deleted entries
            active_entries = [e for e in all_entries if not e.get("deleted", False)]
            
            for entry in active_entries:
                entry_uid = entry.get("uid") or entry.get("id")
                entry_date_check = entry.get("date", "")
                # Handle date comparison - strip time component if present
                entry_date_check_clean = entry_date_check.split()[0] if " " in entry_date_check else entry_date_check
                
                # Handle meal type - can be integer or string
                entry_type_raw = entry.get("type", "")
                if isinstance(entry_type_raw, int):
                    entry_type_check = meal_type_map.get(entry_type_raw, "dinner")
                elif isinstance(entry_type_raw, str):
                    entry_type_check = entry_type_raw.lower()
                else:
                    entry_type_check = "dinner"  # Default
                
                entry_recipe_check = (
                    entry.get("recipe_uid") or entry.get("recipe_id") or entry.get("meal_id")
                )

                if (
                    entry_date_check_clean == entry_date
                    and entry_type_check == entry_type.lower()
                    and entry_recipe_check == entry_recipe_uid
                ):
                    entry_to_delete = entry
                    logger.info(f"Found meal plan entry to delete: uid={entry.get('uid')}, date={entry_date_check_clean}, type={entry_type_check}, recipe={entry_recipe_check}")
                    break

            if not entry_to_delete:
                logger.error(f"Meal plan entry not found. Searched for: date={entry_date}, type={entry_type}, recipe={entry_recipe_uid}")
                logger.error(f"Available entries: {[(e.get('date'), e.get('type'), e.get('recipe_uid')) for e in active_entries[:5]]}")
                raise MealNotFoundError("Meal plan entry not found for deletion")

            entry_id = entry_to_delete.get("uid") or entry_to_delete.get("id") or entry_recipe_uid

            if not entry_id:
                logger.error(f"Entry found but no UID available. Entry keys: {list(entry_to_delete.keys())}")
                raise MealNotFoundError("Meal plan entry UID not found for deletion")

            logger.info(f"Attempting soft delete with UID: {entry_id}")

            # Delete meal plan entry using soft delete (per Go reference)
            # Based on Go reference: deletion is via deleted flag, not HTTP DELETE
            # Create meal entry with UID and deleted=true (minimum required fields per Go reference)
            soft_delete_entry = {
                "uid": entry_id,
                "deleted": True,  # Soft delete flag
            }
            
            # Wrap in array as required by V1 API (per Go reference)
            meals_array = [soft_delete_entry]
            gzipped_data = self._gzip_json(meals_array)
            
            # Create multipart form with filename "data" (per Go reference)
            data = aiohttp.FormData()
            data.add_field("data", gzipped_data, content_type="application/octet-stream", filename="data")

            # POST to /sync/meals/ (not DELETE, per Go reference)
            await self._make_v1_basic_auth_request("POST", "/sync/meals/", data=data)

            logger.info(
                f"Successfully removed meal '{meal_to_remove.get('meal')}' from meal plan on {entry_date}"
            )

            return {
                "result": "Meal removed",
                "meal": meal_to_remove.get("meal", "Unknown"),
                "meal_ID": meal_to_remove.get("meal_ID", ""),
                "date": entry_date,
                "type": entry_type,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to remove meal from plan: {error_msg}")
            # Per non-functional requirements: show API errors literally
            raise PaprikaAPIError(f"Failed to remove meal from plan: {error_msg}")
