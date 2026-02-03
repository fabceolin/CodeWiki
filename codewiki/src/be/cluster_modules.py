from typing import List, Dict, Any
from collections import defaultdict
import logging
import traceback
logger = logging.getLogger(__name__)

from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.llm_services import call_llm
from codewiki.src.be.utils import count_tokens
from codewiki.src.config import Config
from codewiki.src.be.prompt_template import format_cluster_prompt


def format_potential_core_components(leaf_nodes: List[str], components: Dict[str, Node]) -> tuple[str, str]:
    """
    Format the potential core components into a string that can be used in the prompt.
    """
    # Filter out any invalid leaf nodes that don't exist in components
    valid_leaf_nodes = []
    for leaf_node in leaf_nodes:
        if leaf_node in components:
            valid_leaf_nodes.append(leaf_node)
        else:
            logger.warning(f"Skipping invalid leaf node '{leaf_node}' - not found in components")
    
    #group leaf nodes by file
    leaf_nodes_by_file = defaultdict(list)
    for leaf_node in valid_leaf_nodes:
        leaf_nodes_by_file[components[leaf_node].relative_path].append(leaf_node)

    potential_core_components = ""
    potential_core_components_with_code = ""
    for file, leaf_nodes in dict(sorted(leaf_nodes_by_file.items())).items():
        potential_core_components += f"# {file}\n"
        potential_core_components_with_code += f"# {file}\n"
        for leaf_node in leaf_nodes:
            potential_core_components += f"\t{leaf_node}\n"
            potential_core_components_with_code += f"\t{leaf_node}\n"
            potential_core_components_with_code += f"{components[leaf_node].source_code}\n"

    return potential_core_components, potential_core_components_with_code


def cluster_modules(
    leaf_nodes: List[str],
    components: Dict[str, Node],
    config: Config,
    current_module_tree: dict[str, Any] = {},
    current_module_name: str = None,
    current_module_path: List[str] = [],
    seed_modules: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Cluster the potential core components into modules.

    Args:
        leaf_nodes: List of component IDs to cluster
        components: Dictionary mapping component IDs to Node objects
        config: Configuration object
        current_module_tree: Current module tree for hierarchical clustering
        current_module_name: Name of current module being subdivided
        current_module_path: Path to current module in tree
        seed_modules: Existing module tree to preserve and extend (optional)
    """
    # If seed modules provided at top level, start with them and cluster remaining
    if seed_modules is not None and current_module_tree == {}:
        logger.info(f"Starting seeded clustering with {len(seed_modules)} existing modules")
        # Get components already assigned to seed modules
        assigned_components = set()
        for module_info in seed_modules.values():
            assigned_components.update(module_info.get("components", []))

        # Find unassigned leaf nodes
        unassigned_leaf_nodes = [ln for ln in leaf_nodes if ln not in assigned_components]
        logger.info(f"Found {len(unassigned_leaf_nodes)} unassigned components out of {len(leaf_nodes)} total")

        # Start with seed modules as base
        result = {}
        for module_name, module_info in seed_modules.items():
            result[module_name] = {
                "path": module_info.get("path", ""),
                "components": module_info.get("components", []),
                "children": module_info.get("children", {})
            }

        # Cluster unassigned components if any
        if unassigned_leaf_nodes:
            new_modules = cluster_modules(
                unassigned_leaf_nodes,
                components,
                config,
                current_module_tree={},
                current_module_name=None,
                current_module_path=[],
                seed_modules=None  # Don't pass seed again to avoid recursion
            )
            # Merge new modules into result
            for module_name, module_info in new_modules.items():
                if module_name not in result:
                    result[module_name] = module_info
                else:
                    # Append to existing module if name collision
                    result[module_name]["components"].extend(module_info.get("components", []))

        return result

    potential_core_components, potential_core_components_with_code = format_potential_core_components(leaf_nodes, components)

    if count_tokens(potential_core_components_with_code) <= config.max_token_per_module:
        logger.debug(f"Skipping clustering for {current_module_name} because the potential core components are too few: {count_tokens(potential_core_components_with_code)} tokens")
        return {}

    prompt = format_cluster_prompt(potential_core_components, current_module_tree, current_module_name)
    response = call_llm(prompt, config, model=config.cluster_model)

    #parse the response
    try:
        if "<GROUPED_COMPONENTS>" not in response or "</GROUPED_COMPONENTS>" not in response:
            logger.error(f"Invalid LLM response format - missing component tags: {response[:200]}...")
            return {}
        
        response_content = response.split("<GROUPED_COMPONENTS>")[1].split("</GROUPED_COMPONENTS>")[0]
        module_tree = eval(response_content)
        
        if not isinstance(module_tree, dict):
            logger.error(f"Invalid module tree format - expected dict, got {type(module_tree)}")
            return {}
            
    except Exception as e:
        logger.error(f"Failed to parse LLM response: {e}. Response: {response[:200]}...")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {}

    # check if the module tree is valid
    if len(module_tree) <= 1:
        logger.debug(f"Skipping clustering for {current_module_name} because the module tree is too small: {len(module_tree)} modules")
        return {}

    if current_module_tree == {}:
        current_module_tree = module_tree
    else:
        value = current_module_tree
        for key in current_module_path:
            value = value[key]["children"]
        for module_name, module_info in module_tree.items():
            del module_info["path"]
            value[module_name] = module_info

    for module_name, module_info in module_tree.items():
        sub_leaf_nodes = module_info.get("components", [])
        
        # Filter sub_leaf_nodes to ensure they exist in components
        valid_sub_leaf_nodes = []
        for node in sub_leaf_nodes:
            if node in components:
                valid_sub_leaf_nodes.append(node)
            else:
                logger.warning(f"Skipping invalid sub leaf node '{node}' in module '{module_name}' - not found in components")
        
        current_module_path.append(module_name)
        module_info["children"] = {}
        module_info["children"] = cluster_modules(valid_sub_leaf_nodes, components, config, current_module_tree, module_name, current_module_path)
        current_module_path.pop()

    return module_tree