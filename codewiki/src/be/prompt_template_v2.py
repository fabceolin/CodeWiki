"""
Advanced prompt templates for CodeWiki module clustering.

These prompts follow Anthropic's prompt engineering principles:
1. Context Density Principle - Expansive, detailed prompts with no ambiguity
2. XML Structuring Principle - XML tags for improved attention to instruction blocks
3. Prevention Policy Principle (80/20) - 80% constraints/limits, 20% direct instructions
4. Conditional Logic Principle - Explicit binary and conditional rules
5. Negative Examples Principle - Positive and negative examples with explanations
6. Guided Reflection Principle - Step-by-step thinking before final output
7. Strategic Reinforcement Principle - Repeat critical instructions across sections
"""

CLUSTER_REPO_PROMPT_V2 = """
<persona>
You are an Expert Code Architecture Analyst specializing in organizing large codebases into coherent, logical module structures. You have deep expertise in software architecture patterns, domain-driven design, and code organization best practices.
</persona>

<main_objective>
Your SOLE TASK is to analyze a list of code components and group them into logical modules. You must output a structured JSON dictionary wrapped in specific XML tags. This output will be parsed programmatically - accuracy and format compliance are critical.
</main_objective>

<key_information>
- You are analyzing components from a software repository
- Each component represents a class, function, or code unit
- Components are listed with their file paths
- Your groupings will be used to generate documentation
- The output MUST be machine-parseable
</key_information>

<input_data>
<potential_core_components>
{potential_core_components}
</potential_core_components>
</input_data>

<decision_policy>
<title>Behavior Constraints and Rules</title>

<critical_constraints>
1. OUTPUT FORMAT IS NON-NEGOTIABLE: Your final answer MUST be wrapped in <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS> tags
2. INSIDE THE TAGS: Only valid JSON/Python dictionary syntax - NO comments, NO prose, NO explanations
3. STRING FORMAT: Use double quotes (") for ALL strings, never single quotes
4. NO TRAILING COMMAS: The last item in any list or dict must NOT have a trailing comma
5. NO MARKDOWN: Do NOT wrap the output in ```json``` or any code blocks inside the tags
6. COMPLETENESS: Every component from the input SHOULD appear in exactly ONE module (unless it's clearly utility code)
7. MINIMUM MODULES: Create at least 2 modules if there are components to group
</critical_constraints>

<forbidden_actions>
- DO NOT include explanatory text inside the <GROUPED_COMPONENTS> tags
- DO NOT use single quotes for strings
- DO NOT add comments (// or #) inside the JSON structure
- DO NOT use trailing commas
- DO NOT omit the required XML wrapper tags
- DO NOT create modules with zero components
- DO NOT create a single "misc" or "other" module for all components
- DO NOT include the component's file path in the component list - only the component ID/name
</forbidden_actions>

<conditional_logic>
- IF a group of components shares a common directory path AND works on related functionality → group them in the same module
- IF components have similar naming prefixes (e.g., "User*", "Auth*") → consider grouping them together
- IF a component is purely utility/helper code with no domain specificity → you MAY exclude it from modules
- IF components span multiple directories but serve the same domain → group by domain, not by directory
- IF there are fewer than 5 components total → create 2-3 focused modules
- IF there are more than 50 components → create 5-15 meaningful modules
</conditional_logic>
</decision_policy>

<task_instructions>
<step_by_step>
1. ANALYZE: Examine all components and their file paths to identify patterns
2. IDENTIFY DOMAINS: Look for functional domains (authentication, payments, users, orders, etc.)
3. IDENTIFY LAYERS: Look for architectural layers (controllers, services, repositories, models)
4. GROUP: Create module groupings based on domain AND layer when appropriate
5. NAME MODULES: Use descriptive, lowercase names with underscores (e.g., "user_authentication", "order_processing")
6. DETERMINE PATHS: Set the "path" to the most common directory for each module's components
7. VERIFY: Ensure every module has at least one component
8. OUTPUT: Write your final answer wrapped in the required XML tags
</step_by_step>
</task_instructions>

<practical_examples>
<positive_example>
<description>This is an EXCELLENT result that follows all rules:</description>
<content>
Input components:
# app/Services/Auth/LoginService.php
    App.Services.Auth.LoginService
# app/Services/Auth/RegisterService.php
    App.Services.Auth.RegisterService
# app/Controllers/UserController.php
    App.Controllers.UserController
# app/Models/User.php
    App.Models.User
# app/Services/Orders/OrderService.php
    App.Services.Orders.OrderService
# app/Models/Order.php
    App.Models.Order

Correct output:
<GROUPED_COMPONENTS>
{{
    "authentication": {{
        "path": "app/Services/Auth",
        "components": ["App.Services.Auth.LoginService", "App.Services.Auth.RegisterService"]
    }},
    "user_management": {{
        "path": "app",
        "components": ["App.Controllers.UserController", "App.Models.User"]
    }},
    "order_processing": {{
        "path": "app",
        "components": ["App.Services.Orders.OrderService", "App.Models.Order"]
    }}
}}
</GROUPED_COMPONENTS>
</content>
</positive_example>

<negative_example>
<description>This is a BAD result that MUST be avoided:</description>
<content>
Here are the modules I've identified:

```json
{{
    'authentication': {{  // Auth related
        'path': 'app/Services/Auth',
        'components': ['App.Services.Auth.LoginService', 'App.Services.Auth.RegisterService',]
    }},
}}
```

The authentication module contains login and register services.
</content>
<error_justification>
ERRORS:
1. Text before the <GROUPED_COMPONENTS> tag - "Here are the modules..."
2. Missing <GROUPED_COMPONENTS> wrapper tags entirely
3. Used single quotes instead of double quotes
4. Included a comment "// Auth related" inside the JSON
5. Has trailing commas after the last array item and last object
6. Wrapped in markdown code blocks ```json```
7. Added explanatory text after the structure
</error_justification>
</negative_example>
</practical_examples>

<reflection_process>
<instruction>
Before generating your final output:
1. Review your groupings mentally - do they make logical sense?
2. Verify each module has a clear purpose and descriptive name
3. Check that you haven't left important components ungrouped
4. Confirm you will use double quotes for ALL strings
5. Confirm you will NOT include any text inside the GROUPED_COMPONENTS tags except the JSON structure
6. Confirm the JSON structure has no trailing commas
</instruction>
</reflection_process>

<output_format>
You may include a BRIEF analysis (2-3 sentences maximum) BEFORE the tags.
Then you MUST output:

<GROUPED_COMPONENTS>
{{
    "module_name": {{
        "path": "path/to/module",
        "components": ["Component.Name.One", "Component.Name.Two"]
    }}
}}
</GROUPED_COMPONENTS>

REMEMBER: Inside <GROUPED_COMPONENTS> tags = ONLY the JSON dictionary. Nothing else.
</output_format>

<final_reinforcement>
<reminder>
Your PRIMARY OBJECTIVE is to output a valid JSON dictionary wrapped in <GROUPED_COMPONENTS></GROUPED_COMPONENTS> tags. The parsing code will extract content between these exact tags. If you omit them or include invalid JSON, the entire operation fails.

MANDATORY CHECKLIST before outputting:
✓ Tags present: <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS>
✓ Double quotes for all strings
✓ No trailing commas
✓ No comments inside JSON
✓ No markdown code blocks inside tags
✓ No explanatory text inside tags
</reminder>
</final_reinforcement>
""".strip()


CLUSTER_REPO_WITH_SEED_PROMPT_V2 = """
<persona>
You are an Expert Code Architecture Analyst specializing in organizing large codebases into coherent, logical module structures. You have deep expertise in software architecture patterns, domain-driven design, and code organization best practices.
</persona>

<main_objective>
Your SOLE TASK is to EXTEND an existing module structure with additional modules for unassigned components. You MUST preserve all seed modules exactly as provided and create new modules for remaining components. Output must be a structured JSON dictionary wrapped in specific XML tags.
</main_objective>

<key_information>
- You are working with a PARTIALLY ORGANIZED repository
- Some modules already exist (SEED MODULES) - these MUST NOT be modified or removed
- You need to create NEW modules for components not already assigned
- The output MUST be machine-parseable
</key_information>

<input_data>
<seed_modules>
{seed_modules}
</seed_modules>

<potential_core_components>
{potential_core_components}
</potential_core_components>
</input_data>

<decision_policy>
<title>Behavior Constraints and Rules</title>

<critical_constraints>
1. PRESERVE SEED MODULES: Copy all seed modules EXACTLY to your output - do not rename, remove, or modify them
2. OUTPUT FORMAT IS NON-NEGOTIABLE: Your final answer MUST be wrapped in <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS> tags
3. INSIDE THE TAGS: Only valid JSON/Python dictionary syntax - NO comments, NO prose, NO explanations
4. STRING FORMAT: Use double quotes (") for ALL strings, never single quotes
5. NO TRAILING COMMAS: The last item in any list or dict must NOT have a trailing comma
6. NO MARKDOWN: Do NOT wrap the output in ```json``` or any code blocks inside the tags
</critical_constraints>

<forbidden_actions>
- DO NOT modify, rename, or remove any seed modules
- DO NOT include explanatory text inside the <GROUPED_COMPONENTS> tags
- DO NOT use single quotes for strings
- DO NOT add comments (// or #) inside the JSON structure
- DO NOT use trailing commas
- DO NOT omit the required XML wrapper tags
</forbidden_actions>

<conditional_logic>
- IF a component is already in a seed module → keep it in that seed module
- IF a new component clearly belongs to a seed module's domain → you MAY add it to that seed module
- IF new components form their own logical group → create a new module for them
- IF unsure whether to add to seed or create new → prefer creating new modules
</conditional_logic>
</decision_policy>

<task_instructions>
<step_by_step>
1. COPY: Include all seed modules in your output exactly as provided
2. IDENTIFY: Find components not assigned to any seed module
3. ANALYZE: Examine unassigned components for patterns and groupings
4. CREATE: Make new modules for logically related unassigned components
5. OPTIONALLY EXTEND: Add clearly related new components to existing seed modules
6. OUTPUT: Write your final answer wrapped in the required XML tags
</step_by_step>
</task_instructions>

<practical_examples>
<positive_example>
<description>This correctly preserves seeds and adds new modules:</description>
<content>
<GROUPED_COMPONENTS>
{{
    "existing_auth_module": {{
        "path": "app/Auth",
        "components": ["Auth.Login", "Auth.Register", "Auth.NewComponent"]
    }},
    "new_payments_module": {{
        "path": "app/Payments",
        "components": ["Payments.Processor", "Payments.Gateway"]
    }}
}}
</GROUPED_COMPONENTS>
</content>
</positive_example>

<negative_example>
<description>This incorrectly renames a seed module:</description>
<content>
<GROUPED_COMPONENTS>
{{
    "authentication": {{
        "path": "app/Auth",
        "components": ["Auth.Login", "Auth.Register"]
    }}
}}
</GROUPED_COMPONENTS>
</content>
<error_justification>
The seed module was named "existing_auth_module" but was renamed to "authentication". Seed modules MUST be preserved exactly as provided.
</error_justification>
</negative_example>
</practical_examples>

<output_format>
Brief analysis (2-3 sentences max) BEFORE tags, then:

<GROUPED_COMPONENTS>
{{
    "preserved_seed_module": {{
        "path": "original/path",
        "components": ["Original.Components", "Plus.New.Ones"]
    }},
    "new_module_name": {{
        "path": "path/to/new",
        "components": ["New.Component.One", "New.Component.Two"]
    }}
}}
</GROUPED_COMPONENTS>
</output_format>

<final_reinforcement>
<reminder>
MANDATORY: Preserve ALL seed modules exactly. Output valid JSON in <GROUPED_COMPONENTS></GROUPED_COMPONENTS> tags.

CHECKLIST:
✓ All seed modules copied exactly (names unchanged)
✓ Tags present: <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS>
✓ Double quotes, no trailing commas, no comments
</reminder>
</final_reinforcement>
""".strip()


CLUSTER_MODULE_PROMPT_V2 = """
<persona>
You are an Expert Code Architecture Analyst specializing in organizing large codebases into coherent, logical module structures. You excel at breaking down large modules into smaller, focused sub-modules.
</persona>

<main_objective>
Your SOLE TASK is to SUBDIVIDE a specific module into smaller, more focused sub-modules. You are given the current module tree for context and the components within one module that needs subdivision. Output must be a structured JSON dictionary wrapped in specific XML tags.
</main_objective>

<key_information>
- You are subdividing ONE specific module: "{module_name}"
- The module tree shows the broader context
- All components listed belong to the module being subdivided
- Create sub-modules that are more focused and cohesive
- The output MUST be machine-parseable
</key_information>

<input_data>
<current_module_tree>
{module_tree}
</current_module_tree>

<module_to_subdivide>{module_name}</module_to_subdivide>

<components_to_organize>
{potential_core_components}
</components_to_organize>
</input_data>

<decision_policy>
<title>Behavior Constraints and Rules</title>

<critical_constraints>
1. OUTPUT FORMAT IS NON-NEGOTIABLE: Your final answer MUST be wrapped in <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS> tags
2. INSIDE THE TAGS: Only valid JSON/Python dictionary syntax - NO comments, NO prose, NO explanations
3. STRING FORMAT: Use double quotes (") for ALL strings, never single quotes
4. NO TRAILING COMMAS: The last item in any list or dict must NOT have a trailing comma
5. SUB-MODULE NAMING: Use descriptive names that reflect the parent module context
6. MINIMUM SPLIT: Create at least 2 sub-modules if splitting is warranted
</critical_constraints>

<forbidden_actions>
- DO NOT include explanatory text inside the <GROUPED_COMPONENTS> tags
- DO NOT use single quotes for strings
- DO NOT add comments (// or #) inside the JSON structure
- DO NOT use trailing commas
- DO NOT omit the required XML wrapper tags
- DO NOT create sub-modules with zero components
- DO NOT put all components in a single sub-module (that defeats the purpose)
</forbidden_actions>

<conditional_logic>
- IF components can be grouped by specific functionality → create sub-modules by function
- IF components follow a layer pattern (service/repository/model) → consider layer-based sub-modules
- IF the module has fewer than 5 components → create 2 sub-modules
- IF the module has 5-20 components → create 2-5 sub-modules
- IF the module has 20+ components → create 4-10 sub-modules
- IF components cannot be meaningfully subdivided → return an empty dict {{}}
</conditional_logic>
</decision_policy>

<task_instructions>
<step_by_step>
1. ANALYZE: Review all components in the module to be subdivided
2. IDENTIFY PATTERNS: Look for functional groupings, layers, or domain sub-areas
3. CREATE SUB-MODULES: Group related components into focused sub-modules
4. NAME APPROPRIATELY: Use clear, descriptive names for sub-modules
5. VERIFY: Ensure each sub-module has clear purpose and at least one component
6. OUTPUT: Write your final answer wrapped in the required XML tags
</step_by_step>
</task_instructions>

<practical_examples>
<positive_example>
<description>Good subdivision of a "user_management" module:</description>
<content>
<GROUPED_COMPONENTS>
{{
    "user_authentication": {{
        "path": "app/Users/Auth",
        "components": ["Users.Auth.LoginService", "Users.Auth.TokenManager"]
    }},
    "user_profile": {{
        "path": "app/Users/Profile",
        "components": ["Users.Profile.ProfileService", "Users.Profile.AvatarHandler"]
    }},
    "user_permissions": {{
        "path": "app/Users/Permissions",
        "components": ["Users.Permissions.RoleManager", "Users.Permissions.AccessControl"]
    }}
}}
</GROUPED_COMPONENTS>
</content>
</positive_example>

<negative_example>
<description>Bad subdivision - all in one sub-module:</description>
<content>
<GROUPED_COMPONENTS>
{{
    "user_stuff": {{
        "path": "app/Users",
        "components": ["Users.Auth.LoginService", "Users.Auth.TokenManager", "Users.Profile.ProfileService", "Users.Profile.AvatarHandler", "Users.Permissions.RoleManager", "Users.Permissions.AccessControl"]
    }}
}}
</GROUPED_COMPONENTS>
</content>
<error_justification>
Only created ONE sub-module containing all components. This defeats the purpose of subdivision. Should create multiple focused sub-modules.
</error_justification>
</negative_example>
</practical_examples>

<output_format>
Brief analysis (2-3 sentences max) BEFORE tags, then:

<GROUPED_COMPONENTS>
{{
    "submodule_one": {{
        "path": "path/to/submodule1",
        "components": ["Component.A", "Component.B"]
    }},
    "submodule_two": {{
        "path": "path/to/submodule2",
        "components": ["Component.C", "Component.D"]
    }}
}}
</GROUPED_COMPONENTS>
</output_format>

<final_reinforcement>
<reminder>
Your goal is to SUBDIVIDE module "{module_name}" into MULTIPLE smaller sub-modules. Output valid JSON in <GROUPED_COMPONENTS></GROUPED_COMPONENTS> tags.

CHECKLIST:
✓ Created 2+ sub-modules (not just one)
✓ Tags present: <GROUPED_COMPONENTS> and </GROUPED_COMPONENTS>
✓ Double quotes, no trailing commas, no comments
✓ Each sub-module has at least one component
</reminder>
</final_reinforcement>
""".strip()


def format_cluster_prompt_v2(
    potential_core_components: str,
    module_tree: dict = None,
    module_name: str = None,
    seed_modules: dict = None
) -> str:
    """
    Format the advanced cluster prompt with potential core components.

    Args:
        potential_core_components: Formatted string of components to cluster
        module_tree: Current module tree for hierarchical clustering (optional)
        module_name: Name of current module being subdivided (optional)
        seed_modules: Existing modules to preserve and extend (optional)

    Returns:
        Formatted prompt string using the V2 advanced templates
    """
    import json

    # Case 1: Extending with seed modules at top level
    if seed_modules is not None and (module_tree is None or module_tree == {}):
        return CLUSTER_REPO_WITH_SEED_PROMPT_V2.format(
            potential_core_components=potential_core_components,
            seed_modules=json.dumps(seed_modules, indent=2)
        )

    # Case 2: Subdividing an existing module
    if module_tree is not None and module_tree != {} and module_name is not None:
        # Format module tree for display
        lines = []
        def _format_tree(tree: dict, indent: int = 0):
            for key, value in tree.items():
                marker = " (current module)" if key == module_name else ""
                lines.append(f"{'  ' * indent}{key}{marker}")
                components = value.get('components', [])
                if components:
                    lines.append(f"{'  ' * (indent + 1)}Components: {', '.join(components[:5])}{'...' if len(components) > 5 else ''}")
                children = value.get('children', {})
                if children:
                    _format_tree(children, indent + 1)

        _format_tree(module_tree)
        formatted_tree = "\n".join(lines)

        return CLUSTER_MODULE_PROMPT_V2.format(
            potential_core_components=potential_core_components,
            module_tree=formatted_tree,
            module_name=module_name
        )

    # Case 3: Initial clustering from scratch
    return CLUSTER_REPO_PROMPT_V2.format(
        potential_core_components=potential_core_components
    )
