import asyncio
import logging
from typing import Any

from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from config import get_config
from paprika_client import PaprikaClient

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
                    name="get_grocery_lists",
                    description="Get all grocery list names from Paprika",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="get_groceries",
                    description="Get all groceries from a grocery list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "grocery_list_name": {
                                "type": "string",
                                "description": "Name of the grocery list (optional, defaults to default list)",
                            }
                        },
                    },
                ),
                Tool(
                    name="get_grocery",
                    description="Get a specific grocery item by name from a grocery list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "item_name": {
                                "type": "string",
                                "description": "Name of the grocery item",
                            },
                            "grocery_list_name": {
                                "type": "string",
                                "description": "Name of the grocery list (optional, defaults to default list)",
                            },
                        },
                        "required": ["item_name"],
                    },
                ),
                Tool(
                    name="add_grocery",
                    description="Add a grocery item to a grocery list (adds to existing quantity if item already exists). Quantity can be an integer or string like '1 kilo', '4 liters', or '-2 kilos' to subtract.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "item_name": {
                                "type": "string",
                                "description": "Name of the grocery item to add",
                            },
                            "quantity": {
                                "type": "string",
                                "description": "Quantity to add (default: '1'). Can be a number or string with unit like '1 kilo', '4 liters'. Use negative values like '-2 kilos' to subtract.",
                                "default": "1",
                            },
                            "grocery_list_name": {
                                "type": "string",
                                "description": "Name of the grocery list (optional, defaults to default list)",
                            },
                        },
                        "required": ["item_name"],
                    },
                ),
                Tool(
                    name="clear_grocery_list",
                    description="Clear all items from a grocery list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "grocery_list_name": {
                                "type": "string",
                                "description": "Name of the grocery list (optional, defaults to default list)",
                            }
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
                        if recipe.get("ingredients"):
                            ingredients_lines = recipe["ingredients"].split("\n")
                            ingredients_preview = "\n    ".join(ingredients_lines)
                            recipe_text += (
                                f"  Ingredients:\n    {ingredients_preview}\n"
                            )
                        recipe_text += "\n"

                    return [TextContent(type="text", text=recipe_text)]

                elif name == "get_grocery_lists":
                    lists = await paprika_client.get_grocery_lists()
                    if not lists:
                        return [
                            TextContent(
                                type="text",
                                text="No grocery lists found in your Paprika account.",
                            )
                        ]
                    list_text = "Grocery lists:\n"
                    for grocery_list in lists:
                        list_name = grocery_list.get("name", "")
                        is_default = grocery_list.get("is_default", False)
                        default_marker = " (default)" if is_default else ""
                        list_text += f"- {list_name}{default_marker}\n"
                    return [TextContent(type="text", text=list_text)]

                elif name == "get_groceries":
                    grocery_list_name = arguments.get("grocery_list_name")
                    groceries = await paprika_client.get_groceries(grocery_list_name)
                    if not groceries:
                        list_name = grocery_list_name or "default"
                        return [
                            TextContent(
                                type="text",
                                text=f"No groceries found in '{list_name}' list.",
                            )
                        ]
                    grocery_text = (
                        f"Groceries on {grocery_list_name or 'default'} list:\n"
                    )
                    for grocery in groceries:
                        quantity = grocery.get("quantity", "")
                        name = grocery.get("name", "")
                        grocery_text += f"- {quantity}, {name}\n"
                    return [TextContent(type="text", text=grocery_text)]

                elif name == "get_grocery":
                    item_name = arguments["item_name"]
                    grocery_list_name = arguments.get("grocery_list_name")
                    grocery = await paprika_client.get_grocery(
                        item_name, grocery_list_name
                    )
                    if not grocery:
                        list_name = grocery_list_name or "default"
                        return [
                            TextContent(
                                type="text",
                                text=f"Grocery item '{item_name}' not found in '{list_name}' list.",
                            )
                        ]
                    # Format response with name and quantity (from full grocery object)
                    quantity = grocery.get("quantity", "")
                    name = grocery.get("name", "")
                    return [
                        TextContent(
                            type="text",
                            text=f"Grocery item: {name}\nQuantity: {quantity}",
                        )
                    ]

                elif name == "add_grocery":
                    item_name = arguments["item_name"]
                    quantity = arguments.get("quantity", "1")
                    # Convert to string if it's an integer for consistency
                    if isinstance(quantity, int):
                        quantity = str(quantity)
                    grocery_list_name = arguments.get("grocery_list_name")
                    result = await paprika_client.add_grocery(
                        item_name, quantity, grocery_list_name
                    )
                    return [
                        TextContent(
                            type="text",
                            text=f"Added {quantity} '{item_name}' to grocery list. Total quantity: {result['quantity']}",
                        )
                    ]

                elif name == "clear_grocery_list":
                    grocery_list_name = arguments.get("grocery_list_name")
                    await paprika_client.clear_grocery_list(grocery_list_name)
                    list_name = grocery_list_name or "default"
                    return [
                        TextContent(
                            type="text",
                            text=f"Successfully cleared '{list_name}' grocery list.",
                        )
                    ]

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]

            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                # Return human-readable error message
                error_message = str(e)
                if "PaprikaAPIError" in str(type(e)):
                    # Extract the actual error message from PaprikaAPIError
                    error_message = error_message
                return [
                    TextContent(
                        type="text", text=f"Error executing {name}: {error_message}"
                    )
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
