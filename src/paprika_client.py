import gzip
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp

logger = logging.getLogger(__name__)


class PaprikaAPIError(Exception):
    """Custom exception for Paprika API errors."""

    pass


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

    def _parse_quantity(self, quantity_str: str) -> Tuple[float, Optional[str]]:
        """
        Parse a quantity string into numeric value and unit.

        Examples:
            "4 kilos" -> (4.0, "kilos")
            "3 liters" -> (3.0, "liters")
            "5" -> (5.0, None)
            "-2 kilos" -> (-2.0, "kilos")

        Args:
            quantity_str: Quantity string to parse

        Returns:
            Tuple of (numeric_value, unit_string)
        """
        if not quantity_str or not isinstance(quantity_str, str):
            return (0.0, None)

        quantity_str = quantity_str.strip()
        if not quantity_str:
            return (0.0, None)

        # Match pattern: optional minus sign, digits (including decimals), optional whitespace, optional unit
        match = re.match(r"^(-?\d+\.?\d*)\s*(.*)$", quantity_str)
        if match:
            numeric_value = float(match.group(1))
            unit = match.group(2).strip() if match.group(2) else None
            return (numeric_value, unit if unit else None)

        # Try to extract just a number
        try:
            numeric_value = float(quantity_str)
            return (numeric_value, None)
        except ValueError:
            return (0.0, None)

    def _add_quantities(self, quantity1: str, quantity2: str) -> Tuple[str, bool]:
        """
        Add two quantity strings, preserving units.

        Examples:
            "4 kilos" + "1 kilo" -> ("5 kilos", True)
            "3 liters" + "2 liters" -> ("5 liters", True)
            "4 kilos" + "2" -> ("6 kilos", True)  # Unit from first quantity
            "4" + "2 kilos" -> ("6 kilos", True)  # Unit from second quantity
            "4 kilos" + "-2 kilos" -> ("2 kilos", True)
            "1 kilo" + "-2 kilos" -> Error: would go below zero

        Args:
            quantity1: First quantity string (existing quantity)
            quantity2: Second quantity string (quantity to add)

        Returns:
            Tuple of (result_quantity_string, success)

        Raises:
            PaprikaAPIError: If result would be negative
        """
        if not isinstance(quantity1, str):
            quantity1 = str(quantity1)
        if not isinstance(quantity2, str):
            quantity2 = str(quantity2)

        value1, unit1 = self._parse_quantity(quantity1)
        value2, unit2 = self._parse_quantity(quantity2)

        # Determine which unit to use (prefer unit1, fallback to unit2)
        result_unit = unit1 if unit1 else unit2

        # Add the numeric values
        result_value = value1 + value2

        # Check if result would be negative
        if result_value < 0:
            raise PaprikaAPIError(
                f"Cannot subtract {quantity2} from {quantity1}: result would be negative"
            )

        # Format the result
        if result_unit:
            # Remove 's' from unit if value is 1 (singular form)
            if result_value == 1.0 and result_unit.endswith("s"):
                display_unit = result_unit[:-1]
            else:
                display_unit = result_unit

            # Format with appropriate precision (no decimals if whole number)
            if result_value == int(result_value):
                result_str = f"{int(result_value)} {display_unit}"
            else:
                result_str = f"{result_value} {display_unit}"
        else:
            # No unit, format as integer if whole number
            if result_value == int(result_value):
                result_str = str(int(result_value))
            else:
                result_str = str(result_value)

        return (result_str, True)

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
        data.add_field(
            "data",
            BytesIO(gzipped_data),
            filename="recipe.json.gz",
            content_type="application/octet-stream",
        )

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
        data.add_field(
            "data",
            BytesIO(gzipped_data),
            filename="recipe.json.gz",
            content_type="application/octet-stream",
        )

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
                "data",
                BytesIO(gzipped_data),
                filename="recipe.json.gz",
                content_type="application/octet-stream",
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

        Args:
            limit: Maximum number of recipes to return

        Returns:
            List of recipe data

        Raises:
            PaprikaAPIError: If listing fails
        """
        try:
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

                    recipes.append(recipe_data)

                except Exception as e:
                    logger.warning(f"Failed to fetch recipe {uid}: {str(e)}")
                    continue

            logger.info(f"Successfully fetched {len(recipes)} recipes")
            return recipes

        except Exception as e:
            logger.error(f"Failed to list recipes: {str(e)}")
            raise PaprikaAPIError(f"Failed to list recipes: {str(e)}")

    async def get_grocery_lists(self) -> List[Dict[str, Any]]:
        """
        Get all grocery lists with their names and default status.

        Returns:
            List of dictionaries with 'name' and 'is_default' keys

        Raises:
            PaprikaAPIError: If fetching fails
        """
        try:
            response = await self._make_authenticated_request(
                "GET", "/sync/grocerylists"
            )
            grocery_lists = response.get("result", [])

            if not grocery_lists:
                return []

            result = []
            for grocery_list in grocery_lists:
                if "name" in grocery_list:
                    result.append(
                        {
                            "name": grocery_list["name"],
                            "is_default": grocery_list.get("is_default", False),
                        }
                    )

            logger.info(f"Found {len(result)} grocery lists")
            return result

        except Exception as e:
            logger.error(f"Failed to get grocery lists: {str(e)}")
            raise PaprikaAPIError(f"Failed to get grocery lists: {str(e)}")

    async def get_default_list_uuid(self) -> Optional[str]:
        """
        Get the default grocery list UID.

        Returns:
            Default grocery list UID, or None if not found

        Raises:
            PaprikaAPIError: If fetching fails
        """
        try:
            response = await self._make_authenticated_request(
                "GET", "/sync/grocerylists"
            )
            grocery_lists = response.get("result", [])

            if not grocery_lists:
                raise PaprikaAPIError("No grocery lists found")

            for grocery_list in grocery_lists:
                if grocery_list.get("is_default"):
                    uid = grocery_list.get("uid")
                    logger.info(
                        f"Found default grocery list: {grocery_list.get('name')} (UID: {uid})"
                    )
                    return uid

            raise PaprikaAPIError("No default grocery list found")

        except Exception as e:
            logger.error(f"Failed to get default grocery list UUID: {str(e)}")
            raise PaprikaAPIError(f"Failed to get default grocery list: {str(e)}")

    async def _get_list_uuid_by_name(
        self, grocery_list_name: Optional[str] = None
    ) -> str:
        """
        Get grocery list UID by name, or default if name is None.

        Args:
            grocery_list_name: Name of the grocery list, or None for default

        Returns:
            Grocery list UID

        Raises:
            PaprikaAPIError: If list not found, with message including valid list names
        """
        if grocery_list_name is None:
            return await self.get_default_list_uuid()

        try:
            response = await self._make_authenticated_request(
                "GET", "/sync/grocerylists"
            )
            grocery_lists = response.get("result", [])

            for grocery_list in grocery_lists:
                if grocery_list.get("name") == grocery_list_name:
                    return grocery_list.get("uid")

            # List not found - get valid list names for error message
            valid_names = []
            for grocery_list in grocery_lists:
                if "name" in grocery_list:
                    valid_names.append(grocery_list["name"])

            if valid_names:
                valid_names_str = ", ".join([f"'{name}'" for name in valid_names])
                raise PaprikaAPIError(
                    f"Grocery list '{grocery_list_name}' not found. Valid grocery lists are: {valid_names_str}"
                )
            else:
                raise PaprikaAPIError(
                    f"Grocery list '{grocery_list_name}' not found. No grocery lists are available."
                )

        except Exception as e:
            if isinstance(e, PaprikaAPIError):
                raise
            logger.error(f"Failed to get grocery list UUID: {str(e)}")
            raise PaprikaAPIError(f"Failed to get grocery list UUID: {str(e)}")

    async def get_groceries(
        self, grocery_list_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all groceries from a grocery list.

        Args:
            grocery_list_name: Name of the grocery list, or None for default

        Returns:
            List of grocery items with name and quantity

        Raises:
            PaprikaAPIError: If fetching fails
        """
        try:
            list_uuid = await self._get_list_uuid_by_name(grocery_list_name)
            response = await self._make_authenticated_request("GET", "/sync/groceries")
            groceries = response.get("result", [])

            # Filter groceries by list_uid
            filtered_groceries = []
            for grocery in groceries:
                if grocery.get("list_uid") == list_uuid:
                    filtered_groceries.append(
                        {
                            "name": grocery.get("name", ""),
                            "quantity": grocery.get("quantity", ""),
                        }
                    )

            logger.info(f"Found {len(filtered_groceries)} groceries in list")
            return filtered_groceries

        except Exception as e:
            logger.error(f"Failed to get groceries: {str(e)}")
            raise PaprikaAPIError(f"Failed to get groceries: {str(e)}")

    async def get_grocery(
        self, item_name: str, grocery_list_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific grocery item by name.

        Args:
            item_name: Name of the grocery item
            grocery_list_name: Name of the grocery list, or None for default

        Returns:
            Grocery item with name and quantity (for MCP tool), or full grocery object if found internally

        Raises:
            PaprikaAPIError: If fetching fails
        """
        try:
            list_uuid = await self._get_list_uuid_by_name(grocery_list_name)
            response = await self._make_authenticated_request("GET", "/sync/groceries")
            groceries = response.get("result", [])

            for grocery in groceries:
                grocery_name = grocery.get("name", "").strip()
                if (
                    grocery_name == item_name.strip()
                    and grocery.get("list_uid") == list_uuid
                ):
                    # Return full grocery object (needed for add_grocery to get uid)
                    return grocery

            return None

        except Exception as e:
            logger.error(f"Failed to get grocery item '{item_name}': {str(e)}")
            raise PaprikaAPIError(f"Failed to get grocery item: {str(e)}")

    async def add_grocery(
        self,
        item_name: str,
        quantity: Union[int, str] = 1,
        grocery_list_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add or update a grocery item on the grocery list.

        Args:
            item_name: Name of the grocery item
            quantity: Quantity to add (default: 1). Can be an integer or string like "1 kilo", "4 liters", "-2 kilos"
            grocery_list_name: Name of the grocery list, or None for default

        Returns:
            Updated grocery item with final quantity

        Raises:
            PaprikaAPIError: If adding fails or result would be negative
        """
        if not item_name or not item_name.strip():
            raise PaprikaAPIError("Item name cannot be empty")

        try:
            # Convert quantity to string if it's an integer
            if isinstance(quantity, int):
                quantity_str = str(quantity)
            else:
                quantity_str = str(quantity)

            # Check if grocery already exists by fetching full grocery data
            list_uuid = await self._get_list_uuid_by_name(grocery_list_name)
            response = await self._make_authenticated_request("GET", "/sync/groceries")
            groceries = response.get("result", [])

            existing_grocery = None
            for grocery in groceries:
                grocery_name = grocery.get("name", "").strip()
                if (
                    grocery_name == item_name.strip()
                    and grocery.get("list_uid") == list_uuid
                ):
                    existing_grocery = grocery
                    break

            if existing_grocery:
                grocery_uid = existing_grocery.get("uid")
                current_quantity_str = str(existing_grocery.get("quantity", "0"))
            else:
                grocery_uid = self._generate_uuid()
                current_quantity_str = "0"

            # Add quantities using the helper method (handles units and negative values)
            try:
                final_quantity_str, _ = self._add_quantities(
                    current_quantity_str, quantity_str
                )
            except PaprikaAPIError:
                # Re-raise PaprikaAPIError as-is (these are already user-friendly)
                raise

            # Create grocery item data
            grocery_data = [
                {
                    "uid": grocery_uid,
                    "name": item_name.strip(),
                    "ingredient": item_name.strip(),
                    "quantity": final_quantity_str,
                    "recipe_uid": None,
                    "order_flag": 316,
                    "purchased": False,
                    "aisle": "Produce",
                    "recipe": None,
                    "instruction": "",
                    "separate": False,
                    "aisle_uid": "F94467760BF4BC6B9521FFA9329D0F1DBCCA0F5AC0808BD8552FB375A565FB9E",
                    "list_uid": list_uuid,
                }
            ]

            # Compress and send
            gzipped_data = self._gzip_json(grocery_data)
            data = aiohttp.FormData()
            data.add_field(
                "data",
                BytesIO(gzipped_data),
                filename="grocery.json.gz",
                content_type="application/octet-stream",
            )

            await self._make_authenticated_request("POST", "/sync/groceries", data=data)

            logger.info(
                f"Successfully added {quantity_str} '{item_name}' (total: {final_quantity_str})"
            )
            return {
                "name": item_name.strip(),
                "quantity": final_quantity_str,
            }

        except PaprikaAPIError:
            # Re-raise PaprikaAPIError as-is
            raise
        except Exception as e:
            logger.error(f"Failed to add grocery '{item_name}': {str(e)}")
            raise PaprikaAPIError(f"Failed to add grocery: {str(e)}")

    async def clear_grocery_list(self, grocery_list_name: Optional[str] = None) -> bool:
        """
        Clear all items from a grocery list.

        Args:
            grocery_list_name: Name of the grocery list, or None for default

        Returns:
            True if successful

        Raises:
            PaprikaAPIError: If clearing fails
        """
        try:
            list_uuid = await self._get_list_uuid_by_name(grocery_list_name)
            response = await self._make_authenticated_request("GET", "/sync/groceries")
            groceries = response.get("result", [])

            # Get all groceries for this list
            groceries_to_delete = []
            for grocery in groceries:
                if grocery.get("list_uid") == list_uuid:
                    groceries_to_delete.append(grocery)

            if not groceries_to_delete:
                logger.info("Grocery list is already empty")
                return True

            # Delete all groceries by setting quantity to 0 or removing them
            # Based on the API, we'll set quantity to 0 for each item
            grocery_data_list = []
            for grocery in groceries_to_delete:
                grocery_item = {
                    "uid": grocery.get("uid"),
                    "name": grocery.get("name", ""),
                    "ingredient": grocery.get("ingredient", ""),
                    "quantity": "0",
                    "recipe_uid": grocery.get("recipe_uid"),
                    "order_flag": grocery.get("order_flag", 316),
                    "purchased": False,
                    "aisle": grocery.get("aisle", "Produce"),
                    "recipe": grocery.get("recipe"),
                    "instruction": grocery.get("instruction", ""),
                    "separate": grocery.get("separate", False),
                    "aisle_uid": grocery.get(
                        "aisle_uid",
                        "F94467760BF4BC6B9521FFA9329D0F1DBCCA0F5AC0808BD8552FB375A565FB9E",
                    ),
                    "list_uid": list_uuid,
                }
                grocery_data_list.append(grocery_item)

            # Compress and send
            gzipped_data = self._gzip_json(grocery_data_list)
            data = aiohttp.FormData()
            data.add_field(
                "data",
                BytesIO(gzipped_data),
                filename="grocery.json.gz",
                content_type="application/octet-stream",
            )

            await self._make_authenticated_request("POST", "/groceries", data=data)

            logger.info(
                f"Successfully cleared {len(groceries_to_delete)} items from grocery list"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to clear grocery list: {str(e)}")
            raise PaprikaAPIError(f"Failed to clear grocery list: {str(e)}")

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
