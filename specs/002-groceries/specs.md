# Specifications for Groceries feature
This feature allows the agent to things like this:

What grocery lists do I have?
- tool call: get_grocery_lists()
- tool output:
    - "supermarket" (default)
    - "butcher"

What's on my grocery list?
- tool call: get_groceries(grocery_list_name)
- tool output:
    - "3", "bananas"
    - "4 liters", "milk"

How many bananas are on my grocery list?
- tool call: get_grocery(item_name, optional grocery_list_name)
- tool output:
    - name: bananas
    - quantity: 3
    
How much milk is on my grocery list?
- tool call: get_grocery(item_name, optional grocery_list_name)
- tool output:
    - name: milk
    - quantity: "3 liters" (string)

Put peanut butter on my grocery list.
- tool call: add_grocery(item_name, quantity, optional grocery_list_name)
- tool output:
    - name: peanut butter
    - quantity: 3 (apparently there were already 2 peanut butter on the list)

Clear the grocery list.
- tool call: clear_grocery_list(grocery_list_name)

- get_grocery_lists() also returns if a list is the default list.
- If an invalid grocery_list_name is provided, then throw an error that says what the valid grocery lists are.
- Quantity is a string and can be something like "4 kilos".
- When adding quantities then these are added properly, so adding "1 kilo" to "4 kilos" becomes "5 kilos".
- Quantity can be negative, which means substracting quantities. These cannot go below zero. If they do, a proper error is thrown.


# Non-functional requirements
- Create a function for fetching the default list UUID
- Return decent human-readable errors in case a toolcall fails