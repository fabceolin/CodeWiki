from pydantic_ai import RunContext, Tool, Agent
from typing import Union, Any

from codewiki.src.be.agent_tools.deps import CodeWikiDeps
from codewiki.src.be.agent_tools.read_code_components import read_code_components_tool
from codewiki.src.be.agent_tools.str_replace_editor import str_replace_editor_tool
from codewiki.src.be.llm_services import create_fallback_models
from codewiki.src.be.prompt_template import SYSTEM_PROMPT, LEAF_SYSTEM_PROMPT, format_user_prompt
from codewiki.src.be.utils import is_complex_module, count_tokens
from codewiki.src.be.cluster_modules import format_potential_core_components

import logging
logger = logging.getLogger(__name__)


def normalize_sub_module_specs(specs: Union[dict[str, list[str]], list[dict]]) -> dict[str, list[str]]:
    """Normalize sub_module_specs to dict format.

    Handles both formats:
    - Dict format (Claude): {"module_name": ["comp1", "comp2"], ...}
    - List format (GPT/Azure OpenAI): [{"name": "module_name", "components": ["comp1", "comp2"]}, ...]

    Also handles variations in key names that GPT models might use.
    """
    if isinstance(specs, dict):
        return specs

    if isinstance(specs, list):
        result = {}
        for item in specs:
            if isinstance(item, dict):
                # Try different key names that GPT models might use
                name = item.get('name') or item.get('module_name') or item.get('sub_module_name') or item.get('submodule_name')
                components = item.get('components') or item.get('core_components') or item.get('core_component_ids') or item.get('files') or []

                if name:
                    result[name] = components if isinstance(components, list) else [components]
        return result

    # Fallback: return empty dict
    logger.warning(f"Unexpected sub_module_specs format: {type(specs)}")
    return {}



async def generate_sub_module_documentation(
    ctx: RunContext[CodeWikiDeps],
    sub_module_specs: dict[str, list[str]] | list[dict[str, Any]]
) -> str:
    """Generate detailed description of a given sub-module specs to the sub-agents

    Args:
        sub_module_specs: The specs of the sub-modules to generate documentation for.
            Accepts two formats:
            - Dict format: {"sub_module_1": ["core_component_1.1", "core_component_1.2"], "sub_module_2": ["core_component_2.1", "core_component_2.2"], ...}
            - List format: [{"name": "sub_module_1", "components": ["core_component_1.1", "core_component_1.2"]}, ...]
    """
    # Normalize the input to dict format (handles both Claude and GPT model outputs)
    sub_module_specs = normalize_sub_module_specs(sub_module_specs)

    if not sub_module_specs:
        logger.warning("No valid sub-module specs provided after normalization")
        return "No valid sub-module specs provided."

    deps = ctx.deps
    previous_module_name = deps.current_module_name
    
    # Create fallback models from config
    fallback_models = create_fallback_models(deps.config)

    # add the sub-module to the module tree
    value = deps.module_tree
    for key in deps.path_to_current_module:
        value = value[key]["children"]
    for sub_module_name, core_component_ids in sub_module_specs.items():
        value[sub_module_name] = {"components": core_component_ids, "children": {}}
    
    for sub_module_name, core_component_ids in sub_module_specs.items():

        # Create visual indentation for nested modules
        indent = "  " * deps.current_depth
        arrow = "└─" if deps.current_depth > 0 else "→"

        logger.info(f"{indent}{arrow} Generating documentation for sub-module: {sub_module_name}")

        num_tokens = count_tokens(format_potential_core_components(core_component_ids, ctx.deps.components)[-1])
        
        if is_complex_module(ctx.deps.components, core_component_ids) and ctx.deps.current_depth < ctx.deps.max_depth and num_tokens >= ctx.deps.config.max_token_per_leaf_module:
            sub_agent = Agent(
                model=fallback_models,
                name=sub_module_name,
                deps_type=CodeWikiDeps,
                system_prompt=SYSTEM_PROMPT.format(module_name=sub_module_name, custom_instructions=ctx.deps.custom_instructions),
                tools=[read_code_components_tool, str_replace_editor_tool, generate_sub_module_documentation_tool],
            )
        else:
            sub_agent = Agent(
                model=fallback_models,
                name=sub_module_name,
                deps_type=CodeWikiDeps,
                system_prompt=LEAF_SYSTEM_PROMPT.format(module_name=sub_module_name, custom_instructions=ctx.deps.custom_instructions),
                tools=[read_code_components_tool, str_replace_editor_tool],
            )

        deps.current_module_name = sub_module_name
        deps.path_to_current_module.append(sub_module_name)
        deps.current_depth += 1
        # log the current module tree
        # print(f"Current module tree: {json.dumps(deps.module_tree, indent=4)}")

        result = await sub_agent.run(
            format_user_prompt(
                module_name=deps.current_module_name,
                core_component_ids=core_component_ids,
                components=ctx.deps.components,
                module_tree=ctx.deps.module_tree,
            ),
            deps=ctx.deps
        )

        # remove the sub-module name from the path to current module and the module tree
        deps.path_to_current_module.pop()
        deps.current_depth -= 1

    # restore the previous module name
    deps.current_module_name = previous_module_name

    return f"Generate successfully. Documentations: {', '.join([key + '.md' for key in sub_module_specs.keys()])} are saved in the working directory."


generate_sub_module_documentation_tool = Tool(function=generate_sub_module_documentation, name="generate_sub_module_documentation", description="Generate detailed description of a given sub-module specs to the sub-agents", takes_ctx=True)