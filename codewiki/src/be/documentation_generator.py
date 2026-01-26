import logging
import os
import json
from typing import Dict, List, Any, Set, Tuple, Optional
from copy import deepcopy
import traceback

# Configure logging and monitoring
logger = logging.getLogger(__name__)


def should_process_module(
    module_key: str,
    selective_modules: Optional[List[str]],
    all_module_keys: Set[str]
) -> Tuple[bool, str]:
    """
    Determine if a module should be processed based on selective filter.

    Args:
        module_key: The module path as a string (e.g., "backend/auth")
        selective_modules: List of module paths to selectively regenerate
        all_module_keys: Set of all module keys in the tree

    Returns:
        (should_process, reason) tuple
    """
    if not selective_modules:
        return True, "no filter"

    for pattern in selective_modules:
        # Exact match
        if module_key == pattern:
            return True, f"exact match: {pattern}"

        # Child of specified module (prefix match)
        # "backend/auth" matches filter "backend" when module is child
        if module_key.startswith(pattern + "/"):
            return True, f"child of: {pattern}"

        # Parent of specified module (for overview coherence)
        # "backend" matches filter "backend/auth" when module is parent
        if pattern.startswith(module_key + "/"):
            return True, f"parent of: {pattern}"

    return False, "not in filter"


def get_required_parents(selective_modules: List[str]) -> Set[str]:
    """
    Get all parent module paths that need regeneration for overview coherence.

    Args:
        selective_modules: List of module paths to selectively regenerate

    Returns:
        Set of parent module paths
    """
    parents = set()
    for module_path in selective_modules:
        parts = module_path.split("/")
        for i in range(1, len(parts)):
            parents.add("/".join(parts[:i]))
    return parents

# Local imports
from codewiki.src.be.dependency_analyzer import DependencyGraphBuilder
from codewiki.src.be.llm_services import call_llm
from codewiki.src.be.prompt_template import (
    REPO_OVERVIEW_PROMPT,
    MODULE_OVERVIEW_PROMPT,
)
from codewiki.src.be.cluster_modules import cluster_modules
from codewiki.src.config import (
    Config,
    FIRST_MODULE_TREE_FILENAME,
    MODULE_TREE_FILENAME,
    OVERVIEW_FILENAME
)
from codewiki.src.utils import file_manager
from codewiki.src.be.agent_orchestrator import AgentOrchestrator


class DocumentationGenerator:
    """Main documentation generation orchestrator."""
    
    def __init__(self, config: Config, commit_id: str = None):
        self.config = config
        self.commit_id = commit_id
        self.graph_builder = DependencyGraphBuilder(config)
        self.agent_orchestrator = AgentOrchestrator(config)
    
    def create_documentation_metadata(self, working_dir: str, components: Dict[str, Any], num_leaf_nodes: int):
        """Create a metadata file with documentation generation information."""
        from datetime import datetime
        
        metadata = {
            "generation_info": {
                "timestamp": datetime.now().isoformat(),
                "main_model": self.config.main_model,
                "generator_version": "1.0.1",
                "repo_path": self.config.repo_path,
                "commit_id": self.commit_id
            },
            "statistics": {
                "total_components": len(components),
                "leaf_nodes": num_leaf_nodes,
                "max_depth": self.config.max_depth
            },
            "files_generated": [
                "overview.md",
                "module_tree.json",
                "first_module_tree.json"
            ]
        }
        
        # Add generated markdown files to the metadata
        try:
            for file_path in os.listdir(working_dir):
                if file_path.endswith('.md') and file_path not in metadata["files_generated"]:
                    metadata["files_generated"].append(file_path)
        except Exception as e:
            logger.warning(f"Could not list generated files: {e}")
        
        metadata_path = os.path.join(working_dir, "metadata.json")
        file_manager.save_json(metadata, metadata_path)

    
    def get_processing_order(self, module_tree: Dict[str, Any], parent_path: List[str] = []) -> List[tuple[List[str], str]]:
        """Get the processing order using topological sort (leaf modules first)."""
        processing_order = []
        
        def collect_modules(tree: Dict[str, Any], path: List[str]):
            for module_name, module_info in tree.items():
                current_path = path + [module_name]
                
                # If this module has children, process them first
                if module_info.get("children") and isinstance(module_info["children"], dict) and module_info["children"]:
                    collect_modules(module_info["children"], current_path)
                    # Add this parent module after its children
                    processing_order.append((current_path, module_name))
                else:
                    # This is a leaf module, add it immediately
                    processing_order.append((current_path, module_name))
        
        collect_modules(module_tree, parent_path)
        return processing_order

    def is_leaf_module(self, module_info: Dict[str, Any]) -> bool:
        """Check if a module is a leaf module (has no children or empty children)."""
        children = module_info.get("children", {})
        return not children or (isinstance(children, dict) and len(children) == 0)

    def build_overview_structure(self, module_tree: Dict[str, Any], module_path: List[str],
                                 working_dir: str) -> Dict[str, Any]:
        """Build structure for overview generation with 1-depth children docs and target indicator."""
        
        processed_module_tree = deepcopy(module_tree)
        module_info = processed_module_tree
        for path_part in module_path:
            module_info = module_info[path_part]
            if path_part != module_path[-1]:
                module_info = module_info.get("children", {})
            else:
                module_info["is_target_for_overview_generation"] = True

        if "children" in module_info:
            module_info = module_info["children"]

        for child_name, child_info in module_info.items():
            if os.path.exists(os.path.join(working_dir, f"{child_name}.md")):
                child_info["docs"] = file_manager.load_text(os.path.join(working_dir, f"{child_name}.md"))
            else:
                logger.warning(f"Module docs not found at {os.path.join(working_dir, f"{child_name}.md")}")
                child_info["docs"] = ""

        return processed_module_tree

    async def generate_module_documentation(self, components: Dict[str, Any], leaf_nodes: List[str]) -> str:
        """Generate documentation for all modules using dynamic programming approach."""
        # Prepare output directory
        working_dir = os.path.abspath(self.config.docs_dir)
        file_manager.ensure_directory(working_dir)

        module_tree_path = os.path.join(working_dir, MODULE_TREE_FILENAME)
        first_module_tree_path = os.path.join(working_dir, FIRST_MODULE_TREE_FILENAME)
        module_tree = file_manager.load_json(module_tree_path)
        first_module_tree = file_manager.load_json(first_module_tree_path)

        # Get processing order (leaf modules first)
        processing_order = self.get_processing_order(first_module_tree)

        # Get selective modules and force flag from config
        selective_modules = self.config.selective_modules
        force_regenerate = self.config.force_regenerate

        # Build set of all module keys for filtering
        all_module_keys = {"/".join(path) for path, _ in processing_order}

        # Calculate and log summary for selective regeneration
        modules_to_process_count = 0
        modules_skipped_count = 0
        if selective_modules:
            required_parents = get_required_parents(selective_modules)
            for module_path, _ in processing_order:
                module_key = "/".join(module_path)
                should_process, _ = should_process_module(module_key, selective_modules, all_module_keys)
                if should_process:
                    modules_to_process_count += 1
                else:
                    modules_skipped_count += 1
            logger.info(f"📊 Selective regeneration: {modules_to_process_count} of {len(all_module_keys)} total modules")
        else:
            modules_to_process_count = len(all_module_keys)
            logger.info(f"📊 Full generation: {len(all_module_keys)} modules")

        # Process modules in dependency order
        final_module_tree = module_tree
        processed_modules = set()

        if len(module_tree) > 0:
            for module_path, module_name in processing_order:
                try:
                    # Get the module info from the tree
                    module_info = module_tree
                    for path_part in module_path:
                        module_info = module_info[path_part]
                        if path_part != module_path[-1]:  # Not the last part
                            module_info = module_info.get("children", {})

                    # Skip if already processed
                    module_key = "/".join(module_path)
                    if module_key in processed_modules:
                        continue

                    # Apply selective filter
                    if selective_modules:
                        should_process, reason = should_process_module(
                            module_key, selective_modules, all_module_keys
                        )
                        if not should_process:
                            logger.debug(f"⏭️  Skipping {module_key}: {reason}")
                            continue
                        else:
                            logger.debug(f"✓ Including {module_key}: {reason}")

                    # Process the module
                    if self.is_leaf_module(module_info):
                        logger.info(f"📄 Processing leaf module: {module_key}")
                        if self.config.use_claude_code:
                            # Use Claude Code CLI for documentation generation
                            final_module_tree = await self._process_module_with_claude_code(
                                module_name, components, module_info["components"],
                                module_tree, working_dir, force_regenerate
                            )
                        else:
                            final_module_tree = await self.agent_orchestrator.process_module(
                                module_name, components, module_info["components"], module_path, working_dir
                            )
                    else:
                        logger.info(f"📁 Processing parent module: {module_key}")
                        final_module_tree = await self.generate_parent_module_docs(
                            module_path, working_dir, force_regenerate
                        )

                    processed_modules.add(module_key)

                except Exception as e:
                    logger.error(f"Failed to process module {module_key}: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue

            # Generate repo overview
            # Only regenerate if not using selective modules, or if any module was processed
            should_regen_overview = not selective_modules or modules_to_process_count > 0
            if should_regen_overview:
                logger.info(f"📚 Generating repository overview")
                final_module_tree = await self.generate_parent_module_docs(
                    [], working_dir, force_regenerate
                )
        else:
            logger.info(f"Processing whole repo because repo can fit in the context window")
            repo_name = os.path.basename(os.path.normpath(self.config.repo_path))
            if self.config.use_claude_code:
                # Use Claude Code CLI for documentation generation
                final_module_tree = await self._process_module_with_claude_code(
                    repo_name, components, leaf_nodes, module_tree, working_dir, force_regenerate
                )
            else:
                final_module_tree = await self.agent_orchestrator.process_module(
                    repo_name, components, leaf_nodes, [], working_dir
                )

            # save final_module_tree to module_tree.json
            file_manager.save_json(final_module_tree, os.path.join(working_dir, MODULE_TREE_FILENAME))

            # rename repo_name.md to overview.md
            repo_overview_path = os.path.join(working_dir, f"{repo_name}.md")
            if os.path.exists(repo_overview_path):
                os.rename(repo_overview_path, os.path.join(working_dir, OVERVIEW_FILENAME))
        
        return working_dir

    async def generate_parent_module_docs(
        self,
        module_path: List[str],
        working_dir: str,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """Generate documentation for a parent module based on its children's documentation.

        Args:
            module_path: List of path components to the module
            working_dir: Output directory for documentation
            force_regenerate: If True, regenerate even if docs exist

        Returns:
            Updated module tree
        """
        module_name = module_path[-1] if len(module_path) >= 1 else os.path.basename(os.path.normpath(self.config.repo_path))

        logger.info(f"Generating parent documentation for: {module_name}")

        # Load module tree
        module_tree_path = os.path.join(working_dir, MODULE_TREE_FILENAME)
        module_tree = file_manager.load_json(module_tree_path)

        # check if overview docs already exists
        overview_docs_path = os.path.join(working_dir, OVERVIEW_FILENAME)
        if not force_regenerate and os.path.exists(overview_docs_path):
            logger.info(f"✓ Overview docs already exists at {overview_docs_path}")
            return module_tree

        # check if parent docs already exists
        parent_docs_path = os.path.join(working_dir, f"{module_name if len(module_path) >= 1 else OVERVIEW_FILENAME.replace('.md', '')}.md")
        if not force_regenerate and os.path.exists(parent_docs_path):
            logger.info(f"✓ Parent docs already exists at {parent_docs_path}")
            return module_tree

        # Create repo structure with 1-depth children docs and target indicator
        repo_structure = self.build_overview_structure(module_tree, module_path, working_dir)

        prompt = MODULE_OVERVIEW_PROMPT.format(
            module_name=module_name,
            repo_structure=json.dumps(repo_structure, indent=4)
        ) if len(module_path) >= 1 else REPO_OVERVIEW_PROMPT.format(
            repo_name=module_name,
            repo_structure=json.dumps(repo_structure, indent=4)
        )
        
        try:
            # Use Claude Code CLI if configured, otherwise use direct LLM call
            if self.config.use_claude_code:
                from codewiki.src.be.claude_code_adapter import claude_code_generate_overview
                parent_docs = claude_code_generate_overview(prompt, self.config)
            else:
                parent_docs = call_llm(prompt, self.config)

            # Parse and save parent documentation
            if "<OVERVIEW>" in parent_docs and "</OVERVIEW>" in parent_docs:
                parent_content = parent_docs.split("<OVERVIEW>")[1].split("</OVERVIEW>")[0].strip()
            else:
                # Claude Code might return the content directly without tags
                parent_content = parent_docs.strip()
            file_manager.save_text(parent_content, parent_docs_path)

            logger.debug(f"Successfully generated parent documentation for: {module_name}")
            return module_tree

        except Exception as e:
            logger.error(f"Error generating parent documentation for {module_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def _process_module_with_claude_code(
        self,
        module_name: str,
        components: Dict[str, Any],
        core_component_ids: List[str],
        module_tree: Dict[str, Any],
        working_dir: str,
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        """
        Process a module using Claude Code CLI for documentation generation.

        Args:
            module_name: Name of the module
            components: All code components
            core_component_ids: Component IDs in this module
            module_tree: The full module tree
            working_dir: Output directory for documentation
            force_regenerate: If True, regenerate even if docs exist

        Returns:
            Updated module tree
        """
        from codewiki.src.be.claude_code_adapter import claude_code_generate_docs

        # Check if docs already exist
        docs_path = os.path.join(working_dir, f"{module_name}.md")
        if not force_regenerate and os.path.exists(docs_path):
            logger.info(f"✓ Module docs already exists at {docs_path}")
            return module_tree

        try:
            # Generate documentation using Claude Code CLI
            doc_content = claude_code_generate_docs(
                module_name=module_name,
                core_component_ids=core_component_ids,
                components=components,
                module_tree=module_tree,
                config=self.config,
                output_path=working_dir,
            )

            # Check if Claude Code already created the file (via str_replace_editor)
            # If so, don't overwrite with the response (which may be a confirmation message)
            if os.path.exists(docs_path):
                logger.info(f"✓ Generated documentation for {module_name} (file created by Claude Code)")
            else:
                # Claude returned documentation in stdout, save it
                file_manager.save_text(doc_content, docs_path)
                logger.info(f"✓ Generated documentation for {module_name}")

            return module_tree

        except Exception as e:
            logger.error(f"Claude Code documentation generation failed for {module_name}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def run(self) -> None:
        """Run the complete documentation generation process using dynamic programming."""
        try:
            # Build dependency graph
            components, leaf_nodes = self.graph_builder.build_dependency_graph()

            logger.debug(f"Found {len(leaf_nodes)} leaf nodes")
            # logger.debug(f"Leaf nodes:\n{'\n'.join(sorted(leaf_nodes)[:200])}")
            # exit()
            
            # Cluster modules
            working_dir = os.path.abspath(self.config.docs_dir)
            file_manager.ensure_directory(working_dir)
            first_module_tree_path = os.path.join(working_dir, FIRST_MODULE_TREE_FILENAME)
            module_tree_path = os.path.join(working_dir, MODULE_TREE_FILENAME)
            
            # Check if module tree exists
            if os.path.exists(first_module_tree_path):
                logger.debug(f"Module tree found at {first_module_tree_path}")
                module_tree = file_manager.load_json(first_module_tree_path)
            else:
                logger.debug(f"Module tree not found at {module_tree_path}, clustering modules")
                module_tree = cluster_modules(leaf_nodes, components, self.config)
                file_manager.save_json(module_tree, first_module_tree_path)
            
            file_manager.save_json(module_tree, module_tree_path)
            
            logger.debug(f"Grouped components into {len(module_tree)} modules")
            
            # Generate module documentation using dynamic programming approach
            # This processes leaf modules first, then parent modules
            working_dir = await self.generate_module_documentation(components, leaf_nodes)
            
            # Create documentation metadata
            self.create_documentation_metadata(working_dir, components, len(leaf_nodes))
            
            logger.debug(f"Documentation generation completed successfully using dynamic programming!")
            logger.debug(f"Processing order: leaf modules → parent modules → repository overview")
            logger.debug(f"Documentation saved to: {working_dir}")
            
        except Exception as e:
            logger.error(f"Documentation generation failed: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise