# Paprika MCP Python Server

A Model Context Protocol (MCP) server that integrates Paprika Recipe Manager with Claude Desktop and Cursor, enabling natural language recipe and grocery list management through AI conversation.

## Features

- **Recipe Management**: Create, update, and list recipes with natural language descriptions
- **Grocery List Management**: Manage grocery lists with support for quantities with units (e.g., "4 kilos", "3 liters")
- **Smart Quantity Handling**: Add, subtract, and track grocery items with unit-aware quantity management
- **Multiple Lists**: Support for multiple grocery lists with default list fallback

## Demo

### Creating Recipes
![Creating a recipe with natural language](images/demo-create-recipe.png)

### Recipe Recommendations  
![Getting recipe recommendations](images/demo-list-recipes.png)

### Adding to grocery list (Cursor)
![Adding to grocery list](images/demo-add-to-grocerylist-cursor.png)

## Prerequisites

- Python 3.8 or higher
- [Paprika Recipe Manager 3](https://www.paprikaapp.com/) with cloud sync enabled
- [Claude Desktop](https://claude.ai/download) application
- Valid Paprika account credentials

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/sandordaroczi/paprika-mcp-python-server.git
cd paprika-mcp-python-server

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy the example environment file and configure your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Paprika credentials:
```env
PAPRIKA_USERNAME=your_email@example.com
PAPRIKA_PASSWORD=your_paprika_password
```

### 3. Test the Server

Verify your setup by testing authentication:

```bash
python src/server.py --username your_email --password your_password
```

### 4. Configure Claude Desktop

Edit your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the MCP server configuration:

```json
{
  "mcpServers": {
    "paprika": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["/path/to/paprika-mcp-python-server/src/server.py"],
      "env": {
        "PAPRIKA_USERNAME": "your_email@example.com",
        "PAPRIKA_PASSWORD": "your_password"
      }
    }
  }
}
```

**Important**: Use absolute paths and ensure you're pointing to your virtual environment's Python interpreter.

### 5. Restart Claude Desktop

Completely quit and restart Claude Desktop for the changes to take effect.

## Usage Examples

Once configured, you can interact with your Paprika recipes through natural language in Claude:

### Create a New Recipe
```
Create a new recipe called "Spaghetti Carbonara" with these ingredients:
- 400g spaghetti
- 4 large eggs
- 100g pancetta
- 50g Parmesan cheese
- Black pepper and salt

Instructions:
1. Cook spaghetti according to package directions
2. Fry pancetta until crispy
3. Beat eggs with Parmesan
4. Combine hot pasta with pancetta
5. Add egg mixture and toss quickly
6. Season and serve immediately

Set servings to 4 people, prep time 10 minutes, cook time 15 minutes.
```

### List Your Recipes
```
Show me all my recipes from Paprika
```

### Update a Recipe
```
Update the Spaghetti Carbonara recipe to serve 6 people instead of 4, and add "Use room temperature eggs to prevent scrambling" to the notes.
```

### Partial Updates
```
For the recipe with UID [recipe-uid], just change the prep time to 15 minutes and add salt to the ingredients list.
```

### Grocery List Management
```
What grocery lists do I have?

What's on my grocery list?

Add 3 kilos of bananas to my grocery list.

How many bananas are on my grocery list?

Add 1 kilo of flour to my "baking supplies" grocery list.

Subtract 2 kilos of sugar from my grocery list.
```

## Available Tools

### Recipes

| Tool | Description |
|------|-------------|
| `create_recipe` | Create a new recipe with all details |
| `update_recipe` | Complete recipe update (all fields) |
| `update_recipe_partial` | Update only specified fields |
| `list_recipes` | List all recipes with ingredients and details |

### Groceries

| Tool | Description |
|------|-------------|
| `get_grocery_lists` | Get all grocery list names from your Paprika account |
| `get_groceries` | Get all groceries from a grocery list (defaults to default list) |
| `get_grocery` | Get a specific grocery item by name with its quantity |
| `add_grocery` | Add or update a grocery item. Supports quantities with units (e.g., "3 kilos", "4 liters") and negative values for subtraction |
| `clear_grocery_list` | Clear all items from a grocery list |

**Note on Quantities**: The `add_grocery` tool supports:
- Simple numbers: `1`, `3`, `-2`
- Quantities with units: `"3 kilos"`, `"4 liters"`, `"-2 kilos"`
- Automatic unit preservation when adding to existing items
- Error handling if subtraction would result in negative quantity

### Components

- **MCP Server** (`src/server.py`): Handles MCP protocol communication and tool routing
- **Paprika Client** (`src/paprika_client.py`): Manages Paprika API authentication and operations
- **Configuration** (`src/config.py`): Handles environment variables and CLI arguments

## Development

### Running Tests

```bash
# Install development dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/ -v
```

### Adding New Features

1. Create a feature branch: `git checkout -b feature/new-feature`
2. Add your changes with tests
3. Ensure all tests pass: `pytest`
4. Format code: `black src/ tests/`
5. Commit and push your changes

## Troubleshooting

### Common Issues

#### Authentication Failed
- Verify your Paprika credentials work at [paprikaapp.com](https://paprikaapp.com)
- Ensure cloud sync is enabled in your Paprika app
- Check that credentials are correctly set in environment variables

#### Claude Connection Issues
- Verify Python path in Claude config points to your virtual environment
- Check that server.py path is absolute and correct
- Ensure all required packages are installed in the virtual environment

#### Import Errors
- Confirm virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt`
- Check Python version compatibility (3.8+)

## API Rate Limiting

The Paprika API enforces rate limiting to protect their service. When using this server it is advised to avoid making excessive or bulky requests in short periods of time.

## Contributing

Contributions are welcome! Whether you want to report bugs, suggest new features, improve documentation, or submit code changes, your input helps make this project better. Feel free to open an issue for discussions or submit a pull request with your improvements.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Anthropic](https://www.anthropic.com/) for the Model Context Protocol
- [Paprika Recipe Manager](https://www.paprikaapp.com/) for the excellent recipe management app
- The MCP community for documentation and examples

## Changelog

### v1.1.0 (2025-11-01)
- **Grocery List Management**: Complete grocery list functionality
  - List all grocery lists
  - Get groceries from any list
  - Query specific grocery items
  - Add/update groceries with quantity support
  - Clear grocery lists
- **Smart Quantity Handling**: 
  - Support for quantities with units ("4 kilos", "3 liters")
  - Automatic unit preservation when adding quantities
  - Negative quantity support for subtraction
  - Proper error handling for invalid operations
- **Enhanced Error Messages**: Invalid grocery list names now show available valid lists

### v1.0.0 (2025-09-27)
- Initial release
- Recipe creation, updating, and listing functionality
- Full and partial update capabilities

---

**Note**: This is an unofficial integration and is not affiliated with or endorsed by Paprika Recipe Manager or Anthropic.