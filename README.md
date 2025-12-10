# local-docker

Docker Compose setup for running local-engine with all required services.

## Overview

This repository provides a complete Docker Compose environment for local development with local-engine. It includes all the necessary services (MongoDB, Kafka) configured and ready to use.

## Services

- **MongoDB**: Database for DataStoreModule (port 27017)
- **Zookeeper**: Required for Kafka coordination
- **Kafka**: Message broker for MessagingModule (port 9092)

## Quick Start

1. Start all services:
   ```bash
   docker-compose up -d
   ```

2. Verify services are running:
   ```bash
   docker-compose ps
   ```

3. Check service logs:
   ```bash
   docker-compose logs -f
   ```

4. Stop all services:
   ```bash
   docker-compose down
   ```

5. Stop and remove volumes (clean slate):
   ```bash
   docker-compose down -v
   ```

## Configuration

The services are configured to match the default settings in local-engine's `config.yml`:

- **MongoDB**: Available at `mongodb://mongo:27017` (from within Docker network) or `mongodb://localhost:27017` (from host)
- **Kafka**: Available at `kafka:9092` (from within Docker network) or `localhost:9092` (from host)
- **Database**: MongoDB database `mineplex` is automatically created

## Usage with Minecraft Server

### Option 1: Running Minecraft Server on Host

1. Start the Docker services:
   ```bash
   docker-compose up -d
   ```

2. Configure your Minecraft server's `config.yml`:
   ```yaml
   modules:
     datastore:
       connection-string: "mongodb://localhost:27017"
       database: "mineplex"
     messaging:
       bootstrap-servers: "localhost:9092"
   ```

3. Place the local-engine plugin JAR in your server's `plugins` folder

4. Start your Minecraft server

### Option 2: Running Minecraft Server in Docker

To run the Minecraft server in Docker, you can extend this docker-compose.yml:

```yaml
  minecraft-server:
    image: itzg/minecraft-server:latest
    container_name: local-docker-minecraft
    ports:
      - "25565:25565"
    environment:
      EULA: "TRUE"
      TYPE: "PAPER"
      VERSION: "1.21"
      MEMORY: "2G"
    volumes:
      - ./server:/data
      - ./plugins:/data/plugins
    depends_on:
      mongodb:
        condition: service_healthy
      kafka:
        condition: service_healthy
    networks:
      - local-docker-network
```

Then configure the server's `config.yml` to use:
- `mongodb://mongodb:27017` (service name)
- `kafka:9092` (service name)

## Network

All services are connected via the `local-docker-network` bridge network, allowing them to communicate using service names (e.g., `mongodb`, `kafka`).

## Troubleshooting

### MongoDB Connection Issues

- Ensure MongoDB is healthy: `docker-compose ps`
- Check MongoDB logs: `docker-compose logs mongodb`
- Verify connection string matches your setup (localhost vs service name)
- Test connection: `docker-compose exec mongodb mongosh --eval "db.adminCommand('ping')"`

### Kafka Connection Issues

- Ensure Zookeeper is healthy before Kafka starts
- Check Kafka logs: `docker-compose logs kafka`
- Verify Kafka is listening: `docker-compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092`
- Check if topics are being created: `docker-compose exec kafka kafka-topics --bootstrap-server localhost:9092 --list`

### Port Conflicts

If ports 27017 or 9092 are already in use, modify the port mappings in `docker-compose.yml`:

```yaml
ports:
  - "27018:27017"  # Use 27018 on host instead
  - "9093:9092"    # Use 9093 on host instead
```

Then update your `config.yml` accordingly.

## Building Minecraft Server Docker Images

A Python script is provided to build Docker images for game projects with all required plugins and configurations. It supports building multiple projects in parallel and automatically integrates with Docker Compose.

### Installation

Install required Python dependencies:

```bash
pip install -r scripts/requirements.txt
```

### Usage

```bash
python3 scripts/build-minecraft-images.py
```

The script will prompt you to enter project paths interactively. Enter one path per line, and press Enter on an empty line when done.

### Example

```bash
$ python3 scripts/build-minecraft-images.py
Enter project paths (one per line, empty line to finish):
  Project 1: ./skyblock/player-planets
  Project 2: ./skyblock/marketplace
  Project 3: ./skyblock/exploration
  Project 4: 
```

### What the Script Does

1. **Downloads local-engine**: Automatically downloads the latest release from GitHub
2. **Builds project JARs**: Runs `buildPluginJar` Gradle task for each project in parallel
3. **Downloads dependencies**: Parses `config/game-properties.yaml` and downloads plugins listed in `dependencies.libraries`:
   - `PROTOCOLLIB` - ProtocolLib plugin
   - `LIBSDISGUISES` - LibsDisguises plugin
   - `DECENTHOLOGRAMS` - DecentHolograms plugin
4. **Copies assets & configs**: Copies `assets/` and `config/` directories to the correct locations
5. **Creates Dockerfiles**: Generates Dockerfiles using the `itzg/minecraft-server` base image
6. **Builds Docker images**: Creates Docker images for each project
7. **Updates docker-compose.yml**: Automatically adds services to docker-compose.yml
8. **Starts services**: Runs `docker-compose up -d` to start all services

### Project Structure Requirements

Your project should have:
- `config/game-properties.yaml` - Game configuration with dependencies
- `assets/` (optional) - World templates and other assets
- `build.gradle.kts` - Gradle build file with `buildPluginJar` task

### Port Assignment

Each project gets a unique port:
- First project: `25565`
- Second project: `25566`
- Third project: `25567`
- And so on...

### Output

The script:
- Creates Docker images named `local-minecraft-<project-name>:latest`
- Updates `docker-compose.yml` with new services
- Starts all services automatically

After running, you can connect to each server:
- First project: `localhost:25565`
- Second project: `localhost:25566`
- Third project: `localhost:25567`

For more details, see [scripts/README.md](scripts/README.md).

## Additional Resources

- [local-engine Repository](https://github.com/Plexverse/local-engine)
- [Mineplex Studio SDK Documentation](https://docs.mineplex.com/docs/sdk/features)
