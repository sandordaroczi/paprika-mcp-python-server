# Specifications for meal-planning functionality

## Add a meal to the mealplan

```text
User>
 Add pasta bolognese to meal plan
Tool call>
 add_meal_to_plan(meal="pasta bolognese")
Tool response>
 meal: "Pasta Bolognese"
 meal_ID: 23232
 date: 2025-11-03
 type: "dinner"
Assistant>
 Pasta bolognese added to the the meal plan at 3 November 2025. Now 2 lunches and 3 dinners are planned.
```


Tool: add_meal_to_plan  
Arguments:
- meal: "pasta bolognese" OR meal_ID: 23232
- date: "2025-11-03" (optional, defaults to next day that doesn't have a meal of that type yet)
- type: "dinner" (optional, defaults to dinner)


meal can be selected by specifying the title or the UUID.
matching meal title with the available meals will happen in a fuzzy way with some kind of distance function. If the match is mediocre then say: "Meal description didn't match an existing recipe. Nothing added to plan. Did you mean one of these?" and list potential matches. If the match is poor then just say that the recipe is unknown and offer to list all recipies.

## Remove a meal from the mealplan

User>
 Remove pasta bolognese from meal plan
Tool call>
 remove_meal_from_plan(meal="pasta bolognese")
Tool response>
 result: "Meal removed"
 meal: "Pasta Bolognese"
 meal_ID: "22360F6A6-9CA8-4F52-87EB-F42E51C9307C3232"
 date: 2025-11-03
 type: "dinner"

User>
 Remove meal from 3 november
Tool call>
 remove_meal_from_plan(date="2025-11-03")
Tool response>
 result: "Meal removed"
 meal: "Pasta Bolognese"
 meal_ID: "22360F6A6-9CA8-4F52-87EB-F42E51C9307C3232"
 date: 2025-11-03
 type: "dinner"

Tool: remove_meal_from_plan  
Arguments:
- meal: "pasta bolognese" OR meal_ID: 23232 OR date: "2025-11-03" or nothing (in which case the meal on the latest date in the mealplan is removed)
- date: "2025-11-03" (optional, defaults to last day with matching meal)
- type: "dinner" (optional, defaults to dinner)

 ## List meal plan

```
 User>
  What does my meal plan look like?
Tool call>
 list_meal_plan()
Tool response>
[
    {
        meal: "Pasta Bolognese"
        meal_ID: "22360F6A6-9CA8-4F52-87EB-F42E51C9307C3232"
        date: 2025-11-03
        type: "dinner"
    },
    {
        meal: "Pizza Margarita"
        meal_ID: "2321360F6A6-9CF8-4F52-87EB-F42E51C9809C35"
        date: 2025-11-04
        type: "dinner"
    }
]
```

 tool: list_meal_plan  
 arguments:
  - optional num_days = 10
  - optional meal_type = 'dinner'


## Add last_planned to list_recipes
Enhance the list_recipes by adding a `last_planned` attribute to the returned info. It is the date on which the recipe was last planned. This can be used by the LLM in mealplanning such that recently planned recipes are not repeated too often.

Pseudocode for calculating last_planned for each recipe:
- fetch all planned meals in the last 366 days
- for each recipe:
    - loop over all planned meals
        - if the meal matches the current recipe
            - save the most recent date as last_planned

Note that last_planned can be empty in which case it doesn't need to be returned.


# Nonfunctional requirements
- Errors from Paprika API must be shown litterally in the response.
- Mealplanning example with API endpoint URLs can be found here (it's in Go, but treat it as inspiration) https://github.com/soggycactus/paprika-3-mcp/blob/5a81214b157d0184aeb9bfdc0762f6bacfe58032/internal/paprika/client.go
- Date inputs must be forgiving. So yyyy-mm-dd or dd mmm or dd mmmm are all fine. However, just to be sure specify what format is expected in the MCP descriptions.
- There can only be one meal of a particular type per day. No need to enforce this.

# Future expansion (not in scope of this feature)
We are working towards the situation where the user can say: "Plan a week of meals".
The agent then lists the meals, sorts them by 'last_prepared' date. Filters by 'summer' or 'winter' depending on the season and then picks and plans a few meals.