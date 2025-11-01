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
    async def test_get_grocery_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }

            lists = await client.get_grocery_lists()
            assert lists == [
                {"name": "supermarket", "is_default": True},
                {"name": "butcher", "is_default": False},
            ]
            mock_request.assert_called_once_with("GET", "/sync/grocerylists")

    @pytest.mark.asyncio
    async def test_get_grocery_lists_empty(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": []}

            lists = await client.get_grocery_lists()
            assert lists == []

    @pytest.mark.asyncio
    async def test_get_default_list_uuid(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }

            uid = await client.get_default_list_uuid()
            assert uid == "uuid1"

    @pytest.mark.asyncio
    async def test_get_default_list_uuid_not_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": False, "uid": "uuid1"},
                ]
            }

            with pytest.raises(PaprikaAPIError, match="No default grocery list found"):
                await client.get_default_list_uuid()

    @pytest.mark.asyncio
    async def test_get_groceries(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [
                        {
                            "name": "bananas",
                            "quantity": "3",
                            "list_uid": "uuid1",
                        },
                        {
                            "name": "milk",
                            "quantity": "4 liters",
                            "list_uid": "uuid1",
                        },
                        {
                            "name": "apples",
                            "quantity": "2",
                            "list_uid": "uuid2",  # Different list
                        },
                    ]
                }

                groceries = await client.get_groceries()
                assert len(groceries) == 2
                assert {"name": "bananas", "quantity": "3"} in groceries
                assert {"name": "milk", "quantity": "4 liters"} in groceries

    @pytest.mark.asyncio
    async def test_get_grocery_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [
                        {
                            "name": "bananas",
                            "quantity": "3",
                            "list_uid": "uuid1",
                            "uid": "grocery_uid",
                        },
                    ]
                }

                grocery = await client.get_grocery("bananas")
                assert grocery is not None
                assert grocery["name"] == "bananas"
                assert grocery["quantity"] == "3"

    @pytest.mark.asyncio
    async def test_get_grocery_not_found(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {"result": []}

                grocery = await client.get_grocery("bananas")
                assert grocery is None

    @pytest.mark.asyncio
    async def test_get_list_uuid_by_name_invalid_with_valid_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {
                "result": [
                    {"name": "supermarket", "is_default": True, "uid": "uuid1"},
                    {"name": "butcher", "is_default": False, "uid": "uuid2"},
                ]
            }

            with pytest.raises(PaprikaAPIError) as exc_info:
                await client._get_list_uuid_by_name("invalid_list")
            assert "Grocery list 'invalid_list' not found" in str(exc_info.value)
            assert "Valid grocery lists are" in str(exc_info.value)
            assert "'supermarket'" in str(exc_info.value)
            assert "'butcher'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_list_uuid_by_name_invalid_no_lists(self, client):
        client.token = "test_token"
        with patch.object(client, "_make_authenticated_request") as mock_request:
            mock_request.return_value = {"result": []}

            with pytest.raises(PaprikaAPIError) as exc_info:
                await client._get_list_uuid_by_name("invalid_list")
            assert "Grocery list 'invalid_list' not found" in str(exc_info.value)
            assert "No grocery lists are available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_grocery_new_item(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                # First call for checking existing grocery, second for adding
                mock_request.side_effect = [
                    {"result": []},  # No existing grocery
                    {"result": {"success": True}},  # Add successful
                ]

                result = await client.add_grocery("bananas", 3)
                assert result["name"] == "bananas"
                assert result["quantity"] == "3"
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_add_grocery_existing_item(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                # First call for checking existing grocery, second for updating
                mock_request.side_effect = [
                    {
                        "result": [
                            {
                                "name": "bananas",
                                "quantity": "2",
                                "list_uid": "uuid1",
                                "uid": "grocery_uid",
                            },
                        ]
                    },
                    {"result": {"success": True}},  # Update successful
                ]

                result = await client.add_grocery("bananas", 3)
                assert result["name"] == "bananas"
                assert result["quantity"] == "5"  # 2 + 3
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_add_grocery_empty_name(self, client):
        client.token = "test_token"
        with pytest.raises(PaprikaAPIError, match="Item name cannot be empty"):
            await client.add_grocery("", 1)

    def test_parse_quantity_with_unit(self, client):
        """Test parsing quantities with units."""
        value, unit = client._parse_quantity("4 kilos")
        assert value == 4.0
        assert unit == "kilos"

        value, unit = client._parse_quantity("3 liters")
        assert value == 3.0
        assert unit == "liters"

        value, unit = client._parse_quantity("5")
        assert value == 5.0
        assert unit is None

        value, unit = client._parse_quantity("-2 kilos")
        assert value == -2.0
        assert unit == "kilos"

    def test_add_quantities_with_units(self, client):
        """Test adding quantities with units."""
        result, _ = client._add_quantities("4 kilos", "1 kilo")
        assert result == "5 kilos"

        result, _ = client._add_quantities("3 liters", "2 liters")
        assert result == "5 liters"

        result, _ = client._add_quantities("4 kilos", "2")
        assert result == "6 kilos"

        result, _ = client._add_quantities("4", "2 kilos")
        assert result == "6 kilos"

    def test_add_quantities_negative(self, client):
        """Test subtracting quantities."""
        result, _ = client._add_quantities("4 kilos", "-2 kilos")
        assert result == "2 kilos"

        result, _ = client._add_quantities("3", "-1")
        assert result == "2"

    def test_add_quantities_below_zero_error(self, client):
        """Test that adding quantities that would go below zero raises an error."""
        with pytest.raises(PaprikaAPIError, match="result would be negative"):
            client._add_quantities("1 kilo", "-2 kilos")

        with pytest.raises(PaprikaAPIError, match="result would be negative"):
            client._add_quantities("2", "-5")

    @pytest.mark.asyncio
    async def test_add_grocery_with_unit_string(self, client):
        """Test adding grocery with string quantity unit."""
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                # First call for checking existing grocery, second for adding
                mock_request.side_effect = [
                    {"result": []},  # No existing grocery
                    {"result": {"success": True}},  # Add successful
                ]

                result = await client.add_grocery("bananas", "3 kilos")
                assert result["name"] == "bananas"
                assert result["quantity"] == "3 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_existing_with_unit(self, client):
        """Test adding to existing grocery with unit."""
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                # First call for checking existing grocery, second for updating
                mock_request.side_effect = [
                    {
                        "result": [
                            {
                                "name": "bananas",
                                "quantity": "4 kilos",
                                "list_uid": "uuid1",
                                "uid": "grocery_uid",
                            },
                        ]
                    },
                    {"result": {"success": True}},  # Update successful
                ]

                result = await client.add_grocery("bananas", "1 kilo")
                assert result["name"] == "bananas"
                assert result["quantity"] == "5 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_subtract_with_unit(self, client):
        """Test subtracting from grocery with unit."""
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.side_effect = [
                    {
                        "result": [
                            {
                                "name": "bananas",
                                "quantity": "4 kilos",
                                "list_uid": "uuid1",
                                "uid": "grocery_uid",
                            },
                        ]
                    },
                    {"result": {"success": True}},
                ]

                result = await client.add_grocery("bananas", "-2 kilos")
                assert result["name"] == "bananas"
                assert result["quantity"] == "2 kilos"

    @pytest.mark.asyncio
    async def test_add_grocery_subtract_below_zero_error(self, client):
        """Test that subtracting below zero raises an error."""
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {
                    "result": [
                        {
                            "name": "bananas",
                            "quantity": "1 kilo",
                            "list_uid": "uuid1",
                            "uid": "grocery_uid",
                        },
                    ]
                }

                with pytest.raises(PaprikaAPIError, match="result would be negative"):
                    await client.add_grocery("bananas", "-2 kilos")

    @pytest.mark.asyncio
    async def test_clear_grocery_list(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                # First call to get groceries, second to clear them
                mock_request.side_effect = [
                    {
                        "result": [
                            {
                                "name": "bananas",
                                "quantity": "3",
                                "list_uid": "uuid1",
                                "uid": "grocery_uid",
                                "ingredient": "bananas",
                                "recipe_uid": None,
                                "order_flag": 316,
                                "aisle": "Produce",
                                "recipe": None,
                                "instruction": "",
                                "separate": False,
                                "aisle_uid": "F94467760BF4BC6B9521FFA9329D0F1DBCCA0F5AC0808BD8552FB375A565FB9E",
                            },
                            {
                                "name": "milk",
                                "quantity": "4 liters",
                                "list_uid": "uuid1",
                                "uid": "grocery_uid2",
                                "ingredient": "milk",
                                "recipe_uid": None,
                                "order_flag": 316,
                                "aisle": "Produce",
                                "recipe": None,
                                "instruction": "",
                                "separate": False,
                                "aisle_uid": "F94467760BF4BC6B9521FFA9329D0F1DBCCA0F5AC0808BD8552FB375A565FB9E",
                            },
                        ]
                    },
                    {"result": {"success": True}},  # Clear successful
                ]

                result = await client.clear_grocery_list()
                assert result is True
                assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_clear_grocery_list_empty(self, client):
        client.token = "test_token"
        with patch.object(client, "_get_list_uuid_by_name") as mock_get_uuid:
            mock_get_uuid.return_value = "uuid1"
            with patch.object(client, "_make_authenticated_request") as mock_request:
                mock_request.return_value = {"result": []}

                result = await client.clear_grocery_list()
                assert result is True
