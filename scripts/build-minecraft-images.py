#!/usr/bin/env python3
"""
Script to build Minecraft Docker images for game projects.
Supports building multiple projects in parallel and creating docker-compose configuration.

Usage: python3 build-minecraft-images.py
The script will prompt you to enter project paths interactively.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Error: requests is required. Install with: pip install requests")
    sys.exit(1)

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def print_error(msg: str):
    try:
        print(f"{Colors.RED}Error: {msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(f"Error: {msg}")

def print_success(msg: str):
    try:
        print(f"{Colors.GREEN}[OK] {msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(f"[OK] {msg}")

def print_info(msg: str):
    try:
        print(f"{Colors.BLUE}[INFO] {msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(f"[INFO] {msg}")

def print_warning(msg: str):
    try:
        print(f"{Colors.YELLOW}[WARN] {msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(f"[WARN] {msg}")

def download_file(url: str, dest: Path) -> bool:
    """Download a file from URL to destination."""
    try:
        response = requests.get(url, stream=True, timeout=30, allow_redirects=True)
        response.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # Verify the file was actually written and has content
        if not dest.exists() or dest.stat().st_size == 0:
            return False
        return True
    except Exception as e:
        print_warning(f"Failed to download {url}: {e}")
        return False

def get_latest_local_engine_release() -> Optional[str]:
    """Get the latest local-engine release JAR URL."""
    try:
        response = requests.get(
            "https://api.github.com/repos/Plexverse/local-engine/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        # Find JAR asset
        for asset in data.get('assets', []):
            if asset['name'].endswith('.jar') and 'sources' not in asset['name'] and 'javadoc' not in asset['name']:
                return asset['browser_download_url']
        
        return None
    except Exception as e:
        print_error(f"Failed to get latest release: {e}")
        return None

def download_plugin(lib_name: str, plugins_dir: Path) -> bool:
    """Download a plugin by library name using Modrinth, Spiget API, or direct URLs."""
    # Modrinth project IDs, Spiget API resource IDs, and direct download URLs
    plugin_configs = {
        'PROTOCOLLIB': {
            'modrinth_id': 'protocolib',  # ProtocolLib on Modrinth
            'spiget_id': '86311',  # ProtocolLib resource ID on SpigotMC
            'fallback': 'https://github.com/dmulloy2/ProtocolLib/releases/latest/download/ProtocolLib.jar'
        },
        'LIBSDISGUISES': {
            'spiget_id': '32453',  # LibsDisguises resource ID
            'fallback': 'https://github.com/libraryaddict/LibsDisguises/releases/latest/download/LibsDisguises.jar'
        },
        'DECENTHOLOGRAMS': {
            'spiget_id': '96927',  # DecentHolograms resource ID
            'fallback': 'https://github.com/Andre601/DecentHolograms/releases/latest/download/DecentHolograms.jar'
        },
    }
    
    if lib_name not in plugin_configs:
        print_warning(f"Unknown library: {lib_name}")
        return False
    
    config = plugin_configs[lib_name]
    dest = plugins_dir / f"{lib_name}.jar"
    print_info(f"  Downloading {lib_name}...")
    
    # Try Modrinth API first (for ProtocolLib)
    if lib_name == 'PROTOCOLLIB' and config.get('modrinth_id'):
        try:
            # Get latest version from Modrinth
            modrinth_api = f"https://api.modrinth.com/v2/project/{config['modrinth_id']}/version"
            response = requests.get(modrinth_api, timeout=10)
            if response.status_code == 200:
                versions = response.json()
                if versions:
                    # Find the latest version for Minecraft 1.21
                    for version in versions:
                        game_versions = version.get('game_versions', [])
                        if '1.21' in game_versions or '1.21.1' in game_versions:
                            files = version.get('files', [])
                            if files:
                                download_url = files[0].get('url')
                                if download_url and download_file(download_url, dest):
                                    if dest.stat().st_size > 100000:  # > 100KB
                                        print_success(f"  Downloaded {lib_name} from Modrinth")
                                        return True
                                    else:
                                        dest.unlink()
        except Exception as e:
            print_warning(f"  Modrinth download failed: {e}")
    
    # Try Spiget API
    if config.get('spiget_id'):
        try:
            spiget_url = f"https://api.spiget.org/v2/resources/{config['spiget_id']}/download"
            if download_file(spiget_url, dest):
                # Verify file size
                if dest.stat().st_size > 100000:  # > 100KB
                    print_success(f"  Downloaded {lib_name} from Spiget")
                    return True
                else:
                    dest.unlink()
                    print_warning(f"  Downloaded file too small, may be invalid")
        except Exception as e:
            print_warning(f"  Spiget download failed: {e}")
    
    # Fallback to GitHub releases or direct URL
    if config.get('fallback'):
        if download_file(config['fallback'], dest):
            # Verify file size
            if dest.stat().st_size > 100000:  # > 100KB
                print_success(f"  Downloaded {lib_name} from fallback URL")
                return True
            else:
                dest.unlink()
                print_warning(f"  Downloaded file too small, may be invalid")
    
    print_warning(f"  Failed to download {lib_name}")
    return False

def parse_game_properties(project_dir: Path) -> Dict:
    """Parse game-properties.yaml and extract all relevant information."""
    game_properties = project_dir / "config" / "game-properties.yaml"
    
    if not game_properties.exists():
        return {}
    
    try:
        with open(game_properties, 'r') as f:
            data = yaml.safe_load(f)
        
        result = {
            'project_id': data.get('projectId', ''),
            'namespace_id': data.get('namespaceId', ''),
            'libraries': []
        }
        
        # Extract game information
        game_info = data.get('game', {})
        if game_info:
            result['game_name'] = game_info.get('name', '')
            result['display_name'] = game_info.get('displayName', '')
            result['visibility'] = game_info.get('visibility', '')
            result['category'] = game_info.get('category', '')
            result['tags'] = game_info.get('tags', [])
        
        # Extract dependencies
        libraries = data.get('dependencies', {}).get('libraries', [])
        result['libraries'] = libraries if isinstance(libraries, list) else []
        
        # Extract secret environment variable keys
        secret_env_keys = data.get('secretEnvironmentVariableKeys', [])
        result['secret_env_keys'] = secret_env_keys if isinstance(secret_env_keys, list) else []
        
        return result
    except Exception as e:
        print_warning(f"Failed to parse game-properties.yaml: {e}")
        return {}

def build_project_jar(project_dir: Path) -> Optional[Path]:
    """Build the project JAR using buildPluginJar task."""
    # Check for gradlew (Unix) or gradlew.bat (Windows)
    if os.name == 'nt':  # Windows
        gradlew = project_dir / "gradlew.bat"
        if not gradlew.exists():
            gradlew = project_dir / "gradlew"
    else:  # Unix-like
        gradlew = project_dir / "gradlew"
        if not gradlew.exists():
            gradlew = project_dir / "gradlew.bat"
    
    if not gradlew.exists():
        print_error(f"gradlew not found in {project_dir}")
        return None
    
    print_info(f"Building project JAR in {project_dir.name}...")
    
    try:
        # Run buildPluginJar task
        # On Windows, use shell=True for .bat files
        use_shell = os.name == 'nt' and gradlew.suffix == '.bat'
        result = subprocess.run(
            [str(gradlew), "buildPluginJar"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=300,
            shell=use_shell
        )
        
        if result.returncode != 0:
            print_error(f"Build failed: {result.stderr}")
            return None
        
        # Find the built JAR
        libs_dir = project_dir / "build" / "libs"
        mineplex_dir = project_dir / "mineplex"
        
        built_jar = None
        if libs_dir.exists():
            jars = list(libs_dir.glob("*-all.jar")) or list(libs_dir.glob("*.jar"))
            jars = [j for j in jars if 'sources' not in j.name and 'javadoc' not in j.name]
            if jars:
                built_jar = jars[0]
        
        if not built_jar and mineplex_dir.exists():
            jars = list(mineplex_dir.glob("*.jar"))
            if jars:
                built_jar = jars[0]
        
        if built_jar and built_jar.exists():
            print_success(f"Built JAR: {built_jar.name}")
            return built_jar
        
        print_error("Could not find built JAR file")
        return None
        
    except subprocess.TimeoutExpired:
        print_error("Build timed out")
        return None
    except Exception as e:
        print_error(f"Build failed: {e}")
        return None

def build_project_image(project_path: str, port: int = 25565) -> Optional[Dict]:
    """Build a Docker image for a single project."""
    project_dir = Path(project_path).resolve()
    directory_name = project_dir.name
    
    print_info(f"Processing project: {directory_name} (port {port})")
    
    if not project_dir.exists():
        print_error(f"Project directory does not exist: {project_dir}")
        return None
    
    game_properties = project_dir / "config" / "game-properties.yaml"
    if not game_properties.exists():
        print_error(f"game-properties.yaml not found at {game_properties}")
        return None
    
    # Parse game properties to get project ID and other metadata
    game_data = parse_game_properties(project_dir)
    project_id = game_data.get('project_id', '')
    
    if not project_id:
        print_error("projectId not found in game-properties.yaml")
        return None
    
    # Use project ID as the identifier, fallback to directory name
    project_name = project_id
    game_name = game_data.get('game_name', directory_name)
    
    # Calculate container name (same logic as in create_docker_compose)
    sanitized_game_name = ''.join(c for c in game_name if c.isalnum() or c in ('-', '_'))
    container_name = f"{sanitized_game_name}-1"
    
    print_info(f"Project ID: {project_id}, Game: {game_name}")
    
    # Create temporary build directory
    build_dir = Path(tempfile.mkdtemp(prefix=f"minecraft-build-{project_id}-"))
    
    try:
        plugins_dir = build_dir / "plugins"
        plugins_dir.mkdir(parents=True)
        
        # 1. Get local-engine JAR (local path or download)
        local_engine_jar = plugins_dir / "local-engine.jar"
        
        # Check if we should use a local JAR (shared across all projects)
        # This is handled at the main() level, but we check here too for per-project override
        use_local_jar = getattr(build_project_image, '_use_local_jar', None)
        local_jar_path = getattr(build_project_image, '_local_jar_path', None)
        
        if use_local_jar and local_jar_path:
            # Resolve path relative to script's parent directory (workspace root)
            script_dir = Path(__file__).parent.parent
            local_jar = (script_dir / local_jar_path).resolve()
            print_info(f"Using local local-engine JAR: {local_jar}")
            if not local_jar.exists():
                print_error(f"Local JAR path does not exist: {local_jar}")
                return None
            if not local_jar.name.lower().endswith('.jar'):
                print_error(f"Local path is not a JAR file: {local_jar}")
                return None
            # Copy with timestamp to ensure Docker sees it as changed
            shutil.copy2(local_jar, local_engine_jar)
            # Touch the file to update its timestamp
            local_engine_jar.touch()
            print_success(f"Copied local-engine.jar from {local_jar} (size: {local_jar.stat().st_size} bytes)")
        else:
            print_info(f"Downloading local-engine for {game_name}...")
            jar_url = get_latest_local_engine_release()
            if not jar_url:
                print_error("Could not get local-engine release URL")
                return None
            
            if not download_file(jar_url, local_engine_jar):
                print_error("Failed to download local-engine")
                return None
            print_success(f"Downloaded local-engine.jar")
        
        # 2. Build project JAR
        built_jar = build_project_jar(project_dir)
        if not built_jar:
            return None
        
        shutil.copy2(built_jar, plugins_dir / built_jar.name)
        print_success(f"Copied project JAR: {built_jar.name}")
        
        # 3. Download dependencies
        libraries = game_data.get('libraries', [])
        if libraries:
            print_info(f"Downloading {len(libraries)} dependencies...")
            for lib in libraries:
                download_plugin(lib, plugins_dir)
        
        # 4. Copy external-plugins to plugins directory
        external_plugins_dir = project_dir / "external-plugins"
        if external_plugins_dir.exists() and external_plugins_dir.is_dir():
            for plugin_file in external_plugins_dir.glob("*.jar"):
                shutil.copy2(plugin_file, plugins_dir / plugin_file.name)
                print_success(f"Copied external plugin: {plugin_file.name}")
        
        # 5. Copy assets and configs
        if (project_dir / "assets").exists():
            shutil.copytree(project_dir / "assets", build_dir / "assets")
            print_success("Copied assets directory")
        
        if (project_dir / "config").exists():
            shutil.copytree(project_dir / "config", build_dir / "config")
            print_success("Copied config directory")
        
        # 5.5. Create .mineplex-common-name file
        server_dir = build_dir / "server"
        server_dir.mkdir(parents=True, exist_ok=True)
        common_name_file = server_dir / ".mineplex-common-name"
        with open(common_name_file, 'w') as f:
            f.write(container_name)
        print_success(f"Created .mineplex-common-name file with: {container_name}")
        
        # 5. Create Dockerfile
        dockerfile = build_dir / "Dockerfile"
        with open(dockerfile, 'w') as f:
            f.write("FROM itzg/minecraft-server:latest\n\n")
            f.write("# Set environment variables\n")
            f.write("ENV EULA=TRUE\n")
            f.write("ENV TYPE=PAPER\n")
            f.write("ENV VERSION=1.21.8\n")
            f.write("ENV MEMORY=2G\n")
            f.write("ENV ENABLE_RCON=true\n")
            f.write("ENV RCON_PORT=25575\n")
            f.write("ENV DEBUG=true\n")
            f.write("ENV DEBUG_PORT=5005\n")
            f.write("ENV GENERATE_STRUCTURES=false\n")
            f.write("ENV ALLOW_NETHER=false\n")
            f.write("ENV ALLOW_FLIGHT=true\n")
            f.write("ENV SPAWN_PROTECTION=0\n")
            f.write("ENV LEVEL_TYPE=FLAT\n")
            f.write("ENV LEVEL_TYPE_FLAT_GENERATOR_SETTINGS={}\n\n")
            f.write("# Copy plugins and set permissions\n")
            f.write("COPY --chown=1000:1000 plugins/ /data/plugins/\n\n")
            
            if (build_dir / "assets").exists():
                f.write("# Copy assets\n")
                f.write("COPY --chown=1000:1000 assets/ /data/assets/\n\n")
            
            if (build_dir / "config").exists():
                f.write("# Copy config\n")
                f.write("COPY --chown=1000:1000 config/ /data/config/\n\n")
            
            if (build_dir / "server").exists():
                f.write("# Copy server directory (contains .mineplex-common-name)\n")
                f.write("COPY --chown=1000:1000 server/ /server/\n\n")
            
            f.write("# Ensure plugins directory is writable\n")
            f.write("RUN chmod -R 755 /data/plugins && chmod -R 755 /data/config || true\n\n")
            
            f.write("# Note: World settings (empty world, no nether/end) are configured via environment variables above\n")
            f.write("# The itzg/minecraft-server image will generate server.properties from these env vars at runtime\n\n")
            
            f.write("# Expose Minecraft port and debug port\n")
            f.write("EXPOSE 25565\n")
            f.write("EXPOSE 5005\n\n")
            f.write("# Use the default entrypoint from the base image\n")
        
        # 7. Build Docker image with tags
        # Sanitize project ID for Docker tag (only alphanumeric, hyphens, underscores)
        sanitized_project_id = ''.join(c for c in project_id if c.isalnum() or c in ('-', '_')).lower()
        image_base = f"local-minecraft-{sanitized_project_id}"
        image_name = f"{image_base}:latest"
        
        # Create tags from game properties
        tags = [image_name]
        
        # Add tags with game name if available
        if game_name:
            tags.append(f"{image_base}:{game_name.lower().replace(' ', '-')}")
        
        # Add tag with display name if available
        display_name = game_data.get('display_name', '')
        if display_name:
            # Remove Minecraft color codes (§ followed by hex digit or letter)
            import re
            # Remove § and the following character (color code)
            clean_display = re.sub(r'§[0-9a-fk-or]', '', display_name, flags=re.IGNORECASE)
            # Remove any remaining non-ASCII and special characters, keep only alphanumeric, hyphens, underscores
            clean_display = ''.join(c for c in clean_display if c.isascii() and (c.isalnum() or c in ('-', '_'))).lower()
            if clean_display and len(clean_display) > 0:
                tags.append(f"{image_base}:{clean_display}")
        
        print_info(f"Building Docker image: {image_name}...")
        
        # Build with all tags, force rebuild without cache to ensure latest JAR is used
        build_cmd = ["docker", "build", "--no-cache"]
        for tag in tags:
            build_cmd.extend(["-t", tag])
        build_cmd.append(".")
        
        result = subprocess.run(
            build_cmd,
            cwd=build_dir,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print_error(f"Docker build failed: {result.stderr}")
            return None
        
        print_success(f"Docker image built: {image_name} (tags: {', '.join(tags)})")
        
        return {
            'project_id': project_id,
            'project_name': project_id,  # Use project ID as identifier
            'game_name': game_name,
            'display_name': display_name,
            'image_name': image_base,  # Base name without tag
            'image_tags': tags,
            'port': port,
            'build_dir': build_dir,
            'game_data': game_data
        }
        
    except Exception as e:
        print_error(f"Failed to build {project_name}: {e}")
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
        return None

def prompt_for_env_vars(project_name: str, env_keys: List[str]) -> Dict[str, str]:
    """Prompt user for environment variable values."""
    env_vars = {}
    if not env_keys:
        return env_vars
    
    print(f"\n{Colors.BLUE}Environment variables for {project_name}:{Colors.NC}")
    for key in env_keys:
        try:
            value = input(f"  {key} (default: unset): ").strip()
            env_vars[key] = value if value else "unset"
        except (EOFError, KeyboardInterrupt):
            print_warning(f"  Using default 'unset' for {key}")
            env_vars[key] = "unset"
    
    return env_vars

def create_docker_compose(projects: List[Dict], compose_file: Path, base_compose_file: Optional[Path] = None):
    """Create or update docker-compose.yml file for all projects."""
    # Load existing compose file if it exists
    existing_services = {}
    existing_networks = {}
    existing_volumes = {}
    
    # Infrastructure services to preserve (not Minecraft game services)
    infrastructure_services = {'mongodb', 'kafka', 'kafka-ui', 'zookeeper'}
    
    if base_compose_file and base_compose_file.exists():
        with open(base_compose_file, 'r') as f:
            existing_data = yaml.safe_load(f) or {}
            all_services = existing_data.get('services', {})
            existing_networks = existing_data.get('networks', {})
            existing_volumes = existing_data.get('volumes', {})
            
            # Only preserve infrastructure services, remove old Minecraft game services
            for service_name, service_config in all_services.items():
                if service_name in infrastructure_services:
                    existing_services[service_name] = service_config
                    # Ensure all existing services have deploy.replicas set to 1
                    if 'deploy' not in service_config:
                        service_config['deploy'] = {}
                    if 'replicas' not in service_config['deploy']:
                        service_config['deploy']['replicas'] = 1
    
    # Add new Minecraft services
    for project in projects:
        project_id = project['project_id']
        game_name = project.get('game_name', project_id)
        
        # Use game name for container name with "-1" suffix
        # Sanitize game name for container name (alphanumeric, hyphens, underscores only)
        sanitized_game_name = ''.join(c for c in game_name if c.isalnum() or c in ('-', '_'))
        container_name = f"{sanitized_game_name}-1"
        
        # Use project ID for service name (for docker-compose service name)
        sanitized_id = ''.join(c for c in project_id if c.isalnum() or c in ('-', '_')).lower()
        service_name = sanitized_id
        
        # Use the latest tag (first tag)
        image_tag = project['image_tags'][0] if project['image_tags'] else f"{project['image_name']}:latest"
        
        # Calculate debug port (5005 + index to avoid conflicts)
        debug_port = 5005 + (project.get('port', 25565) - 25565)
        
        # Get game data first
        game_data = project.get('game_data', {})
        
        # Build environment variables
        environment = {
            'EULA': 'TRUE',
            'TYPE': 'PAPER',
            'VERSION': '1.21.8',
            'MEMORY': '2G',
            'DEBUG': 'true',
            'DEBUG_PORT': '5005',
            'GENERATE_STRUCTURES': 'false',
            'ALLOW_NETHER': 'false',
            'ALLOW_FLIGHT': 'true',
            'SPAWN_PROTECTION': '0',
            'LEVEL_TYPE': 'FLAT',
            'LEVEL_TYPE_FLAT_GENERATOR_SETTINGS': '{}'
        }
        
        # Add Mineplex-specific environment variables
        environment['POD_NAME'] = container_name
        environment['MINEPLEX_PROJECT_ID'] = project_id
        environment['DEV_MODE'] = 'true'  # Always true for local development
        
        # Add namespace ID if available
        namespace_id = game_data.get('namespace_id', '')
        if namespace_id:
            environment['MINEPLEX_NAMESPACE_ID'] = namespace_id
        
        # Set MINEPLEX_ENVIRONMENT (defaults to empty, which will make it production in the code)
        # For local development, we can set it to 'dev' or leave empty
        environment['MINEPLEX_ENVIRONMENT'] = ''  # Empty = production, 'stg' = staging, 'dev' = development
        
        # Add secret environment variables from game properties
        secret_env_keys = game_data.get('secret_env_keys', [])
        if secret_env_keys:
            # Get environment variables for this project (should be in project dict)
            secret_env_vars = project.get('secret_env_vars', {})
            for key, value in secret_env_vars.items():
                environment[key] = value
        
        existing_services[service_name] = {
            'image': image_tag,
            'ports': [
                {'target': 25565, 'published': project['port'], 'protocol': 'tcp', 'mode': 'ingress'},
                {'target': 5005, 'published': debug_port, 'protocol': 'tcp', 'mode': 'ingress'}
            ],
            'environment': environment,
            'networks': ['local-docker-network'],
            'deploy': {
                'replicas': 1,
                'restart_policy': {
                    'condition': 'on-failure',
                    'delay': '5s',
                    'max_attempts': 3
                },
                'placement': {
                    'constraints': []
                }
            },
            'labels': {
                'com.plexverse.project.id': project_id,
                'com.plexverse.project.name': game_name,
                'com.plexverse.project.display_name': project.get('display_name', ''),
                'com.plexverse.project.port': str(project['port']),
                'com.plexverse.container.name': container_name
            }
        }
        
        # Add game properties as labels if available
        if game_data.get('namespace_id'):
            existing_services[service_name]['labels']['com.plexverse.namespace.id'] = game_data['namespace_id']
        if game_data.get('visibility'):
            existing_services[service_name]['labels']['com.plexverse.game.visibility'] = game_data['visibility']
        if game_data.get('category'):
            existing_services[service_name]['labels']['com.plexverse.game.category'] = game_data['category']
    
    # Ensure network exists (use overlay for Swarm, bridge for single-node)
    if 'local-docker-network' not in existing_networks:
        existing_networks['local-docker-network'] = {'driver': 'overlay', 'attachable': True}
    
    compose_data = {
        'version': '3.8',
        'services': existing_services,
        'networks': existing_networks
    }
    
    if existing_volumes:
        compose_data['volumes'] = existing_volumes
    
    with open(compose_file, 'w') as f:
        yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
    
    print_success(f"Created/updated docker-compose.yml with {len(projects)} Minecraft service(s)")

def main():
    # Ask if user wants to use a local local-engine JAR
    print(f"{Colors.BLUE}Use local local-engine JAR? (leave empty to download from GitHub):{Colors.NC}")
    local_jar_path = None
    try:
        local_path_input = input("  Local JAR path: ").strip()
        if local_path_input:
            local_jar_path = Path(local_path_input).expanduser().resolve()
            if not local_jar_path.exists():
                print_error(f"Local JAR path does not exist: {local_jar_path}")
                sys.exit(1)
            if not local_jar_path.is_file():
                print_error(f"Local path is not a file: {local_jar_path}")
                sys.exit(1)
            if not local_jar_path.name.lower().endswith('.jar'):
                print_warning(f"File does not have .jar extension: {local_jar_path}")
                response = input("  Continue anyway? (y/N): ").strip().lower()
                if response != 'y':
                    sys.exit(1)
            print_success(f"Using local JAR: {local_jar_path}")
            # Store in function attribute for use in build_project_image
            build_project_image._use_local_jar = True
            build_project_image._local_jar_path = str(local_jar_path)
        else:
            print_info("Will download latest release from GitHub")
            build_project_image._use_local_jar = False
            build_project_image._local_jar_path = None
    except (EOFError, KeyboardInterrupt):
        print_error("\nCancelled")
        sys.exit(1)
    
    # Prompt for project paths interactively
    print(f"\n{Colors.BLUE}Enter project paths (one per line, empty line to finish):{Colors.NC}")
    project_paths = []
    
    while True:
        try:
            path = input(f"  Project {len(project_paths) + 1}: ").strip()
            if not path:
                if len(project_paths) == 0:
                    print_error("At least one project path is required")
                    continue
                break
            project_paths.append(path)
        except (EOFError, KeyboardInterrupt):
            if len(project_paths) == 0:
                print_error("\nNo project paths provided")
                sys.exit(1)
            break
    
    if not project_paths:
        print_error("No project paths provided")
        sys.exit(1)
    base_port = 25565
    
    print_info(f"Building {len(project_paths)} project(s) in parallel...")
    
    # Build all projects in parallel
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(project_paths)) as executor:
        # Create futures with index tracking
        future_to_index = {
            executor.submit(build_project_image, path, base_port + i): i
            for i, path in enumerate(project_paths)
        }
        
        # Collect results in order
        completed_results = {}
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            result = future.result()
            if result:
                completed_results[index] = result
        
        # Sort by index to maintain order
        results = [completed_results[i] for i in sorted(completed_results.keys())]
    
    if not results:
        print_error("No projects were built successfully")
        sys.exit(1)
    
    print_success(f"Successfully built {len(results)} project(s)")
    
    # Prompt for environment variables for each project
    for project in results:
        game_data = project.get('game_data', {})
        secret_env_keys = game_data.get('secret_env_keys', [])
        if secret_env_keys:
            project_name = project.get('display_name') or project.get('game_name') or project['project_id']
            env_vars = prompt_for_env_vars(project_name, secret_env_keys)
            project['secret_env_vars'] = env_vars
    
    # Create/update docker-compose.yml
    script_dir = Path(__file__).parent.parent
    base_compose_file = script_dir / "docker-compose.yml"
    compose_file = script_dir / "docker-compose.yml"
    create_docker_compose(results, compose_file, base_compose_file)
    
    # Print summary
    print(f"\n{Colors.GREEN}Build Summary:{Colors.NC}")
    for project in results:
        game_name = project.get('game_name', project['project_id'])
        display_name = project.get('display_name', '')
        if display_name:
            print(f"  {display_name} ({project['project_id']}): {project['image_tags'][0]} (port {project['port']})")
        else:
            print(f"  {game_name} ({project['project_id']}): {project['image_tags'][0]} (port {project['port']})")
    
    # Initialize Docker Swarm if not already initialized
    print(f"\n{Colors.BLUE}Initializing Docker Swarm...{Colors.NC}")
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
            capture_output=True,
            text=True,
            check=True
        )
        swarm_state = result.stdout.strip()
        if swarm_state != "active":
            print_info("Initializing Docker Swarm...")
            subprocess.run(
                ["docker", "swarm", "init"],
                check=True,
                capture_output=True,
                text=True
            )
            print_success("Docker Swarm initialized")
        else:
            print_info("Docker Swarm already active")
    except subprocess.CalledProcessError as e:
        print_warning(f"Failed to check/initialize Docker Swarm: {e.stderr}")
        print_warning("Attempting to continue anyway...")
    
    # Ask if user wants to start services
    stack_name = "local-docker"
    print(f"\n{Colors.BLUE}Deploying Docker Stack '{stack_name}'...{Colors.NC}")
    try:
        result = subprocess.run(
            ["docker", "stack", "deploy", "-c", str(compose_file), stack_name],
            cwd=script_dir,
            check=True,
            capture_output=True,
            text=True
        )
        print_success(f"Docker Stack '{stack_name}' deployed")
        print(f"\n{Colors.GREEN}Services are running:{Colors.NC}")
        for project in results:
            game_name = project.get('game_name', project['project_id'])
            display_name = project.get('display_name', '')
            name_display = display_name if display_name else game_name
            print(f"  {name_display} ({project['project_id']}): localhost:{project['port']}")
        print(f"\n{Colors.YELLOW}To view stack services:{Colors.NC}")
        print(f"  docker stack services {stack_name}")
        print(f"\n{Colors.YELLOW}To remove the stack:{Colors.NC}")
        print(f"  docker stack rm {stack_name}")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to deploy Docker Stack: {e.stderr}")
        print(f"\n{Colors.YELLOW}You can deploy manually with:{Colors.NC}")
        print(f"  docker stack deploy -c {compose_file} {stack_name}")

if __name__ == "__main__":
    main()

