#!/usr/bin/env python3
"""
Script to rebuild and redeploy all Minecraft instances from the current docker-compose.yml.

This script:
1. Reads the docker-compose.yml to find all Minecraft service images
2. Rebuilds each image
3. Redeploys the stack/compose

Usage: python3 scripts/rebuild-minecraft-instances.py
"""

import os
import sys
import subprocess
import json
import yaml
from pathlib import Path

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

def check_docker_swarm():
    """Check if Docker Swarm is active."""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False

def get_minecraft_services(compose_file: Path):
    """Extract Minecraft service information from docker-compose.yml."""
    try:
        with open(compose_file, 'r') as f:
            compose_data = yaml.safe_load(f)
        
        services = compose_data.get('services', {})
        minecraft_services = []
        
        for service_name, service_config in services.items():
            # Skip velocity, mongo, kafka, etc.
            if service_name in ['velocity', 'mongodb', 'kafka', 'zookeeper', 'kafka-ui']:
                continue
            
            # Check if it has Minecraft-related labels
            labels = service_config.get('labels', {})
            if isinstance(labels, dict):
                project_id = labels.get('com.plexverse.project.id')
                if project_id:
                    # This is a Minecraft service
                    image = service_config.get('image', '')
                    build_config = service_config.get('build', {})
                    
                    minecraft_services.append({
                        'name': service_name,
                        'image': image,
                        'build': build_config,
                        'project_id': project_id,
                        'project_name': labels.get('com.plexverse.project.name', service_name)
                    })
        
        return minecraft_services
    except Exception as e:
        print_error(f"Failed to parse docker-compose.yml: {e}")
        return []

def load_project_paths(script_dir: Path):
    """Load project paths from saved file."""
    project_paths_file = script_dir / ".project-paths.json"
    if not project_paths_file.exists():
        return {}
    
    try:
        with open(project_paths_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_warning(f"Failed to load project paths: {e}")
        return {}

def rebuild_image(service_info: dict, project_path: str, script_dir: Path):
    """Rebuild a Docker image for a Minecraft service."""
    service_name = service_info['name']
    project_name = service_info['project_name']
    project_id = service_info['project_id']
    image = service_info['image']
    
    if not image:
        print_warning(f"Service {service_name} has no image specified, skipping")
        return False
    
    if not project_path:
        print_warning(f"No project path found for {service_name} (project ID: {project_id})")
        print_warning(f"Please run the full build script: python3 scripts/build-minecraft-images.py")
        return False
    
    project_path_obj = Path(project_path).expanduser().resolve()
    if not project_path_obj.exists():
        print_error(f"Project path does not exist: {project_path_obj}")
        return False
    
    print_info(f"Rebuilding {project_name} ({service_name}) from {project_path_obj}...")
    
    # Import the build function from the main build script
    build_script_path = script_dir / "scripts" / "build-minecraft-images.py"
    if not build_script_path.exists():
        print_error(f"Build script not found: {build_script_path}")
        return False
    
    # Add scripts directory to path and import
    scripts_dir = script_dir / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    
    try:
        # Import the build function
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_minecraft_images", build_script_path)
        build_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_module)
        
        # Rebuild the image
        result = build_module.build_project_image(str(project_path_obj), 25565)
        if result:
            print_success(f"Successfully rebuilt {project_name}")
            return True
        else:
            print_error(f"Failed to rebuild {project_name}")
            return False
    except Exception as e:
        print_error(f"Failed to rebuild {project_name}: {e}")
        import traceback
        traceback.print_exc()
        return False

def redeploy_stack(compose_file: Path, use_swarm: bool, stack_name: str = "local-docker"):
    """Redeploy the Docker stack or compose."""
    script_dir = compose_file.parent
    
    if use_swarm:
        print_info(f"Redeploying Docker Stack '{stack_name}'...")
        try:
            result = subprocess.run(
                ["docker", "stack", "deploy", "-c", str(compose_file), stack_name],
                cwd=script_dir,
                check=True,
                capture_output=True,
                text=True
            )
            print_success(f"Docker Stack '{stack_name}' redeployed")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to redeploy Docker Stack: {e.stderr}")
            return False
    else:
        print_info("Redeploying with docker-compose...")
        try:
            # Stop existing services
            subprocess.run(
                ["docker-compose", "-f", str(compose_file), "down"],
                cwd=script_dir,
                capture_output=True
            )
            
            # Start services
            result = subprocess.run(
                ["docker-compose", "-f", str(compose_file), "up", "-d", "--build"],
                cwd=script_dir,
                check=True,
                capture_output=True,
                text=True
            )
            print_success("Services redeployed with docker-compose")
            return True
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to redeploy: {e.stderr}")
            return False

def main():
    script_dir = Path(__file__).parent.parent
    compose_file = script_dir / "docker-compose.yml"
    
    if not compose_file.exists():
        print_error(f"docker-compose.yml not found at {compose_file}")
        sys.exit(1)
    
    print_info("Reading docker-compose.yml...")
    minecraft_services = get_minecraft_services(compose_file)
    
    if not minecraft_services:
        print_warning("No Minecraft services found in docker-compose.yml")
        print_info("You may need to run the build script first: python3 scripts/build-minecraft-images.py")
        sys.exit(1)
    
    print_info(f"Found {len(minecraft_services)} Minecraft service(s)")
    
    # Load project paths
    project_paths_map = load_project_paths(script_dir)
    
    if not project_paths_map:
        print_warning("No saved project paths found.")
        print_warning("Run the full build script first: python3 scripts/build-minecraft-images.py")
        sys.exit(1)
    
    # Check Docker Swarm status
    use_swarm = check_docker_swarm()
    if use_swarm:
        print_info("Docker Swarm is active")
    else:
        print_info("Using docker-compose mode")
    
    # Rebuild images
    print_info("Rebuilding Docker images...")
    rebuild_count = 0
    for service_info in minecraft_services:
        project_id = service_info['project_id']
        project_path_data = project_paths_map.get(project_id, {})
        project_path = project_path_data.get('path', '')
        
        if rebuild_image(service_info, project_path, script_dir):
            rebuild_count += 1
    
    if rebuild_count > 0:
        print_success(f"Rebuilt {rebuild_count} image(s)")
    else:
        print_warning("No images were rebuilt. Using existing images.")
    
    # Redeploy the stack/compose
    print_info("Redeploying services...")
    if redeploy_stack(compose_file, use_swarm):
        print_success("Rebuild and redeployment complete!")
        print_info("Services should be restarting with updated images")
    else:
        print_error("Redeployment failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

