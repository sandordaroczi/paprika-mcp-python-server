from unittest.mock import AsyncMock, patch

import pytest

from src.paprika_client import PaprikaAPIError, PaprikaClient


class TestPaprikaClient:
    @pytest.fixture
    def client(self):
        return PaprikaClient("test@example.com", "testpass")

    @pytest.mark.asyncio
    async def test_authentication_success(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"result": {"token": "test_token"}}
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            token = await client.authenticate()
            assert token == "test_token"
            assert client.token == "test_token"

    @pytest.mark.asyncio
    async def test_authentication_failure(self, client):
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_post.return_value.__aenter__.return_value = mock_response
            mock_post.return_value.__aexit__.return_value = None

            with pytest.raises(PaprikaAPIError):
                await client.authenticate()

    @pytest.mark.asyncio
    async def test_list_recipes_with_last_planned(self, client):
        """Test list_recipes includes last_planned date when available."""
        # Mock recipe list response
        recipe_list_response = {
            "result": [
                {"uid": "recipe-1"},
                {"uid": "recipe-2"},
            ]
        }

        # Mock individual recipe responses
        recipe_1_data = {
            "result": {
                "uid": "recipe-1",
                "name": "Pasta Bolognese",
                "in_trash": False,
            }
        }

        recipe_2_data = {
            "result": {
                "uid": "recipe-2",
                "name": "Pizza Margarita",
                "in_trash": False,
            }
        }

        # Mock meal plan with last_planned dates
        meal_plan_mock = [
            {
                "meal": "Pasta Bolognese",
                "meal_ID": "recipe-1",
                "date": "2025-10-15",
                "type": "dinner",
            },
            {
                "meal": "Pasta Bolognese",
                "meal_ID": "recipe-1",
                "date": "2025-11-01",  # More recent date
                "type": "dinner",
            },
            {
                "meal": "Pizza Margarita",
                "meal_ID": "recipe-2",
                "date": "2025-10-20",
                "type": "dinner",
            },
        ]

        with patch.object(
            client, "get_meal_plan", new_callable=AsyncMock
        ) as mock_get_meal_plan:
            mock_get_meal_plan.return_value = meal_plan_mock

            with patch.object(
                client, "_make_authenticated_request", new_callable=AsyncMock
            ) as mock_request:
                # First call: recipe list, then individual recipes
                mock_request.side_effect = [
                    recipe_list_response,
                    recipe_1_data,
                    recipe_2_data,
                ]

                recipes = await client.list_recipes(limit=50)

                # Check that recipes have last_planned dates
                assert len(recipes) == 2
                
                # Recipe 1 should have last_planned = 2025-11-01 (most recent)
                recipe_1 = next(r for r in recipes if r["uid"] == "recipe-1")
                assert recipe_1["last_planned"] == "2025-11-01"
                
                # Recipe 2 should have last_planned = 2025-10-20
                recipe_2 = next(r for r in recipes if r["uid"] == "recipe-2")
                assert recipe_2["last_planned"] == "2025-10-20"

    @pytest.mark.asyncio
    async def test_list_recipes_without_last_planned(self, client):
        """Test list_recipes works when no meal plan entries exist."""
        # Mock recipe list response
        recipe_list_response = {
            "result": [
                {"uid": "recipe-1"},
            ]
        }

        recipe_1_data = {
            "result": {
                "uid": "recipe-1",
                "name": "New Recipe",
                "in_trash": False,
            }
        }

        with patch.object(
            client, "get_meal_plan", new_callable=AsyncMock
        ) as mock_get_meal_plan:
            mock_get_meal_plan.return_value = []  # No meal plan entries

            with patch.object(
                client, "_make_authenticated_request", new_callable=AsyncMock
            ) as mock_request:
                mock_request.side_effect = [recipe_list_response, recipe_1_data]

                recipes = await client.list_recipes(limit=50)

                assert len(recipes) == 1
                recipe_1 = recipes[0]
                assert recipe_1["uid"] == "recipe-1"
                # Should not have last_planned if not in meal plan
                assert "last_planned" not in recipe_1