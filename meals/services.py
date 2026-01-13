from datetime import date, timedelta

# In-memory stores
_meals = {}
_ingredients = {}
_next_meal_id = 1
_next_ingredient_id = 1


def get_meals_for_week(start_date):
    """Return all meals for the 7-day period starting at start_date."""
    end_date = start_date + timedelta(days=6)
    return [
        meal for meal in _meals.values()
        if start_date <= meal["date"] <= end_date
    ]


def get_meal(meal_id):
    """Return a single meal by ID, or None if not found."""
    meal = _meals.get(meal_id)
    if meal is None:
        return None
    return {
        **meal,
        "ingredients": [
            ing for ing in _ingredients.values()
            if ing["meal_id"] == meal_id
        ],
    }


def create_meal(payload, username):
    """Create a new meal. payload should have 'name', 'date', and optionally 'meal_type'."""
    global _next_meal_id
    meal_id = _next_meal_id
    _next_meal_id += 1
    meal = {
        "id": meal_id,
        "name": payload["name"],
        "date": payload["date"],
        "meal_type": payload.get("meal_type", "dinner"),
        "notes": payload.get("notes", ""),
        "created_by_username": username,
    }
    _meals[meal_id] = meal
    return meal


def update_meal(meal_id, payload):
    """Update an existing meal. Returns updated meal or None if not found."""
    if meal_id not in _meals:
        return None
    meal = _meals[meal_id]
    if "name" in payload:
        meal["name"] = payload["name"]
    if "date" in payload:
        meal["date"] = payload["date"]
    if "meal_type" in payload:
        meal["meal_type"] = payload["meal_type"]
    if "notes" in payload:
        meal["notes"] = payload["notes"]
    return meal


def add_ingredient(meal_id, payload):
    """Add an ingredient to a meal. payload should have 'name' and optionally 'quantity'."""
    global _next_ingredient_id
    if meal_id not in _meals:
        return None
    ingredient_id = _next_ingredient_id
    _next_ingredient_id += 1
    ingredient = {
        "id": ingredient_id,
        "meal_id": meal_id,
        "name": payload["name"],
        "quantity": payload.get("quantity", ""),
        "is_on_hand": False,
    }
    _ingredients[ingredient_id] = ingredient
    return ingredient


def toggle_ingredient(meal_id, ingredient_id):
    """Toggle the checked status of an ingredient. Returns updated ingredient or None."""
    ingredient = _ingredients.get(ingredient_id)
    if ingredient is None or ingredient["meal_id"] != meal_id:
        return None
    ingredient["is_on_hand"] = not ingredient["is_on_hand"]
    return ingredient
