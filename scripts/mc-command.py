#!/usr/bin/env python3
"""
Script to easily run Minecraft commands in Minecraft server containers.
Supports both Docker Swarm and Docker Compose modes.

Usage:
    python3 mc-command.py                    # Interactive mode - select server and enter commands
    python3 mc-command.py <service> <cmd>    # Run command directly
    python3 mc-command.py <service>          # Interactive mode for specific service
"""

import os
import sys
import subprocess
import argparse
from typing import List, Optional, Tuple

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color

def print_error(msg: str):
    try:
        print(f"{Colors.RED}Error: {msg}{Colors.NC}", file=sys.stderr)
    except UnicodeEncodeError:
        print(f"Error: {msg}", file=sys.stderr)

def print_success(msg: str):
    try:
        print(f"{Colors.GREEN}{msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(msg)

def print_info(msg: str):
    try:
        print(f"{Colors.CYAN}{msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(msg)

def print_warning(msg: str):
    try:
        print(f"{Colors.YELLOW}Warning: {msg}{Colors.NC}")
    except UnicodeEncodeError:
        print(f"Warning: {msg}")

def check_docker_swarm() -> bool:
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

def get_minecraft_containers(use_swarm: bool) -> List[Tuple[str, str]]:
    """
    Get list of Minecraft server containers.
    Returns list of (container_name, service_name) tuples.
    """
    containers = []
    
    try:
        if use_swarm:
            # Get services from docker-compose.yml to identify Minecraft services
            # Then find their containers
            result = subprocess.run(
                ["docker", "service", "ls", "--format", "{{.Name}}"],
                capture_output=True,
                text=True,
                check=True
            )
            services = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            
            # Filter for local-docker services and exclude infrastructure
            minecraft_services = [
                s for s in services 
                if s.startswith('local-docker_') 
                and s not in ['local-docker_velocity', 'local-docker_mongodb', 'local-docker_kafka', 
                              'local-docker_zookeeper', 'local-docker_kafka-ui']
            ]
            
            # Get container names for each service
            for service in minecraft_services:
                try:
                    # Get task ID
                    task_result = subprocess.run(
                        ["docker", "service", "ps", service, "-q", "--no-trunc"],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    task_ids = [line.strip() for line in task_result.stdout.strip().split('\n') if line.strip()]
                    
                    if task_ids:
                        # Get container ID from task
                        task_id = task_ids[0]
                        inspect_result = subprocess.run(
                            ["docker", "inspect", "--format", "{{.Status.ContainerStatus.ContainerID}}", task_id],
                            capture_output=True,
                            text=True,
                            check=True
                        )
                        container_id = inspect_result.stdout.strip()
                        
                        if container_id:
                            # Get container name
                            name_result = subprocess.run(
                                ["docker", "ps", "--filter", f"id={container_id}", "--format", "{{.Names}}"],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            container_name = name_result.stdout.strip()
                            
                            if container_name:
                                # Extract service name (remove local-docker_ prefix)
                                service_name = service.replace('local-docker_', '')
                                containers.append((container_name, service_name))
                except Exception as e:
                    # Skip services that can't be inspected
                    continue
        else:
            # Docker Compose mode - get containers directly
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.strip().split('\t')
                if len(parts) == 2:
                    container_name, image = parts
                    # Filter for Minecraft containers (exclude infrastructure)
                    if (container_name.startswith('local-docker_') and 
                        container_name not in ['local-docker_velocity', 'local-docker_mongodb', 
                                              'local-docker_kafka', 'local-docker_zookeeper', 
                                              'local-docker_kafka-ui'] and
                        'minecraft' in image.lower() or 'local-' in image.lower()):
                        # Extract service name
                        service_name = container_name.replace('local-docker_', '').split('_')[0]
                        containers.append((container_name, service_name))
        
        return containers
    except Exception as e:
        print_error(f"Failed to get containers: {e}")
        return []

def run_command(container_name: str, command: str) -> bool:
    """
    Run a Minecraft command in a container using RCON.
    The itzg/minecraft-server image has RCON enabled on port 25575.
    """
    try:
        # The itzg/minecraft-server image includes rcon-cli
        # RCON is enabled by default with password from RCON_PASSWORD env var
        # Default password is empty or can be set via environment
        
        # Try using rcon-cli directly (itzg/minecraft-server includes it)
        # rcon-cli connects to localhost:25575 by default
        result = subprocess.run(
            ["docker", "exec", container_name, "rcon-cli", command],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            if result.stdout.strip():
                # Print output, removing any color codes if needed
                output = result.stdout.strip()
                print(output)
            return True
        else:
            # If rcon-cli fails, try alternative methods
            if "rcon-cli: command not found" in result.stderr or "rcon-cli: not found" in result.stderr:
                # Fallback: try using the command file method
                # Some Minecraft server images accept commands via /data/command.txt
                result = subprocess.run(
                    ["docker", "exec", container_name, "sh", "-c", f"echo '{command}' >> /data/command.txt"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    print_info("Command queued (using command.txt method)")
                    return True
            
            if result.stderr:
                error_msg = result.stderr.strip()
                if error_msg:
                    print_error(error_msg)
            return False
            
    except subprocess.TimeoutExpired:
        print_error("Command timed out")
        return False
    except Exception as e:
        print_error(f"Failed to run command: {e}")
        return False

def interactive_mode(container_name: Optional[str] = None, service_name: Optional[str] = None):
    """Interactive mode for running commands."""
    use_swarm = check_docker_swarm()
    
    if container_name is None:
        # Show list of containers
        containers = get_minecraft_containers(use_swarm)
        
        if not containers:
            print_error("No Minecraft server containers found!")
            print_info("Make sure your servers are running with: docker compose up -d or docker stack deploy")
            sys.exit(1)
        
        print_info(f"Found {len(containers)} Minecraft server(s):")
        for i, (cont_name, serv_name) in enumerate(containers, 1):
            print(f"  {i}. {serv_name} ({cont_name})")
        
        while True:
            try:
                choice = input(f"\nSelect server (1-{len(containers)}) or 'q' to quit: ").strip()
                if choice.lower() == 'q':
                    sys.exit(0)
                
                idx = int(choice) - 1
                if 0 <= idx < len(containers):
                    container_name, service_name = containers[idx]
                    break
                else:
                    print_error(f"Invalid choice. Please enter a number between 1 and {len(containers)}")
            except ValueError:
                print_error("Invalid input. Please enter a number or 'q' to quit")
            except KeyboardInterrupt:
                print("\n")
                sys.exit(0)
    
    print_success(f"Connected to {service_name or container_name}")
    print_info("Enter Minecraft commands (or 'exit'/'quit' to exit):")
    print_info("Tip: Commands don't need the '/' prefix - just type 'help', 'list', 'say Hello', etc.")
    
    while True:
        try:
            command = input(f"{Colors.CYAN}mc>{Colors.NC} ").strip()
            
            if not command:
                continue
            
            if command.lower() in ['exit', 'quit', 'q']:
                print_info("Exiting...")
                break
            
            # Run the command
            run_command(container_name, command)
            
        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            print("\n")
            break

def main():
    parser = argparse.ArgumentParser(
        description='Run Minecraft commands in server containers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive mode - select server
  %(prog)s micro-battles            # Interactive mode for specific service
  %(prog)s micro-battles say Hello  # Run single command (no quotes needed!)
  %(prog)s micro-battles list       # List players
  %(prog)s micro-battles help       # Show help
        """
    )
    parser.add_argument('service', nargs='?', help='Service name (e.g., micro-battles)')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='Minecraft command to run (all remaining arguments)')
    
    args = parser.parse_args()
    
    use_swarm = check_docker_swarm()
    
    if args.service:
        # Find container for this service
        containers = get_minecraft_containers(use_swarm)
        matching = [(c, s) for c, s in containers if args.service.lower() in s.lower()]
        
        if not matching:
            print_error(f"Service '{args.service}' not found!")
            print_info("Available services:")
            for _, serv_name in containers:
                print(f"  - {serv_name}")
            sys.exit(1)
        
        container_name, service_name = matching[0]
        
        if args.command:
            # Join all command arguments into a single command string
            command = ' '.join(args.command)
            # Run single command
            print_info(f"Running command in {service_name}...")
            success = run_command(container_name, command)
            sys.exit(0 if success else 1)
        else:
            # Interactive mode for this service
            interactive_mode(container_name, service_name)
    else:
        # Full interactive mode
        interactive_mode()

if __name__ == "__main__":
    main()

