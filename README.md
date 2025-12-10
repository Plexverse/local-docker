<img width="4096" height="843" alt="Github Repository Header" src="https://github.com/user-attachments/assets/2ec10054-b063-441a-b6de-65f3c374ef98" />
</br>
</br>

Local Docker development environment for Mineplex game servers with Velocity proxy, auto-registration, and health checks.

## Features

- **Automated Docker Image Building**: Build Docker images for multiple Minecraft game projects in parallel
- **Velocity Proxy Integration**: Automatic server discovery and registration via Velocity proxy on port 25565
- **Docker Swarm & Compose Support**: Works with both Docker Swarm and docker-compose for flexible deployment
- **Auto-Registration Plugin**: Automatically discovers and registers game servers using Docker socket API
- **Health Checks**: Servers only become available when fully ready (monitors game state readiness)
- **Internal Networking**: All game servers use internal networking only - no port conflicts when scaling
- **Easy Scaling**: Scale game server instances up or down without manual configuration
- **Debug Port Support**: Remote debugging support on port 5005 for each server instance
- **Quick Rebuild Script**: Rebuild and redeploy all instances with a single command
- **Project Path Persistence**: Saves project paths for quick rebuilds without re-entering paths

## Using the Build Script

> [!IMPORTANT]
> Make sure Docker Desktop is started before running the script.

1. **Install dependencies:**
   ```bash
   pip install -r scripts/requirements.txt
   ```

2. **Run the script:**
   ```bash
   python3 scripts/build-minecraft-images.py
   ```

3. **Enter project paths:**
   The script will prompt you to enter Mineplex project paths. Provide the path to each project on your computer, one path per line. Press Enter on an empty line when done:
   ```
   Enter project paths (one per line, empty line to finish):
     Project 1: ./micro-battles
     Project 2: ./skywars
     Project 3: 
   ```

The script will:
- Build Docker images for each project with human-readable service names (based on game name, lowercased)
- Configure all Minecraft servers to use internal networking only (no published ports)
- Set up a Velocity proxy on port 25565 (default Minecraft port)
- Automatically register all servers with Velocity via the auto-registration plugin using Docker socket API

## Connecting to Servers

All Minecraft servers are accessible through the Velocity proxy:

- **Proxy Address:** `localhost:25565`
- **Server Names:** Use the lowercased game name with replica number (e.g., `micro-battles-1`, `micro-battles-2`, `skywars-1`)

The Velocity proxy automatically forwards players to the correct backend server based on the server name. Each replica of a service is registered as a separate server (e.g., `gamename-1`, `gamename-2`, etc.).

## Scaling Game Server Instances

To increase the number of instances for a game server:

### Using docker-compose (local mode):

```bash
# Scale the service to 3 replicas
docker-compose -f docker-compose.yml up -d --scale <service-name>=<replica-count>

# For example, to scale micro-battles to 3 instances:
docker-compose -f docker-compose.yml up -d --scale micro-battles=3

# Check the status
docker-compose -f docker-compose.yml ps

# View logs
docker-compose -f docker-compose.yml logs -f <service-name>
```

### Using Docker Swarm:

1. **List running services:**
   ```bash
   docker service ls
   ```

2. **Scale a specific game server service:**
   ```bash
   docker service scale <stack-name>_<service-name>=<replica-count>
   ```

   For example, to scale a service named `micro-battles` in the `local-docker` stack to 3 instances:
   ```bash
   docker service scale local-docker_micro-battles=3
   ```

3. **Verify scaling:**
   ```bash
   docker service ps <stack-name>_<service-name>
   ```

Since all servers use internal networking, multiple replicas can run without port conflicts. The Velocity proxy will automatically discover and register each replica as a separate server (e.g., `gamename-1`, `gamename-2`, `gamename-3`).

## Server Health Checks

Minecraft game servers have health checks configured that ensure servers are only marked as healthy (and registered with Velocity) when they are fully ready to accept players.

The health check monitors the server logs for the message:
```
Game state is now ready (isReady() = true). Allowing player logins and unregistering ReadyStateModule.
```

**Health Check Configuration:**
- **Check Interval:** Every 10 seconds
- **Timeout:** 5 seconds per check
- **Retries:** Up to 30 attempts (5 minutes total)
- **Start Period:** 60 seconds grace period before checks begin

Servers will only be registered with Velocity and available for player connections once they pass the health check. This prevents players from connecting to servers that are still initializing.

## Velocity Auto-Registration Plugin

The Velocity proxy includes an auto-registration plugin that automatically discovers and registers Minecraft servers using the Docker socket API. The plugin:

- Scans Docker services (Swarm or Compose) every 10 seconds
- Automatically registers all game server services with Velocity
- Registers each replica as a separate server (e.g., `gamename-1`, `gamename-2`, `gamename-3`)
- Automatically unregisters servers when they are removed or scaled down

The plugin uses the Docker socket mounted in the Velocity container, so no manual configuration is needed. Servers are discovered automatically based on Docker service labels.

After scaling, connect to `localhost:25565` and use `/server <server-name>` to connect to specific replicas (e.g., `/server micro-battles-1`, `/server micro-battles-2`).

The plugin is automatically downloaded from GitHub (Plexverse/local-velocity-plugin) when you run the build script. You can optionally provide a local path to use a custom build instead.

For more information about the plugin, see [local-velocity-plugin](../local-velocity-plugin/README.md).

## Debugging Minecraft Servers

Each Minecraft server instance has a debug port configured for remote debugging. The debug port is set to `5005` by default.

### Connecting to Debug Port

Since Minecraft servers use internal networking only, you need to access the debug port through Docker. Here are the methods:

#### Method 1: Port Forwarding (Recommended)

Forward the container's debug port to your local machine:

```bash
# For docker-compose
docker-compose -f docker-compose.yml exec <service-name> sh -c "socat TCP-LISTEN:5005,fork,reuseaddr TCP:localhost:5005" &
# Then connect to localhost:5005 from your IDE

# Or use docker port forwarding
docker port <container-name> 5005
```

#### Method 2: Direct Container Access

If you know the container name or ID:

```bash
# Find the container
docker ps | grep <service-name>

# Get the container IP
docker inspect <container-id> | grep IPAddress

# Connect to the debug port using the container IP
# Note: This only works if the debug port is accessible within the Docker network
```

#### Method 3: Publish Debug Port (Temporary)

For easier debugging, you can temporarily publish the debug port by editing `docker-compose.yml`:

```yaml
<service-name>:
  ports:
    - "5005:5005"  # Add this to publish debug port
```

Then restart the service:
```bash
# For Swarm
docker service update --publish-add 5005:5005 local-docker_<service-name>

# For docker-compose
docker-compose -f docker-compose.yml up -d <service-name>
```

**Note:** Remember to remove the published port after debugging to keep servers internal-only.

### IDE Configuration

Configure your IDE to connect to the debug port:

- **IntelliJ IDEA / Android Studio:**
  1. Run → Edit Configurations
  2. Add → Remote JVM Debug
  3. Host: `localhost` (or container IP if using Method 2)
  4. Port: `5005`
  5. Debugger mode: `Attach`

- **VS Code:**
  Add to `.vscode/launch.json`:
  ```json
  {
    "type": "java",
    "name": "Attach to Minecraft Server",
    "request": "attach",
    "hostName": "localhost",
    "port": 5005
  }
  ```

- **Eclipse:**
  1. Run → Debug Configurations
  2. Remote Java Application → New
  3. Host: `localhost`, Port: `5005`

## Rebuilding Docker Instances

When you make changes to your Minecraft project code, you need to rebuild the Docker images and redeploy the services.

### Full Rebuild (Recommended)

The recommended way is to run the full build script again, which will rebuild all images:

```bash
python3 scripts/build-minecraft-images.py
```

This will:
- Rebuild Docker images for all projects
- Update the docker-compose.yml
- Redeploy the stack/compose

### Quick Rebuild Script

For a quicker rebuild and redeploy of existing instances (without rebuilding images), use the rebuild script:

```bash
python3 scripts/rebuild-minecraft-instances.py
```

**Note:** This script redeploys services but doesn't rebuild images. To rebuild images with code changes, you must run the full build script.

### Manual Rebuild

You can also manually rebuild and redeploy:

#### Using Docker Swarm:

```bash
# Rebuild a specific service image (requires project path)
# First, rebuild the image using the build script, then:
docker service update --force local-docker_<service-name>
```

#### Using docker-compose:

```bash
# Rebuild and restart a specific service
docker-compose -f docker-compose.yml up -d --build <service-name>

# Rebuild and restart all services
docker-compose -f docker-compose.yml up -d --build
```

### Rebuilding After Code Changes

1. **Make your code changes** in the project directory
2. **Run the build script:**
   ```bash
   python3 scripts/build-minecraft-images.py
   ```
3. **The script will:**
   - Detect the project paths from docker-compose.yml (or prompt you)
   - Rebuild the Docker images with your changes
   - Update and redeploy the services

The build script uses `--no-cache` by default to ensure fresh builds with your latest code changes.
