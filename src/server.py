import asyncio
import logging
from typing import Any

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from config import get_config
from paprika_client import (
    MealMatchAmbiguousError,
    MealNotFoundError,
    PaprikaClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize server
server = Server("paprika-mcp-python")


async def main():
    """Main entry point for the MCP server."""
    paprika_client = None
    try:
        config = get_config()

        # Initialize Paprika client
        paprika_client = PaprikaClient(
            username=config.paprika_username, password=config.paprika_password
        )
        await paprika_client.authenticate()
        logger.info("Successfully authenticated with Paprika")

        # Define tools
        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="create_recipe",
                    description="Create a new recipe in Paprika",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "The name of the recipe",
                            },
                            "ingredients": {
                                "type": "string",
                                "description": "Recipe ingredients, one per line",
                            },
                            "directions": {
                                "type": "string",
                                "description": "Cooking directions/instructions",
                            },
                            "description": {
                                "type": "string",
                                "description": "Optional recipe description",
                                "default": "",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional cooking notes",
                                "default": "",
                            },
                            "servings": {
                                "type": "string",
                                "description": "Number of servings",
                                "default": "",
                            },
                            "prep_time": {
                                "type": "string",
                                "description": "Preparation time (e.g., '15 mins')",
                                "default": "",
                            },
                            "cook_time": {
                                "type": "string",
                                "description": "Cooking time (e.g., '30 mins')",
                                "default": "",
                            },
                            "difficulty": {
                                "type": "string",
                                "description": "Difficulty level (Easy, Medium, Hard)",
                                "default": "",
                            },
                        },
                        "required": ["name", "ingredients", "directions"],
                    },
                ),
                Tool(
                    name="update_recipe",
                    description="Update an existing recipe in Paprika",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "uid": {
                                "type": "string",
                                "description": "The UID of the recipe to update",
                            },
                            "name": {
                                "type": "string",
                                "description": "The name of the recipe",
                            },
                            "ingredients": {
                                "type": "string",
                                "description": "Recipe ingredients, one per line",
                            },
                            "directions": {
                                "type": "string",
                                "description": "Cooking directions/instructions",
                            },
                            "description": {
                                "type": "string",
                                "description": "Recipe description",
                                "default": "",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Cooking notes",
                                "default": "",
                            },
                            "servings": {
                                "type": "string",
                                "description": "Number of servings",
                                "default": "",
                            },
                            "prep_time": {
                                "type": "string",
                                "description": "Preparation time",
                                "default": "",
                            },
                            "cook_time": {
                                "type": "string",
                                "description": "Cooking time",
                                "default": "",
                            },
                            "difficulty": {
                                "type": "string",
                                "description": "Difficulty level",
                                "default": "",
                            },
                        },
                        "required": ["uid", "name", "ingredients", "directions"],
                    },
                ),
                Tool(
                    name="update_recipe_partial",
                    description="Partially update an existing recipe in Paprika (only specified fields)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "uid": {
                                "type": "string",
                                "description": "The UID of the recipe to update",
                            },
                            "name": {
                                "type": "string",
                                "description": "The name of the recipe (optional)",
                            },
                            "ingredients": {
                                "type": "string",
                                "description": "Recipe ingredients, one per line (optional)",
                            },
                            "directions": {
                                "type": "string",
                                "description": "Cooking directions/instructions (optional)",
                            },
                            "description": {
                                "type": "string",
                                "description": "Recipe description (optional)",
                            },
                            "notes": {
                                "type": "string",
                                "description": "Cooking notes (optional)",
                            },
                            "servings": {
                                "type": "string",
                                "description": "Number of servings (optional)",
                            },
                            "prep_time": {
                                "type": "string",
                                "description": "Preparation time (optional)",
                            },
                            "cook_time": {
                                "type": "string",
                                "description": "Cooking time (optional)",
                            },
                            "difficulty": {
                                "type": "string",
                                "description": "Difficulty level (optional)",
                            },
                        },
                        "required": ["uid"],
                    },
                ),
                Tool(
                    name="list_recipes",
                    description="List all recipes from Paprika with their basic information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of recipes to return (default: 50)",
                                "default": 50,
                            }
                        },
                    },
                ),
                Tool(
                    name="add_meal_to_plan",
                    description="Add a meal to the meal plan",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "meal": {
                                "type": "string",
                                "description": "Meal name for fuzzy matching (optional if meal_id provided)",
                            },
                            "meal_id": {
                                "type": "string",
                                "description": "Recipe UUID (optional if meal provided)",
                            },
                            "date": {
                                "type": "string",
                                "description": 'Date in flexible format - accepts "YYYY-MM-DD", "dd mmm", "dd mmmm", etc. (preferred: "YYYY-MM-DD"). Optional, defaults to next day that doesn\'t have a meal of that type yet',
                            },
                            "type": {
                                "type": "string",
                                "description": "Meal type (default: dinner)",
                                "default": "dinner",
                            },
                        },
                    },
                ),
                Tool(
                    name="remove_meal_from_plan",
                    description="Remove a meal from the meal plan. If no arguments provided, removes meal on latest date in mealplan",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "meal": {
                                "type": "string",
                                "description": "Meal name (optional)",
                            },
                            "meal_id": {
                                "type": "string",
                                "description": "Recipe UUID (optional)",
                            },
                            "date": {
                                "type": "string",
                                "description": 'Date in flexible format - accepts "YYYY-MM-DD", "dd mmm", "dd mmmm", etc. (preferred: "YYYY-MM-DD"). Optional, defaults to last day with matching meal',
                            },
                            "type": {
                                "type": "string",
                                "description": "Meal type for filtering (default: dinner)",
                                "default": "dinner",
                            },
                        },
                    },
                ),
                Tool(
                    name="list_meal_plan",
                    description="List meal plan entries",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "num_days": {
                                "type": "integer",
                                "description": "Number of days to show (default: 10)",
                                "default": 10,
                            },
                            "meal_type": {
                                "type": "string",
                                "description": "Filter by meal type (default: dinner)",
                                "default": "dinner",
                            },
                        },
                    },
                ),
            ]

        @server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool calls."""
            try:
                if name == "create_recipe":
                    result = await paprika_client.create_recipe(
                        name=arguments["name"],
                        ingredients=arguments["ingredients"],
                        directions=arguments["directions"],
                        description=arguments.get("description", ""),
                        notes=arguments.get("notes", ""),
                        servings=arguments.get("servings", ""),
                        prep_time=arguments.get("prep_time", ""),
                        cook_time=arguments.get("cook_time", ""),
                        difficulty=arguments.get("difficulty", ""),
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Successfully created recipe '{result['name']}' with UID: {result['uid']}",
                        )
                    ]

                elif name == "update_recipe":
                    result = await paprika_client.update_recipe(
                        uid=arguments["uid"],
                        name=arguments["name"],
                        ingredients=arguments["ingredients"],
                        directions=arguments["directions"],
                        description=arguments.get("description", ""),
                        notes=arguments.get("notes", ""),
                        servings=arguments.get("servings", ""),
                        prep_time=arguments.get("prep_time", ""),
                        cook_time=arguments.get("cook_time", ""),
                        difficulty=arguments.get("difficulty", ""),
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Successfully updated recipe '{result['name']}'",
                        )
                    ]

                elif name == "update_recipe_partial":
                    result = await paprika_client.update_recipe_partial(
                        uid=arguments["uid"],
                        **{
                            k: v
                            for k, v in arguments.items()
                            if k != "uid" and v is not None
                        },
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Successfully updated recipe '{result['name']}' (partial update)",
                        )
                    ]

                elif name == "list_recipes":
                    limit = arguments.get("limit", 50)
                    recipes = await paprika_client.list_recipes(limit=limit)

                    if not recipes:
                        return [
                            TextContent(
                                type="text",
                                text="No recipes found in your Paprika account.",
                            )
                        ]

                    # Format recipe list
                    recipe_text = f"Found {len(recipes)} recipes:\n\n"
                    for recipe in recipes:
                        recipe_text += f"• **{recipe['name']}**\n"
                        recipe_text += f"  UID: {recipe['uid']}\n"
                        if recipe.get("description"):
                            recipe_text += f"  Description: {recipe['description']}\n"
                        if recipe.get("servings"):
                            recipe_text += f"  Servings: {recipe['servings']}\n"
                        if recipe.get("prep_time") or recipe.get("cook_time"):
                            times = []
                            if recipe.get("prep_time"):
                                times.append(f"Prep: {recipe['prep_time']}")
                            if recipe.get("cook_time"):
                                times.append(f"Cook: {recipe['cook_time']}")
                            recipe_text += f"  Time: {', '.join(times)}\n"
                        if recipe.get("last_planned"):
                            recipe_text += f"  Last planned: {recipe['last_planned']}\n"
                        if recipe.get("ingredients"):
                            ingredients_lines = recipe["ingredients"].split("\n")
                            ingredients_preview = "\n    ".join(ingredients_lines)
                            recipe_text += (
                                f"  Ingredients:\n    {ingredients_preview}\n"
                            )
                        recipe_text += "\n"

                    return [TextContent(type="text", text=recipe_text)]

                elif name == "add_meal_to_plan":
                    meal = arguments.get("meal")
                    meal_id = arguments.get("meal_id")
                    date = arguments.get("date")
                    meal_type = arguments.get("type", "dinner")

                    result = await paprika_client.add_meal_to_plan(
                        meal=meal, meal_id=meal_id, date=date, meal_type=meal_type
                    )

                    # Get meal plan to count meals by type
                    all_meals = await paprika_client.get_meal_plan(num_days=365, meal_type=None)
                    lunch_count = sum(1 for m in all_meals if m.get("type", "").lower() == "lunch")
                    dinner_count = sum(1 for m in all_meals if m.get("type", "").lower() == "dinner")

                    # Format readable date
                    formatted_date = paprika_client._format_date_readable(result["date"])

                    response_text = (
                        f"Meal '{result['meal']}' added to the meal plan on {formatted_date}. "
                        f"Now {lunch_count} lunches and {dinner_count} dinners are planned."
                    )

                    return [TextContent(type="text", text=response_text)]

                elif name == "remove_meal_from_plan":
                    meal = arguments.get("meal")
                    meal_id = arguments.get("meal_id")
                    date = arguments.get("date")
                    meal_type = arguments.get("type", "dinner")

                    result = await paprika_client.remove_meal_from_plan(
                        meal=meal, meal_id=meal_id, date=date, meal_type=meal_type
                    )

                    # Format readable date
                    formatted_date = paprika_client._format_date_readable(result["date"])

                    response_text = (
                        f"Meal '{result['meal']}' removed from meal plan on {formatted_date}"
                    )

                    return [TextContent(type="text", text=response_text)]

                elif name == "list_meal_plan":
                    num_days = arguments.get("num_days", 10)
                    meal_type = arguments.get("meal_type", "dinner")

                    meals = await paprika_client.get_meal_plan(
                        num_days=num_days, meal_type=meal_type
                    )

                    if not meals:
                        return [
                            TextContent(
                                type="text",
                                text="No meals found in your meal plan for the specified criteria.",
                            )
                        ]

                    # Format meal plan list
                    meal_text = f"Found {len(meals)} meal(s) in your meal plan:\n\n"
                    for meal_entry in meals:
                        formatted_date = paprika_client._format_date_readable(meal_entry["date"])
                        meal_text += f"• **{meal_entry['meal']}**\n"
                        meal_text += f"  Date: {formatted_date}\n"
                        meal_text += f"  Type: {meal_entry['type']}\n"
                        meal_text += f"  Recipe ID: {meal_entry['meal_ID']}\n\n"

                    return [TextContent(type="text", text=meal_text)]

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

            except MealMatchAmbiguousError as e:
                # Format ambiguous match error with suggestions
                match_names = [m.get("name", "Unknown") for m in e.matches]
                suggestions = ", ".join(match_names)
                return [
                    TextContent(
                        type="text",
                        text=f"Did you mean these? {suggestions}",
                    )
                ]

            except MealNotFoundError as e:
                return [TextContent(type="text", text=str(e))]

            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                # Per non-functional requirements: show API errors literally
                error_msg = str(e)
                return [
                    TextContent(type="text", text=f"Error executing {name}: {error_msg}")
                ]

        # Run the server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="paprika-mcp-python",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    except Exception as e:
        logger.error(f"Server startup failed: {str(e)}")
        raise
    finally:
        if paprika_client:
            await paprika_client.close()


if __name__ == "__main__":
    asyncio.run(main())
