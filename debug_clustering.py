#!/usr/bin/env python3
"""
Debug script to test module clustering with Claude Code CLI.

Usage:
    cd ~/src/CodeWiki
    .venv/bin/python debug_clustering.py
"""

import json
import logging
import sys

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Sample test data - a small subset of components
TEST_DEPENDENCY_GRAPH = {
    "metadata": {
        "repo_path": "/test/repo",
        "analyzed_at": "2024-01-01T00:00:00Z"
    },
    "components": {
        "App.Services.Auth.LoginService": {
            "name": "LoginService",
            "type": "class",
            "file_path": "/test/repo/app/Services/Auth/LoginService.php",
            "relative_path": "app/Services/Auth/LoginService.php",
            "source_code": "class LoginService { public function login() {} }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 10
        },
        "App.Services.Auth.RegisterService": {
            "name": "RegisterService",
            "type": "class",
            "file_path": "/test/repo/app/Services/Auth/RegisterService.php",
            "relative_path": "app/Services/Auth/RegisterService.php",
            "source_code": "class RegisterService { public function register() {} }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 15
        },
        "App.Services.Auth.TokenService": {
            "name": "TokenService",
            "type": "class",
            "file_path": "/test/repo/app/Services/Auth/TokenService.php",
            "relative_path": "app/Services/Auth/TokenService.php",
            "source_code": "class TokenService { public function generateToken() {} }",
            "depends_on": [],
            "start_line": 1,
            "end_line": 20
        },
        "App.Controllers.UserController": {
            "name": "UserController",
            "type": "class",
            "file_path": "/test/repo/app/Controllers/UserController.php",
            "relative_path": "app/Controllers/UserController.php",
            "source_code": "class UserController { public function show() {} }",
            "depends_on": ["App.Services.Auth.LoginService", "App.Models.User"],
            "start_line": 1,
            "end_line": 25
        },
        "App.Controllers.ProfileController": {
            "name": "ProfileController",
            "type": "class",
            "file_path": "/test/repo/app/Controllers/ProfileController.php",
            "relative_path": "app/Controllers/ProfileController.php",
            "source_code": "class ProfileController { public function update() {} }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 30
        },
        "App.Models.User": {
            "name": "User",
            "type": "class",
            "file_path": "/test/repo/app/Models/User.php",
            "relative_path": "app/Models/User.php",
            "source_code": "class User extends Model { protected $table = 'users'; }",
            "depends_on": [],
            "start_line": 1,
            "end_line": 50
        },
        "App.Models.Profile": {
            "name": "Profile",
            "type": "class",
            "file_path": "/test/repo/app/Models/Profile.php",
            "relative_path": "app/Models/Profile.php",
            "source_code": "class Profile extends Model { protected $table = 'profiles'; }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 40
        },
        "App.Services.Orders.OrderService": {
            "name": "OrderService",
            "type": "class",
            "file_path": "/test/repo/app/Services/Orders/OrderService.php",
            "relative_path": "app/Services/Orders/OrderService.php",
            "source_code": "class OrderService { public function create() {} }",
            "depends_on": ["App.Models.Order", "App.Models.User"],
            "start_line": 1,
            "end_line": 60
        },
        "App.Services.Orders.OrderValidationService": {
            "name": "OrderValidationService",
            "type": "class",
            "file_path": "/test/repo/app/Services/Orders/OrderValidationService.php",
            "relative_path": "app/Services/Orders/OrderValidationService.php",
            "source_code": "class OrderValidationService { public function validate() {} }",
            "depends_on": ["App.Models.Order"],
            "start_line": 1,
            "end_line": 45
        },
        "App.Models.Order": {
            "name": "Order",
            "type": "class",
            "file_path": "/test/repo/app/Models/Order.php",
            "relative_path": "app/Models/Order.php",
            "source_code": "class Order extends Model { protected $table = 'orders'; }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 80
        },
        "App.Controllers.OrderController": {
            "name": "OrderController",
            "type": "class",
            "file_path": "/test/repo/app/Controllers/OrderController.php",
            "relative_path": "app/Controllers/OrderController.php",
            "source_code": "class OrderController { public function index() {} }",
            "depends_on": ["App.Services.Orders.OrderService", "App.Models.Order"],
            "start_line": 1,
            "end_line": 55
        },
        "App.Repositories.UserRepository": {
            "name": "UserRepository",
            "type": "class",
            "file_path": "/test/repo/app/Repositories/UserRepository.php",
            "relative_path": "app/Repositories/UserRepository.php",
            "source_code": "class UserRepository { public function find() {} }",
            "depends_on": ["App.Models.User"],
            "start_line": 1,
            "end_line": 35
        },
        "App.Repositories.OrderRepository": {
            "name": "OrderRepository",
            "type": "class",
            "file_path": "/test/repo/app/Repositories/OrderRepository.php",
            "relative_path": "app/Repositories/OrderRepository.php",
            "source_code": "class OrderRepository { public function find() {} }",
            "depends_on": ["App.Models.Order"],
            "start_line": 1,
            "end_line": 40
        }
    },
    "leaf_nodes": [
        "App.Services.Auth.LoginService",
        "App.Services.Auth.RegisterService",
        "App.Services.Auth.TokenService",
        "App.Controllers.UserController",
        "App.Controllers.ProfileController",
        "App.Models.User",
        "App.Models.Profile",
        "App.Services.Orders.OrderService",
        "App.Services.Orders.OrderValidationService",
        "App.Models.Order",
        "App.Controllers.OrderController",
        "App.Repositories.UserRepository",
        "App.Repositories.OrderRepository"
    ]
}


def test_prompt_generation():
    """Test just the prompt generation without calling Claude."""
    from codewiki.src.be.cluster_modules import format_potential_core_components
    from codewiki.src.be.prompt_template_v2 import format_cluster_prompt_v2
    from codewiki.src.be.dependency_analyzer.models.core import Node

    # Convert test data to Node objects
    components = {}
    for comp_id, comp_data in TEST_DEPENDENCY_GRAPH["components"].items():
        components[comp_id] = Node(
            id=comp_id,
            name=comp_data.get("name", ""),
            component_type=comp_data.get("type", "unknown"),
            file_path=comp_data.get("file_path", ""),
            relative_path=comp_data.get("relative_path", ""),
            source_code=comp_data.get("source_code"),
            depends_on=set(comp_data.get("depends_on", [])),
            start_line=comp_data.get("start_line", 0),
            end_line=comp_data.get("end_line", 0),
        )

    leaf_nodes = TEST_DEPENDENCY_GRAPH["leaf_nodes"]

    # Format the components
    potential_core_components, _ = format_potential_core_components(leaf_nodes, components)

    # Generate the V2 prompt
    prompt = format_cluster_prompt_v2(potential_core_components)

    print("=" * 80)
    print("GENERATED V2 PROMPT:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    print(f"\nPrompt length: {len(prompt)} characters")
    print(f"Estimated tokens: ~{len(prompt) // 4}")

    return prompt


def test_clustering_with_claude_code():
    """Test the full clustering with Claude Code CLI."""
    from codewiki.src.be.claude_code_adapter import claude_code_cluster
    from codewiki.src.be.dependency_analyzer.models.core import Node
    from codewiki.src.config import Config

    # Convert test data to Node objects
    components = {}
    for comp_id, comp_data in TEST_DEPENDENCY_GRAPH["components"].items():
        components[comp_id] = Node(
            id=comp_id,
            name=comp_data.get("name", ""),
            component_type=comp_data.get("type", "unknown"),
            file_path=comp_data.get("file_path", ""),
            relative_path=comp_data.get("relative_path", ""),
            source_code=comp_data.get("source_code"),
            depends_on=set(comp_data.get("depends_on", [])),
            start_line=comp_data.get("start_line", 0),
            end_line=comp_data.get("end_line", 0),
        )

    leaf_nodes = TEST_DEPENDENCY_GRAPH["leaf_nodes"]

    # Create a minimal config
    config = Config(
        repo_path="/test/repo",
        output_dir="/tmp/codewiki-test",
        dependency_graph_dir="/tmp/codewiki-test",
        docs_dir="/tmp/codewiki-test",
        max_depth=2,
        llm_base_url="",
        llm_api_key="",
        main_model="",
        cluster_model="",
        max_token_per_module=50000,
        use_claude_code=True,
    )

    print("\n" + "=" * 80)
    print("CALLING CLAUDE CODE CLI FOR CLUSTERING...")
    print("=" * 80)

    try:
        result = claude_code_cluster(
            leaf_nodes=leaf_nodes,
            components=components,
            config=config,
            use_v2_prompts=True  # Use the new V2 prompts
        )

        print("\n" + "=" * 80)
        print("CLUSTERING RESULT:")
        print("=" * 80)
        print(json.dumps(result, indent=2))

        return result

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("CodeWiki Clustering Debug Script")
    print("=" * 80)

    if len(sys.argv) > 1 and sys.argv[1] == "--prompt-only":
        # Just show the prompt without calling Claude
        test_prompt_generation()
    else:
        # Full test with Claude Code CLI
        print("\nStep 1: Generate and show prompt")
        test_prompt_generation()

        print("\n\nStep 2: Call Claude Code CLI")
        response = input("\nProceed with Claude Code CLI call? (y/n): ")
        if response.lower() == 'y':
            test_clustering_with_claude_code()
        else:
            print("Skipped Claude Code CLI call.")


if __name__ == "__main__":
    main()
